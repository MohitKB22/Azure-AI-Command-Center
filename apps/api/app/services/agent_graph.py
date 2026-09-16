"""LangGraph agent execution graph.

START -> validate_input -> guardrail_input -> route -> retrieve -> tools
      -> assemble_context -> generate -> guardrail_output -> telemetry -> END

The graph is acyclic by construction, so it cannot loop forever. Retries and
model fallback are handled inside the `generate` node with a bounded attempt
counter rather than by cycling edges.
"""

from __future__ import annotations

import time
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.core.errors import ProviderError, ProviderNotConfiguredError
from app.core.logging import get_logger
from app.db.models import Agent, GuardrailPolicy, ModelCatalogEntry
from app.providers.base import ChatMessage
from app.providers.registry import get_llm
from app.services import guardrails as gr
from app.services.rag import build_context, resolve_pipeline, retrieve
from app.services.tools import ToolExecutionError, available_tools, run_tool

logger = get_logger(__name__)

MAX_ATTEMPTS = 3


def _append(left: list, right: list) -> list:
    return (left or []) + (right or [])


class AgentState(TypedDict, total=False):
    # inputs
    question: str
    agent_id: str
    correlation_id: str | None
    tool_args: dict[str, Any]
    # working values
    sanitized_question: str
    route: str
    context: str
    citations: list[dict[str, Any]]
    retrieval: dict[str, Any]
    tool_results: list[dict[str, Any]]
    answer: str
    # accounting
    prompt_tokens: int
    completion_tokens: int
    model_name: str
    used_fallback: bool
    attempts: int
    # control
    halted: bool
    status: str
    error_code: str | None
    error_message: str | None
    guardrail_outcome: str
    findings: Annotated[list[dict[str, Any]], _append]
    steps: Annotated[list[dict[str, Any]], _append]


def _step(node: str, started: float, status: str = "ok", **detail: Any) -> dict[str, Any]:
    return {
        "node": node,
        "status": status,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "detail": detail,
    }


def build_graph(db: Session, agent: Agent, policy: GuardrailPolicy | None):
    """Compile the execution graph for a single agent invocation."""

    llm = get_llm()
    primary: ModelCatalogEntry | None = agent.model
    fallback: ModelCatalogEntry | None = agent.fallback_model

    def validate_input(state: AgentState) -> AgentState:
        started = time.perf_counter()
        question = (state.get("question") or "").strip()
        if not question:
            return {
                "halted": True,
                "status": "failed",
                "error_code": "empty_input",
                "error_message": "Input must not be empty.",
                "steps": [_step("validate_input", started, "failed", reason="empty")],
            }
        return {
            "sanitized_question": question,
            "attempts": 0,
            "halted": False,
            "status": "running",
            "guardrail_outcome": "pass",
            "steps": [_step("validate_input", started, chars=len(question))],
        }

    def guardrail_input(state: AgentState) -> AgentState:
        started = time.perf_counter()
        if state.get("halted"):
            return {}
        decision = gr.evaluate_input(state["sanitized_question"], policy)
        findings = [
            {"stage": "input", "rule": f.rule, "severity": f.severity, "detail": f.detail}
            for f in decision.findings
        ]
        if decision.blocked:
            return {
                "halted": True,
                "status": "blocked",
                "guardrail_outcome": "blocked",
                "error_code": "guardrail_blocked",
                "error_message": "Input was blocked by the guardrail policy.",
                "answer": (
                    "This request was blocked before reaching the model because it "
                    "matched a guardrail rule."
                ),
                "findings": findings,
                "steps": [_step("guardrail_input", started, "blocked", rules=len(findings))],
            }
        return {
            "sanitized_question": decision.text,
            "guardrail_outcome": decision.outcome,
            "findings": findings,
            "steps": [
                _step("guardrail_input", started, action=decision.action, rules=len(findings))
            ],
        }

    def route(state: AgentState) -> AgentState:
        started = time.perf_counter()
        if state.get("halted"):
            return {}
        question = state["sanitized_question"].lower()
        allowed = gr.filter_tools(list(agent.tools or []), policy)
        if any(tool in allowed for tool in ("calculator",)) and any(
            token in question for token in ("+", "-", "*", "/", "calculate", "sum of")
        ):
            selected = "tool"
        elif agent.rag_enabled:
            selected = "retrieval"
        else:
            selected = "direct"
        return {
            "route": selected,
            "steps": [_step("route", started, route=selected, allowed_tools=allowed)],
        }

    def retrieve_node(state: AgentState) -> AgentState:
        started = time.perf_counter()
        if state.get("halted") or state.get("route") == "direct":
            return {"steps": [_step("retrieve", started, "skipped")]}
        pipeline = resolve_pipeline(db, agent.rag_pipeline_id)
        result = retrieve(db, state["sanitized_question"], pipeline=pipeline)
        return {
            "citations": result.citations,
            "retrieval": {
                "pipeline": result.pipeline,
                "stages": result.stages,
                "candidates": result.candidates_considered,
                "returned": len(result.chunks),
                "latency_ms": result.latency_ms,
            },
            "context": build_context(result),
            "steps": [
                _step(
                    "retrieve",
                    started,
                    candidates=result.candidates_considered,
                    returned=len(result.chunks),
                    pipeline=result.pipeline.get("name"),
                )
            ],
        }

    def tools_node(state: AgentState) -> AgentState:
        started = time.perf_counter()
        if state.get("halted") or state.get("route") != "tool":
            return {"steps": [_step("tools", started, "skipped")]}
        allowed = gr.filter_tools(list(agent.tools or []), policy)
        results: list[dict[str, Any]] = []
        for tool_name in allowed:
            if tool_name not in available_tools():
                continue
            try:
                output = run_tool(
                    tool_name,
                    state["sanitized_question"],
                    policy=policy,
                    extra=state.get("tool_args") or {},
                )
                results.append({"tool": tool_name, "status": "ok", "output": output})
            except ToolExecutionError as exc:
                # Tool failure is not fatal: the model still answers from context.
                results.append({"tool": tool_name, "status": "error", "output": str(exc)})
        return {
            "tool_results": results,
            "steps": [_step("tools", started, executed=[r["tool"] for r in results])],
        }

    def assemble_context(state: AgentState) -> AgentState:
        started = time.perf_counter()
        if state.get("halted"):
            return {}
        parts = []
        if state.get("context"):
            parts.append(state["context"])
        for result in state.get("tool_results") or []:
            if result.get("status") == "ok":
                parts.append(f"[tool:{result['tool']}] {result['output']}")
        assembled = "\n\n".join(parts)
        return {
            "context": assembled,
            "steps": [_step("assemble_context", started, chars=len(assembled))],
        }

    def generate(state: AgentState) -> AgentState:
        started = time.perf_counter()
        if state.get("halted"):
            return {}

        messages = [ChatMessage(role="system", content=agent.system_prompt or "")]
        if state.get("context"):
            messages.append(
                ChatMessage(
                    role="tool",
                    content=(
                        "Use only the following retrieved context. If it does not "
                        "answer the question, say so.\n\n" + state["context"]
                    ),
                )
            )
        messages.append(ChatMessage(role="user", content=state["sanitized_question"]))

        candidates = [(primary, False)]
        if fallback is not None and fallback.id != (primary.id if primary else None):
            candidates.append((fallback, True))

        attempts = 0
        last_error: Exception | None = None
        for model, is_fallback in candidates:
            deployment = model.deployment_name if model else "local-grounded"
            model_label = model.name if model else "local-grounded"
            while attempts < MAX_ATTEMPTS:
                attempts += 1
                try:
                    result = llm.chat(
                        messages,
                        model=deployment,
                        temperature=agent.temperature,
                        max_tokens=agent.max_output_tokens,
                        timeout=float(agent.timeout_seconds),
                    )
                    return {
                        "answer": result.text,
                        "prompt_tokens": result.prompt_tokens,
                        "completion_tokens": result.completion_tokens,
                        "model_name": model_label,
                        "used_fallback": is_fallback,
                        "attempts": attempts,
                        "steps": [
                            _step(
                                "generate",
                                started,
                                model=model_label,
                                attempts=attempts,
                                fallback=is_fallback,
                                tokens=result.total_tokens,
                                provider=result.raw.get("provider"),
                                provider_note=result.raw.get("note"),
                            )
                        ],
                    }
                except (ProviderError, ProviderNotConfiguredError) as exc:
                    last_error = exc
                    if attempts >= agent.max_retries + 1:
                        break  # move on to the fallback model
                except Exception as exc:  # unexpected: do not retry blindly
                    last_error = exc
                    break

        return {
            "halted": True,
            "status": "failed",
            "attempts": attempts,
            "error_code": "generation_failed",
            "error_message": str(last_error)[:500] if last_error else "Model call failed.",
            "answer": "",
            "steps": [
                _step("generate", started, "failed", attempts=attempts, error=str(last_error)[:200])
            ],
        }

    def guardrail_output(state: AgentState) -> AgentState:
        started = time.perf_counter()
        if state.get("halted"):
            return {}
        decision = gr.evaluate_output(
            state.get("answer", ""), policy, citation_count=len(state.get("citations") or [])
        )
        findings = [
            {"stage": "output", "rule": f.rule, "severity": f.severity, "detail": f.detail}
            for f in decision.findings
        ]
        if decision.blocked:
            return {
                "answer": (
                    "The generated response was withheld because it violated the "
                    "output guardrail policy."
                ),
                "status": "blocked",
                "guardrail_outcome": "blocked",
                "findings": findings,
                "steps": [_step("guardrail_output", started, "blocked", rules=len(findings))],
            }
        outcome = state.get("guardrail_outcome", "pass")
        if decision.findings and outcome == "pass":
            outcome = "flagged"
        return {
            "answer": decision.text,
            "guardrail_outcome": outcome,
            "findings": findings,
            "steps": [
                _step("guardrail_output", started, action=decision.action, rules=len(findings))
            ],
        }

    def telemetry(state: AgentState) -> AgentState:
        started = time.perf_counter()
        status = state.get("status", "running")
        if status == "running":
            status = "succeeded"
        return {
            "status": status,
            "steps": [
                _step(
                    "telemetry",
                    started,
                    status=status,
                    citations=len(state.get("citations") or []),
                    tokens=state.get("prompt_tokens", 0) + state.get("completion_tokens", 0),
                )
            ],
        }

    graph = StateGraph(AgentState)
    graph.add_node("validate_input", validate_input)
    graph.add_node("guardrail_input", guardrail_input)
    graph.add_node("route", route)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("tools", tools_node)
    graph.add_node("assemble_context", assemble_context)
    graph.add_node("generate", generate)
    graph.add_node("guardrail_output", guardrail_output)
    graph.add_node("telemetry", telemetry)

    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "guardrail_input")
    graph.add_edge("guardrail_input", "route")
    graph.add_edge("route", "retrieve")
    graph.add_edge("retrieve", "tools")
    graph.add_edge("tools", "assemble_context")
    graph.add_edge("assemble_context", "generate")
    graph.add_edge("generate", "guardrail_output")
    graph.add_edge("guardrail_output", "telemetry")
    graph.add_edge("telemetry", END)

    return graph.compile()


GRAPH_TOPOLOGY = [
    {"id": "validate_input", "label": "Input validation", "next": ["guardrail_input"]},
    {"id": "guardrail_input", "label": "Input guardrail", "next": ["route"]},
    {"id": "route", "label": "Intent routing", "next": ["retrieve"]},
    {"id": "retrieve", "label": "Retrieval", "next": ["tools"]},
    {"id": "tools", "label": "Tool execution", "next": ["assemble_context"]},
    {"id": "assemble_context", "label": "Context assembly", "next": ["generate"]},
    {"id": "generate", "label": "Model generation", "next": ["guardrail_output"]},
    {"id": "guardrail_output", "label": "Output guardrail", "next": ["telemetry"]},
    {"id": "telemetry", "label": "Telemetry", "next": []},
]
