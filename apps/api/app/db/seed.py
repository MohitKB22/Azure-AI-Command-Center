"""Seed the database with clearly labelled synthetic demo data.

Run with:  python -m app.db.seed          (idempotent — safe to re-run)
           python -m app.db.seed --reset  (drops and recreates every table)

Every row created here has `is_demo=True` where the model supports it, and every
document body is explicitly marked as demo content.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.core.logging import configure_logging, get_logger
from app.core.rbac import Role
from app.core.security import hash_password
from app.db.models import (
    Agent,
    AgentVersion,
    Alert,
    AzureResource,
    Budget,
    Document,
    EvaluationDataset,
    GuardrailPolicy,
    ModelCatalogEntry,
    Prompt,
    PromptVersion,
    RagPipeline,
    User,
)
from app.db.seed_content import DEMO_DOCUMENTS, DEMO_EVALUATION_ITEMS
from app.services import costs
from app.services.rag import checksum, ingest_document
from app.services.runner import execute_agent

logger = get_logger("seed")

DEMO_PASSWORD = "Passw0rd!Demo"

USERS = [
    ("admin@contoso.com", "Avery Chen", Role.ADMIN, "Platform"),
    ("engineer@contoso.com", "Priya Nair", Role.AI_ENGINEER, "Platform"),
    ("dev@contoso.com", "Marco Silva", Role.DEVELOPER, "Support Engineering"),
    ("analyst@contoso.com", "Dana Whitfield", Role.ANALYST, "Finance"),
    ("viewer@contoso.com", "Sam Okafor", Role.VIEWER, "Compliance"),
]

MODELS = [
    {
        "name": "GPT-4o",
        "deployment_name": "gpt-4o",
        "kind": "chat",
        "context_window": 128_000,
        "max_output_tokens": 16_384,
        "capabilities": ["chat", "reasoning", "json_mode", "vision"],
        "input_cost_per_1k": 0.005,
        "output_cost_per_1k": 0.015,
        "is_default": True,
        "notes": "Primary reasoning model for complex agents.",
    },
    {
        "name": "GPT-4o mini",
        "deployment_name": "gpt-4o-mini",
        "kind": "chat",
        "context_window": 128_000,
        "max_output_tokens": 16_384,
        "capabilities": ["chat", "json_mode", "classification"],
        "input_cost_per_1k": 0.00015,
        "output_cost_per_1k": 0.0006,
        "is_fallback": True,
        "notes": "Cheap, fast. Preferred for routing and summarisation.",
    },
    {
        "name": "GPT-3.5 Turbo",
        "deployment_name": "gpt-35-turbo",
        "kind": "chat",
        "context_window": 16_385,
        "max_output_tokens": 4_096,
        "capabilities": ["chat"],
        "input_cost_per_1k": 0.0005,
        "output_cost_per_1k": 0.0015,
        "status": "deprecated",
        "notes": "Retained for cost comparison only.",
    },
    {
        "name": "text-embedding-3-large",
        "deployment_name": "text-embedding-3-large",
        "kind": "embedding",
        "context_window": 8_191,
        "max_output_tokens": 1,
        "capabilities": ["embedding"],
        "input_cost_per_1k": 0.00013,
        "output_cost_per_1k": 0.0,
        "notes": "Production embedding model when EMBEDDING_PROVIDER=azure.",
    },
    {
        "name": "text-embedding-3-small",
        "deployment_name": "text-embedding-3-small",
        "kind": "embedding",
        "context_window": 8_191,
        "max_output_tokens": 1,
        "capabilities": ["embedding"],
        "input_cost_per_1k": 0.00002,
        "output_cost_per_1k": 0.0,
        "notes": "Lower cost embedding option.",
    },
    {
        "name": "Local Grounded (offline)",
        "provider": "local",
        "deployment_name": "local-grounded",
        "kind": "chat",
        "context_window": 32_000,
        "max_output_tokens": 2_048,
        "capabilities": ["chat", "extractive", "offline"],
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "notes": "Deterministic extractive responder used when LLM_PROVIDER=local.",
    },
]

AGENTS = [
    {
        "name": "Support Answering Agent",
        "description": "Answers customer support questions from the indexed knowledge base.",
        "system_prompt": (
            "You are Contoso's support assistant. Answer only from the retrieved context. "
            "Always cite the source document. If the context does not answer the question, "
            "say so and offer to escalate. Never promise refunds or timelines."
        ),
        "tags": ["support", "customer-facing"],
        "status": "active",
        "environment": "production",
        "rag_enabled": True,
        "tools": [],
    },
    {
        "name": "Platform Runbook Assistant",
        "description": "Helps on-call engineers navigate runbooks and incident history.",
        "system_prompt": (
            "You are an on-call assistant. Answer from runbooks and postmortems only. "
            "Be concise and lead with the action the engineer should take."
        ),
        "tags": ["operations", "internal"],
        "status": "active",
        "environment": "production",
        "rag_enabled": True,
        "tools": ["current_time"],
    },
    {
        "name": "FinOps Cost Analyst",
        "description": "Explains AI spend drivers and answers cost policy questions.",
        "system_prompt": (
            "You are a FinOps analyst. Explain cost drivers using the cost policy and "
            "usage data. Show arithmetic when you compute a figure."
        ),
        "tags": ["finops", "internal"],
        "status": "active",
        "environment": "staging",
        "rag_enabled": True,
        "tools": ["calculator"],
    },
    {
        "name": "Security Review Agent",
        "description": "Reviews AI workloads against the data classification policy.",
        "system_prompt": (
            "You are a security reviewer. Apply the data classification policy strictly. "
            "When a workload is non-compliant, name the specific rule it breaks."
        ),
        "tags": ["security", "governance"],
        "status": "active",
        "environment": "development",
        "rag_enabled": True,
        "tools": ["url_allowlist_check"],
    },
    {
        "name": "Onboarding Guide",
        "description": "Answers new-joiner questions about the AI platform.",
        "system_prompt": (
            "You are an onboarding guide. Be welcoming and practical. Answer from the "
            "onboarding FAQ and platform standards."
        ),
        "tags": ["onboarding", "internal"],
        "status": "active",
        "environment": "development",
        "rag_enabled": True,
        "tools": [],
    },
    {
        "name": "Draft Release Notes Agent",
        "description": "Drafts release notes from changelog inputs. Not yet released.",
        "system_prompt": "You draft concise release notes grouped by user-visible impact.",
        "tags": ["docs"],
        "status": "draft",
        "environment": "development",
        "rag_enabled": False,
        "tools": [],
        "enabled": False,
    },
]

PROMPTS = [
    {
        "key": "support.answer",
        "name": "Support answer",
        "description": "Grounded answer template for the support agent.",
        "tags": ["support", "production"],
        "versions": [
            (
                "Answer the customer question using only the context below.\n\n"
                "Context:\n{{context}}\n\nQuestion: {{question}}\n\n"
                "If the context is insufficient, say so.",
                "Initial version",
                "production",
                "approved",
            ),
            (
                "You are answering a Contoso customer.\n\nContext:\n{{context}}\n\n"
                "Question: {{question}}\n\nRules:\n"
                "- Cite the source document for every claim.\n"
                "- If the context is insufficient, say so and offer escalation.\n"
                "- Never promise refunds or timelines.",
                "Added citation and escalation rules",
                "production",
                "approved",
            ),
        ],
    },
    {
        "key": "runbook.triage",
        "name": "Runbook triage",
        "description": "First-response triage prompt for on-call engineers.",
        "tags": ["operations"],
        "versions": [
            (
                "Incident: {{incident}}\nSymptoms: {{symptoms}}\n\n"
                "Using the runbooks in context, give the first three actions to take.",
                "Initial version",
                "staging",
                "approved",
            ),
        ],
    },
    {
        "key": "finops.explain",
        "name": "FinOps explanation",
        "description": "Explains a cost change to a non-technical stakeholder.",
        "tags": ["finops"],
        "versions": [
            (
                "Explain the change in AI spend for {{team}} between {{period_a}} and "
                "{{period_b}}. Lead with the single largest driver.",
                "Initial version",
                "development",
                "draft",
            ),
            (
                "Explain the change in AI spend for {{team}} between {{period_a}} and "
                "{{period_b}}.\n\nStructure:\n1. Largest driver\n2. Secondary drivers\n"
                "3. Recommended action\n\nAvoid jargon.",
                "Structured output",
                "development",
                "draft",
            ),
        ],
    },
]

AZURE_RESOURCES = [
    ("contoso-aoai-eastus", "Microsoft.CognitiveServices", "eastus", "rg-contoso-ai-prod"),
    ("contoso-search-eastus", "Microsoft.Search", "eastus", "rg-contoso-ai-prod"),
    ("contosoaistorage", "Microsoft.Storage", "eastus", "rg-contoso-ai-prod"),
    ("contoso-pg-flex", "Microsoft.DBforPostgreSQL", "eastus", "rg-contoso-ai-prod"),
    ("contoso-redis", "Microsoft.Cache", "eastus", "rg-contoso-ai-prod"),
    ("contoso-appinsights", "Microsoft.Insights", "eastus", "rg-contoso-ai-prod"),
]


def _get_or_create(db, model, defaults=None, **filters):
    instance = db.execute(select(model).filter_by(**filters)).scalar_one_or_none()
    if instance is not None:
        return instance, False
    instance = model(**{**filters, **(defaults or {})})
    db.add(instance)
    db.flush()
    return instance, True


def seed(reset: bool = False, with_runs: bool = True) -> dict:
    configure_logging()
    if reset:
        logger.warning("dropping_all_tables")
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    created = {
        "users": 0,
        "models": 0,
        "pipelines": 0,
        "policies": 0,
        "documents": 0,
        "agents": 0,
        "prompts": 0,
        "runs": 0,
        "usage_records": 0,
    }
    rng = random.Random(20240814)
    db = SessionLocal()

    try:
        # ---------------------------------------------------------- users
        password_hash = hash_password(DEMO_PASSWORD)
        for email, name, role, team in USERS:
            _, made = _get_or_create(
                db,
                User,
                defaults={
                    "full_name": name,
                    "hashed_password": password_hash,
                    "role": role.value,
                    "team": team,
                    "is_demo": True,
                },
                email=email,
            )
            created["users"] += int(made)
        admin = db.execute(select(User).where(User.email == USERS[0][0])).scalar_one()

        # --------------------------------------------------------- models
        for spec in MODELS:
            payload = {**spec}
            provider = payload.pop("provider", "azure_openai")
            _, made = _get_or_create(
                db,
                ModelCatalogEntry,
                defaults={**payload, "is_demo": True},
                provider=provider,
                deployment_name=payload["deployment_name"],
            )
            created["models"] += int(made)

        chat_models = list(
            db.execute(
                select(ModelCatalogEntry).where(
                    ModelCatalogEntry.kind == "chat",
                    ModelCatalogEntry.status == "available",
                )
            ).scalars()
        )
        default_model = next((m for m in chat_models if m.is_default), chat_models[0])
        fallback_model = next(
            (m for m in chat_models if m.is_fallback), chat_models[-1]
        )

        # ------------------------------------------------------ pipelines
        pipeline, made = _get_or_create(
            db,
            RagPipeline,
            defaults={
                "description": "Contoso RAG standard v3 defaults.",
                "chunk_size": 900,
                "chunk_overlap": 150,
                "top_k": 5,
                "similarity_threshold": 0.05,
                "reranking_enabled": True,
                "is_default": True,
                "is_demo": True,
            },
            name="Standard Knowledge Base",
        )
        created["pipelines"] += int(made)
        _, made = _get_or_create(
            db,
            RagPipeline,
            defaults={
                "description": "High precision: larger chunks, higher threshold.",
                "chunk_size": 1400,
                "chunk_overlap": 200,
                "top_k": 3,
                "similarity_threshold": 0.15,
                "reranking_enabled": True,
                "is_demo": True,
            },
            name="High Precision Compliance",
        )
        created["pipelines"] += int(made)

        # ------------------------------------------------------- policies
        policy, made = _get_or_create(
            db,
            GuardrailPolicy,
            defaults={
                "description": "Baseline: block injection, redact PII.",
                "detect_prompt_injection": True,
                "redact_pii": True,
                "block_on_injection": True,
                "max_input_chars": 8000,
                "tool_allowlist": ["calculator", "current_time", "url_allowlist_check"],
                "domain_allowlist": ["contoso.com", "learn.microsoft.com"],
                "is_default": True,
                "is_demo": True,
            },
            name="Baseline Policy",
        )
        created["policies"] += int(made)
        _, made = _get_or_create(
            db,
            GuardrailPolicy,
            defaults={
                "description": "Customer-facing: citations required, no tools.",
                "detect_prompt_injection": True,
                "redact_pii": True,
                "block_on_injection": True,
                "require_citations": True,
                "max_input_chars": 4000,
                "tool_allowlist": [],
                "domain_allowlist": ["contoso.com"],
                "is_demo": True,
            },
            name="Customer Facing Policy",
        )
        created["policies"] += int(made)

        # ------------------------------------------------------ documents
        for spec in DEMO_DOCUMENTS:
            raw = spec["text"].strip().encode("utf-8")
            digest = checksum(raw)
            existing = db.execute(
                select(Document).where(Document.checksum == digest)
            ).scalar_one_or_none()
            if existing:
                continue
            document = Document(
                filename=spec["filename"],
                content_type="text/markdown",
                size_bytes=len(raw),
                checksum=digest,
                status="pending",
                tags=[*spec["tags"], "demo"],
                pipeline_id=pipeline.id,
                uploaded_by=admin.id,
                doc_metadata={"source": "seed", "synthetic": True},
                is_demo=True,
            )
            db.add(document)
            db.flush()
            ingest_document(db, document, raw, pipeline=pipeline)
            created["documents"] += 1

        # --------------------------------------------------------- agents
        agent_objects: list[Agent] = []
        for spec in AGENTS:
            slug = spec["name"].lower().replace(" ", "-")
            agent, made = _get_or_create(
                db,
                Agent,
                defaults={
                    "name": spec["name"],
                    "description": spec["description"],
                    "system_prompt": spec["system_prompt"],
                    "status": spec["status"],
                    "environment": spec["environment"],
                    "enabled": spec.get("enabled", True),
                    "rag_enabled": spec["rag_enabled"],
                    "tools": spec["tools"],
                    "tags": [*spec["tags"], "demo"],
                    "model_id": default_model.id,
                    "fallback_model_id": fallback_model.id,
                    "rag_pipeline_id": pipeline.id if spec["rag_enabled"] else None,
                    "guardrail_policy_id": policy.id,
                    "created_by": admin.id,
                    "updated_by": admin.id,
                    "is_demo": True,
                },
                slug=slug,
            )
            if made:
                created["agents"] += 1
                db.add(
                    AgentVersion(
                        agent_id=agent.id,
                        version=1,
                        snapshot={"name": agent.name, "seeded": True},
                        changelog="Seeded demo agent",
                        created_by=admin.id,
                    )
                )
            agent_objects.append(agent)

        # -------------------------------------------------------- prompts
        for spec in PROMPTS:
            prompt, made = _get_or_create(
                db,
                Prompt,
                defaults={
                    "name": spec["name"],
                    "description": spec["description"],
                    "tags": [*spec["tags"], "demo"],
                    "owner_id": admin.id,
                    "active_version": len(spec["versions"]),
                    "is_demo": True,
                },
                key=spec["key"],
            )
            if made:
                created["prompts"] += 1
                for index, (template, changelog, environment, approval) in enumerate(
                    spec["versions"], start=1
                ):
                    import re

                    db.add(
                        PromptVersion(
                            prompt_id=prompt.id,
                            version=index,
                            template=template,
                            variables=sorted(
                                set(re.findall(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}",
                                                template))
                            ),
                            environment=environment,
                            approval_status=approval,
                            changelog=changelog,
                            created_by=admin.id,
                        )
                    )

        # ------------------------------------------------ evaluation data
        _get_or_create(
            db,
            EvaluationDataset,
            defaults={
                "description": "Demo questions covering the seeded corpus, "
                "including one adversarial prompt.",
                "items": DEMO_EVALUATION_ITEMS,
                "is_demo": True,
            },
            name="Platform Knowledge Baseline",
        )

        # ------------------------------------------------ azure resources
        for name, resource_type, region, group in AZURE_RESOURCES:
            _get_or_create(
                db,
                AzureResource,
                defaults={
                    "resource_type": resource_type,
                    "region": region,
                    "resource_group": group,
                    "status": "not_configured",
                    "data_source": "none",
                    "details": {
                        "note": "Seeded inventory entry. No metrics are synthesised; "
                        "connect Azure credentials for live data."
                    },
                    "is_demo": True,
                },
                name=name,
            )

        # -------------------------------------------------------- budgets
        _get_or_create(
            db,
            Budget,
            defaults={
                "scope": "monthly",
                "amount": 2500.0,
                "warning_threshold": 0.8,
                "team": "Platform",
                "currency": "USD",
            },
            name="Platform monthly",
        )
        _get_or_create(
            db,
            Budget,
            defaults={
                "scope": "monthly",
                "amount": 750.0,
                "warning_threshold": 0.75,
                "team": "Support Engineering",
                "currency": "USD",
            },
            name="Support monthly",
        )

        # --------------------------------------------------------- alerts
        for title, severity, source, description in [
            (
                "Retrieval latency above 5s on Support Answering Agent",
                "warning",
                "platform",
                "p95 retrieval latency exceeded the 5 second threshold for 12 minutes.",
            ),
            (
                "Platform monthly budget at 82%",
                "warning",
                "finops",
                "Spend crossed the 80% warning threshold with 9 days remaining.",
            ),
            (
                "Prompt injection attempt blocked",
                "critical",
                "guardrails",
                "An instruction-override attempt was blocked before reaching the model.",
            ),
            (
                "Azure OpenAI not configured",
                "info",
                "platform",
                "Running in local provider mode. No Azure endpoint is configured.",
            ),
        ]:
            _get_or_create(
                db,
                Alert,
                defaults={
                    "description": description,
                    "severity": severity,
                    "source": source,
                    "status": "active",
                    "is_demo": True,
                    "context": {"synthetic": True},
                },
                title=title,
            )

        db.commit()

        # ------------------------------------------- real runs + usage
        if with_runs:
            questions = [
                "What is the default chunk size and overlap?",
                "What availability do we target during business hours?",
                "What caused incident 2043 and how was it resolved?",
                "Which cost lever should teams apply first?",
                "What groundedness score is required for production?",
                "How do I roll back a bad prompt?",
                "What happens to restricted data?",
                "When should the support agent escalate to a human?",
            ]
            runnable = [a for a in agent_objects if a.enabled and a.rag_enabled]
            for index, question in enumerate(questions):
                agent = runnable[index % len(runnable)]
                execute_agent(db, agent, question, user=admin)
                created["runs"] += 1
            db.commit()

            # Historical usage so the dashboards have a trend to draw.
            now = datetime.now(timezone.utc)
            for day_offset in range(1, 21):
                day = now - timedelta(days=day_offset)
                for _ in range(rng.randint(4, 18)):
                    model = rng.choice([default_model, fallback_model])
                    agent = rng.choice(agent_objects)
                    prompt_tokens = rng.randint(400, 3200)
                    completion_tokens = rng.randint(60, 700)
                    costs.record_usage(
                        db,
                        model=model,
                        model_name=model.name,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        latency_ms=rng.randint(500, 4200),
                        agent_id=agent.id,
                        user_id=rng.choice(
                            list(db.execute(select(User.id)).scalars().all())
                        ),
                        team=rng.choice(["Platform", "Support Engineering", "Finance"]),
                        succeeded=rng.random() > 0.04,
                        is_demo=True,
                        occurred_at=day.replace(
                            hour=rng.randint(7, 20), minute=rng.randint(0, 59)
                        ),
                    )
                    created["usage_records"] += 1
            db.commit()

        logger.info("seed_complete", extra=created)
        return created

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo data.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables")
    parser.add_argument("--no-runs", action="store_true", help="Skip agent runs and usage history")
    args = parser.parse_args()

    if settings.environment == "production" and not settings.demo_mode:
        print("Refusing to seed demo data into a production environment.", file=sys.stderr)
        return 1

    created = seed(reset=args.reset, with_runs=not args.no_runs)
    print("Seed complete:")
    for key, value in created.items():
        print(f"  {key:16} {value}")
    print(f"\nDemo sign-in: {USERS[0][0]} / {DEMO_PASSWORD}")
    print("All seeded records are synthetic and labelled as demo data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
