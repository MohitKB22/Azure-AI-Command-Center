"""Guardrails: detection, policy, enforcement — kept explicitly separate.

Scope and honesty note
----------------------
These are *heuristic* controls. Regex-based prompt-injection detection and PII
patterns catch common, well-formed cases; they are trivially bypassed by a
motivated attacker and must not be treated as a complete security boundary.
Layer them with Azure AI Content Safety, least-privilege tool design, and
human review before trusting an agent with sensitive actions.

Structure:
  * detect_*  -> pure functions returning findings, no side effects
  * evaluate_input / evaluate_output -> apply a policy to findings
  * GuardrailDecision.action -> what the caller must enforce
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.db.models import GuardrailPolicy

INJECTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "instruction_override",
        re.compile(r"(?i)\b(ignore|disregard|forget)\b[^.\n]{0,40}\b(previous|prior|above|all)\b"
                   r"[^.\n]{0,30}\b(instruction|prompt|rule|direction)"),
        "high",
    ),
    (
        "system_prompt_exfiltration",
        re.compile(r"(?i)\b(reveal|show|print|repeat|output)\b[^.\n]{0,30}"
                   r"\b(system prompt|initial instructions|your instructions)\b"),
        "high",
    ),
    (
        "role_hijack",
        re.compile(r"(?i)^\s*(system|developer)\s*[:>]|(?i)\byou are now\b[^.\n]{0,40}\b(dan|"
                   r"unrestricted|jailbroken|no longer bound)\b"),
        "high",
    ),
    (
        "credential_probe",
        re.compile(r"(?i)\b(api[_ -]?key|connection string|access token|password|secret)\b"
                   r"[^.\n]{0,30}\b(show|print|list|reveal|what is)\b"
                   r"|(?i)\b(show|print|list|reveal|what is)\b[^.\n]{0,30}"
                   r"\b(api[_ -]?key|connection string|access token|password|secret)\b"),
        "medium",
    ),
    (
        "encoded_payload",
        re.compile(r"(?i)\b(base64|rot13|hex)\s*(decode|decoded|the following)"),
        "medium",
    ),
]

PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("us_ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(r"\b(?:\+?\d{1,3}[ -]?)?(?:\(\d{3}\)|\d{3})[ -]?\d{3}[ -]?\d{4}\b")),
    ("azure_key", re.compile(r"(?i)AccountKey=[A-Za-z0-9+/=]{20,}")),
    ("bearer_token", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}")),
]


@dataclass(slots=True)
class Finding:
    rule: str
    severity: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GuardrailDecision:
    action: str  # allow | redact | block
    text: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.action == "block"

    @property
    def outcome(self) -> str:
        if self.action == "block":
            return "blocked"
        return "flagged" if self.findings else "pass"


DEFAULT_POLICY = GuardrailPolicy(
    name="__default__",
    detect_prompt_injection=True,
    redact_pii=True,
    block_on_injection=True,
    max_input_chars=8000,
    banned_phrases=[],
    tool_allowlist=[],
    domain_allowlist=[],
    require_citations=False,
)


# ----------------------------------------------------------------- detection


def detect_prompt_injection(text: str) -> list[Finding]:
    findings = []
    for rule, pattern, severity in INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(
                Finding(
                    rule=rule,
                    severity=severity,
                    detail={"match": match.group(0)[:120], "position": match.start()},
                )
            )
    return findings


def detect_pii(text: str) -> list[Finding]:
    findings = []
    for rule, pattern in PII_PATTERNS:
        hits = pattern.findall(text)
        if hits:
            findings.append(
                Finding(rule=f"pii_{rule}", severity="medium", detail={"count": len(hits)})
            )
    return findings


def redact_pii(text: str) -> str:
    for rule, pattern in PII_PATTERNS:
        text = pattern.sub(f"[REDACTED_{rule.upper()}]", text)
    return text


def detect_banned_phrases(text: str, phrases: list[str]) -> list[Finding]:
    lowered = text.lower()
    return [
        Finding(rule="banned_phrase", severity="high", detail={"phrase": phrase})
        for phrase in phrases
        if phrase and phrase.lower() in lowered
    ]


# ------------------------------------------------------------------- policy


def evaluate_input(text: str, policy: GuardrailPolicy | None = None) -> GuardrailDecision:
    policy = policy or DEFAULT_POLICY
    findings: list[Finding] = []

    if len(text) > policy.max_input_chars:
        return GuardrailDecision(
            action="block",
            text=text[: policy.max_input_chars],
            findings=[
                Finding(
                    rule="input_too_large",
                    severity="medium",
                    detail={"length": len(text), "limit": policy.max_input_chars},
                )
            ],
        )

    if policy.detect_prompt_injection:
        findings.extend(detect_prompt_injection(text))
    findings.extend(detect_banned_phrases(text, list(policy.banned_phrases or [])))

    blocking = [f for f in findings if f.severity == "high"]
    if blocking and policy.block_on_injection:
        return GuardrailDecision(action="block", text=text, findings=findings)

    output = text
    if policy.redact_pii:
        pii = detect_pii(text)
        if pii:
            findings.extend(pii)
            output = redact_pii(text)
            return GuardrailDecision(action="redact", text=output, findings=findings)

    return GuardrailDecision(action="allow", text=output, findings=findings)


def evaluate_output(
    text: str,
    policy: GuardrailPolicy | None = None,
    *,
    citation_count: int = 0,
) -> GuardrailDecision:
    policy = policy or DEFAULT_POLICY
    findings: list[Finding] = []
    output = text

    if policy.redact_pii:
        pii = detect_pii(text)
        if pii:
            findings.extend(pii)
            output = redact_pii(text)

    findings.extend(detect_banned_phrases(text, list(policy.banned_phrases or [])))

    if policy.require_citations and citation_count == 0:
        findings.append(
            Finding(rule="missing_citations", severity="high", detail={"citations": 0})
        )
        return GuardrailDecision(action="block", text=output, findings=findings)

    if any(f.severity == "high" for f in findings):
        return GuardrailDecision(action="block", text=output, findings=findings)

    return GuardrailDecision(
        action="redact" if output != text else "allow", text=output, findings=findings
    )


def filter_tools(requested: list[str], policy: GuardrailPolicy | None = None) -> list[str]:
    """Enforcement: an empty allowlist means 'no restriction configured'."""
    policy = policy or DEFAULT_POLICY
    allowlist = list(policy.tool_allowlist or [])
    if not allowlist:
        return requested
    return [tool for tool in requested if tool in allowlist]
