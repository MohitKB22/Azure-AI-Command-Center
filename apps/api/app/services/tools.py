"""Agent tools.

Tools are deliberately few and deliberately safe. Each one declares what it
touches, and network-capable tools honour the policy domain allowlist. Adding a
tool means registering it here so the allowlist stays meaningful.
"""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.db.models import GuardrailPolicy


class ToolExecutionError(Exception):
    """Raised when a tool fails; the graph records it and continues."""


# ------------------------------------------------------------- calculator

_OPERATORS: dict[type, Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_EXPRESSION_RE = re.compile(r"[-+*/%().\d\s^]+")


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ToolExecutionError("Only numeric literals are allowed.")
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(left) > 1e6 or abs(right) > 64):
            raise ToolExecutionError("Exponent out of supported range.")
        if isinstance(node.op, (ast.Div, ast.Mod)) and right == 0:
            raise ToolExecutionError("Division by zero.")
        return _OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ToolExecutionError("Unsupported expression.")


def calculator(query: str, **_: Any) -> str:
    """Evaluate arithmetic found in the query using an AST allowlist (never eval)."""
    candidates = [m.group(0).strip() for m in _EXPRESSION_RE.finditer(query)]
    expression = max(candidates, key=len, default="").replace("^", "**")
    if not expression or not any(char.isdigit() for char in expression):
        raise ToolExecutionError("No arithmetic expression found in the request.")
    if len(expression) > 200:
        raise ToolExecutionError("Expression too long.")
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolExecutionError(f"Could not parse '{expression}'.") from exc
    result = _safe_eval(parsed)
    return f"{expression.strip()} = {result:g}"


# ------------------------------------------------------------- clock


def current_time(_: str, **__: Any) -> str:
    now = datetime.now(timezone.utc)
    return f"Current UTC time is {now.isoformat(timespec='seconds')}."


# ------------------------------------------------------------- url check


def url_allowlist_check(query: str, *, policy: GuardrailPolicy | None = None, **_: Any) -> str:
    """Policy check for URLs in the request. Reports; never fetches."""
    urls = re.findall(r"https?://[^\s)\]]+", query)
    if not urls:
        return "No URLs found in the request."
    allowlist = list((policy.domain_allowlist if policy else []) or [])
    lines = []
    for url in urls[:5]:
        host = (urlparse(url).hostname or "").lower()
        if not allowlist:
            verdict = "no allowlist configured — treated as blocked"
        elif any(host == d.lower() or host.endswith(f".{d.lower()}") for d in allowlist):
            verdict = "allowed"
        else:
            verdict = "blocked"
        lines.append(f"{host or url}: {verdict}")
    return "URL policy check — " + "; ".join(lines)


TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "calculator": {
        "fn": calculator,
        "description": "Evaluates arithmetic expressions with a parser allowlist.",
        "network": False,
    },
    "current_time": {
        "fn": current_time,
        "description": "Returns the current UTC time.",
        "network": False,
    },
    "url_allowlist_check": {
        "fn": url_allowlist_check,
        "description": "Checks URLs in the request against the policy domain allowlist.",
        "network": False,
    },
}


def available_tools() -> dict[str, dict[str, Any]]:
    return TOOL_REGISTRY


def tool_catalog() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": meta["description"], "network": meta["network"]}
        for name, meta in TOOL_REGISTRY.items()
    ]


def run_tool(
    name: str,
    query: str,
    *,
    policy: GuardrailPolicy | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    meta = TOOL_REGISTRY.get(name)
    if meta is None:
        raise ToolExecutionError(f"Unknown tool '{name}'.")
    return str(meta["fn"](query, policy=policy, **(extra or {})))
