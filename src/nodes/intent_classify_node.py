"""IntentClassifyNode — classify query intent and resolve route for career support."""

from __future__ import annotations

from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

_SUPPORTED_ROUTES = frozenset({"grounded_qa", "timeline_guidance", "interview_preparation", "es_feedback"})
_DEFAULT_LOW_CONFIDENCE_ROUTE = "grounded_qa"
_CONFIDENCE_THRESHOLD = 0.70

# Deterministic keyword routing (pre-LLM fast path)
_ROUTE_KEYWORDS: dict[str, list[str]] = {
    "timeline_guidance": [
        "when",
        "deadline",
        "schedule",
        "season",
        "date",
        "timeline",
        "recruiting period",
        "application period",
        "intern start",
    ],
    "interview_preparation": [
        "interview",
        "prepare",
        "practice",
        "question",
        "checklist",
        "how to prepare",
        "etiquette",
        "suit",
        "dress code",
    ],
    "es_feedback": [
        "entry sheet",
        "es ",
        "personal statement",
        "motivation letter",
        "self-pr",
        "check my",
        "review my",
        "feedback on",
    ],
}


def _keyword_classify(query: str) -> tuple[str, float, str]:
    """Return (route, confidence, rationale) using keyword heuristics."""
    ql = query.lower()
    for route, keywords in _ROUTE_KEYWORDS.items():
        for kw in keywords:
            if kw in ql:
                return route, 0.85, f"keyword_match:{kw}"
    return _DEFAULT_LOW_CONFIDENCE_ROUTE, 0.55, "no_keyword_match"


class IntentClassifyNode(FunctionNode):
    """Inner node: classify query into one of four routes with confidence score.

    Uses deterministic keyword heuristics (no LLM call needed for common queries).
    Low-confidence queries default to grounded_qa with a clarification warning.
    Malicious/injection attempts cannot force unsupported routes — validation
    is already done in PreProcessNode; this node only selects from supported routes.
    """

    # Inner DomainWorkflowGraph node — ANONYMOUS (trust verified at outer boundary)
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        # Honor a pre-validated route hint from PreProcessNode
        route_hint = state.get("route_hint", "")
        if route_hint and route_hint in _SUPPORTED_ROUTES:
            emit_trace_event(
                "IntentClassifyNode_route_resolved",
                {
                    "resolved_route": route_hint,
                    "source": "caller_hint",
                    "confidence": 1.0,
                },
                state,
            )
            return {
                "resolved_route": route_hint,
                "classification_confidence": "1.0",
                "classification_rationale": "caller_hint_validated",
            }

        # The outer GraphNode passes the sanitized query as the inner graph's
        # `user_input` (see graph.py extract_input), so `sanitized_query` is
        # unset inside this graph. Reading only that key made every query miss
        # the keyword table and fall back to generic guidance.
        sanitized_query = state.get("sanitized_query") or state.get("user_input", "")

        # Classify by keyword heuristics
        route, confidence, rationale = _keyword_classify(sanitized_query)

        warnings: list[str] = []
        if confidence < _CONFIDENCE_THRESHOLD:
            # Low confidence — route to safe Q&A with clarification
            route = _DEFAULT_LOW_CONFIDENCE_ROUTE
            warnings.append(
                "Query intent was unclear. Showing general career guidance. "
                "Please specify your question (e.g. interview prep, ES feedback, timeline)."
            )
            rationale = f"low_confidence_fallback:{rationale}"

        import json

        existing_warnings = []
        try:
            existing_warnings = json.loads(state.get("warnings", "[]") or "[]")
        except (TypeError, ValueError):
            existing_warnings = []
        all_warnings = existing_warnings + warnings

        emit_trace_event(
            "IntentClassifyNode_classification_complete",
            {
                "resolved_route": route,
                "confidence": confidence,
                "rationale": rationale,
                "low_confidence": confidence < _CONFIDENCE_THRESHOLD,
            },
            state,
        )

        return {
            "resolved_route": route,
            "classification_confidence": str(confidence),
            "classification_rationale": rationale,
            "warnings": json.dumps(all_warnings, ensure_ascii=False),
        }
