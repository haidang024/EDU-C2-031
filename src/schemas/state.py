"""State — flat TypedDict for EDU-C2-031 University Career Support Agent."""

# ADR-005: State must be a flat TypedDict (msgpack serialization).
# Do NOT add credentials, InvocationContext, or ES draft content beyond active invocation.
# Structured payloads (list/dict) are JSON-encoded as str for msgpack safety.

from __future__ import annotations

import json
from typing import Optional

from framework.schemas.agent_state import AgentState


def to_json(value: object) -> str:
    """JSON-encode a structured value to a state-safe string."""
    return json.dumps(value, ensure_ascii=False)


def from_json(value: Optional[str], default: object = None) -> object:
    """Decode a JSON-encoded state field; return default on error/empty."""
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class State(AgentState):
    """Agent state for EDU-C2-031 University Career Support Agent.

    All shared fields (user_input, status, session_id, node_history,
    error_log, hitl_*, etc.) are inherited from AgentState.

    Field naming rules:
    - Structured payloads (list/dict) are JSON-encoded as str (msgpack safety).
    - No raw student PII, ES draft content beyond active invocation,
      credentials, or InvocationContext.
    - Student reference is masked/opaque; names/email/phone are never stored.
    """

    input_error_message: str | None
    input_error_guidance: list[str]
    # Inner-workflow failure reason, carried as a domain field so the run
    # keeps a valid AgentStatus and still reaches the post-process node.
    workflow_error_message: str | None
    generation_mode: str | None
    provider_error_message: str | None

    # ── Input boundary (set by PreProcessNode) ────────────────────────────────

    # Masked/anonymised student reference (opaque token, no name/email)
    masked_student_ref: str

    # Sanitized query text — PII removed, length bounded
    sanitized_query: str

    # Route hint supplied by caller
    route_hint: str

    # Target role/industry for interview prep and ES feedback
    target_role: str
    target_industry: str

    # Academic year context supplied by caller ("AY2025-2026" format)
    academic_year_context: str

    # Sanitized ES draft for feedback route — ephemeral, PII-stripped
    # JSON-encoded string; must NOT appear verbatim in final output
    sanitized_es_draft: str

    # ── Classification (set by IntentClassifyNode) ────────────────────────────

    # Resolved route: "grounded_qa" | "timeline_guidance" |
    # "interview_preparation" | "es_feedback"
    resolved_route: str

    # JSON-encoded float [0.0, 1.0]
    classification_confidence: str

    # Human-readable rationale code for audit
    classification_rationale: str

    # ── Retrieval (set by GuidanceRetrieveNode) ───────────────────────────────

    # JSON-encoded list[dict] of retrieved evidence chunks
    # Each chunk: {chunk_id, text, source_title, section, corpus_version,
    #              effective_year, citation, excerpt}
    retrieved_evidence: str

    # Corpus version/timestamp of the retrieved evidence
    corpus_version: str

    # "fresh" | "stale" | "missing" — drives whether timeline claims are allowed
    corpus_freshness: str
    # Which corpus answered: "live" when the vector-store credential is
    # provisioned, "fixture" when the bundled sample corpus was used. Recorded
    # for operators only — the caller-facing output is identical either way.
    corpus_source: str

    # ── Industry context (set by IndustryContextNode) ─────────────────────────

    # JSON-encoded dict with profile metadata and checklist items
    # checklist items: {item, rationale, citation, context_version, safety_notice}
    industry_context: str

    # ── ES feedback (set by ESFeedbackNode) ───────────────────────────────────

    # JSON-encoded list[dict] of rubric-grounded suggestions
    # Each suggestion: {criterion, suggestion, span_hint, rubric_ref}
    es_suggestions: str

    # ── Synthesis/output (set by SynthesizeNode / PostProcessNode) ────────────

    # JSON-encoded final response artifact (route-specific structure)
    response_artifact: str

    # JSON-encoded list of citation dicts for final output
    citations: str

    # Non-removable advisory notice
    advisory_notice: str

    # JSON-encoded list of warning strings (stale corpus, escalation, etc.)
    warnings: str

    # Unique request ID for correlation (no student identity)
    request_id: str
