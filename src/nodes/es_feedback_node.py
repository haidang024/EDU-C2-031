"""ESFeedbackNode — evaluate ES draft against institution-approved rubric criteria."""

from __future__ import annotations

import json
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.schemas.state import to_json

_RUBRIC_VERSION = "v2025"
_MIN_SUGGESTIONS = 3
_AUTHORSHIP_NOTICE = (
    "These suggestions are advisory only. You retain full authorship of your entry sheet. "
    "Do not submit AI-generated text directly; revise in your own words."
)
_ADVISORY_NOTICE = (
    "ES feedback is advisory and does not constitute a hiring assessment, score, or ranking. "
    "Advisers remain authoritative."
)

# Rubric criteria with default template feedback
_RUBRIC_CRITERIA = [
    {
        "criterion": "self_pr",
        "criterion_label": "Self-PR (jiko PR)",
        "prompt": "Does the ES clearly articulate unique strengths with specific evidence?",
    },
    {
        "criterion": "motivation",
        "criterion_label": "Motivation (shibo riyu)",
        "prompt": "Is the motivation for applying to this company/role specific and credible?",
    },
    {
        "criterion": "clarity",
        "criterion_label": "Clarity and structure",
        "prompt": "Is the writing clear, well-organised, and easy to follow?",
    },
    {
        "criterion": "specificity",
        "criterion_label": "Specificity and concreteness",
        "prompt": "Are claims supported by concrete examples, numbers, or outcomes?",
    },
    {
        "criterion": "evidence",
        "criterion_label": "Evidence of experience",
        "prompt": "Does the ES demonstrate relevant experience or skills tied to the target role?",
    },
    {
        "criterion": "target_role_alignment",
        "criterion_label": "Target-role alignment",
        "prompt": "Does the ES connect the applicant's background clearly to the target role?",
    },
]


def _evaluate_draft(draft: str) -> list[dict]:
    """Return rubric-grounded suggestions for the draft.

    In production, this would call an LLM with a structured rubric prompt.
    The mock implementation returns deterministic suggestions grounded in rubric
    criteria — the LLM cannot alter criterion labels, rubric refs, or advice notices.
    """
    suggestions = []

    # Self-PR: check for first-person concrete claim
    if "i " not in draft.lower() and "my " not in draft.lower():
        suggestions.append(
            {
                "criterion": "self_pr",
                "suggestion": (
                    "The draft does not clearly state a specific personal strength. "
                    "Add a concrete self-PR statement with a specific skill or achievement "
                    "(e.g. 'I led a 5-person project that reduced processing time by 30%.')."
                ),
                "span_hint": "Opening section",
                "rubric_ref": f"ES Rubric v{_RUBRIC_VERSION}, criterion: self_pr",
            }
        )

    # Motivation: check for company name or role mention
    if len(draft) < 200:
        suggestions.append(
            {
                "criterion": "motivation",
                "suggestion": (
                    "The motivation section appears brief. Explain specifically why you are "
                    "applying to this company and role — reference something concrete about "
                    "the company (e.g. a product, initiative, or value)."
                ),
                "span_hint": "Motivation section",
                "rubric_ref": f"ES Rubric v{_RUBRIC_VERSION}, criterion: motivation",
            }
        )

    # Specificity: check for numbers/quantified outcomes
    import re

    has_numbers = bool(re.search(r"\d+", draft))
    if not has_numbers:
        suggestions.append(
            {
                "criterion": "specificity",
                "suggestion": (
                    "No quantified outcomes are present. Strengthen your claims by adding "
                    "concrete figures (e.g. team size, results achieved, time saved, "
                    "percentage improvement)."
                ),
                "span_hint": "Experience/achievement section",
                "rubric_ref": f"ES Rubric v{_RUBRIC_VERSION}, criterion: specificity",
            }
        )

    # Evidence: check draft length as proxy for evidence density
    if len(draft.split()) < 80:
        suggestions.append(
            {
                "criterion": "evidence",
                "suggestion": (
                    "The draft is short and may lack sufficient evidence. "
                    "Elaborate on at least one experience with a clear problem-action-result "
                    "structure to demonstrate relevant skills."
                ),
                "span_hint": "Experience section",
                "rubric_ref": f"ES Rubric v{_RUBRIC_VERSION}, criterion: evidence",
            }
        )

    # Target-role alignment: check for role-related language
    alignment_keywords = ["role", "position", "contribute", "skill", "experience", "goal"]
    has_alignment = any(kw in draft.lower() for kw in alignment_keywords)
    if not has_alignment:
        suggestions.append(
            {
                "criterion": "target_role_alignment",
                "suggestion": (
                    "The connection between your background and the target role is not clear. "
                    "Add a closing statement explaining how your skills and goals align with "
                    "the specific responsibilities of this position."
                ),
                "span_hint": "Closing section",
                "rubric_ref": f"ES Rubric v{_RUBRIC_VERSION}, criterion: target_role_alignment",
            }
        )

    # Ensure minimum number of suggestions
    while len(suggestions) < _MIN_SUGGESTIONS:
        fallback_criterion = _RUBRIC_CRITERIA[len(suggestions) % len(_RUBRIC_CRITERIA)]
        suggestions.append(
            {
                "criterion": fallback_criterion["criterion"],
                "suggestion": (
                    f"Consider reviewing the '{fallback_criterion['criterion_label']}' dimension: "
                    f"{fallback_criterion['prompt']} "
                    "Ensure this is addressed explicitly in your draft."
                ),
                "span_hint": "General review",
                "rubric_ref": f"ES Rubric v{_RUBRIC_VERSION}, criterion: {fallback_criterion['criterion']}",
            }
        )

    return suggestions[: max(_MIN_SUGGESTIONS, len(suggestions))]


class ESFeedbackNode(FunctionNode):
    """Inner node: evaluate sanitized ES draft against the institution-approved rubric.

    Only active for 'es_feedback' route. Draft content is ephemeral and must not
    appear in audit trace or final output beyond allowed suggestion excerpts.
    No rewrite of the full draft. No score, rank, or hiring-probability claim.
    Prompt injection in the draft cannot alter rubric criterion fields or safety notices.
    """

    # Inner DomainWorkflowGraph node — ANONYMOUS
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        resolved_route = state.get("resolved_route", "grounded_qa")

        if resolved_route != "es_feedback":
            emit_trace_event(
                "ESFeedbackNode_skipped",
                {"resolved_route": resolved_route, "reason": "route_is_not_es_feedback"},
                state,
            )
            return {"es_suggestions": to_json([])}

        sanitized_es_draft = state.get("sanitized_es_draft", "")

        if not sanitized_es_draft or not sanitized_es_draft.strip():
            emit_trace_event(
                "ESFeedbackNode_no_draft",
                {"resolved_route": resolved_route, "draft_present": False},
                state,
            )
            return {
                "es_suggestions": to_json([]),
                "warnings": to_json(
                    (json.loads(state.get("warnings", "[]") or "[]")) + ["No ES draft was provided for feedback."]
                ),
            }

        suggestions = _evaluate_draft(sanitized_es_draft)

        # Audit event must NOT include draft content
        emit_trace_event(
            "ESFeedbackNode_feedback_complete",
            {
                "suggestion_count": len(suggestions),
                "rubric_version": _RUBRIC_VERSION,
                "draft_word_count": len(sanitized_es_draft.split()),
                # No draft text in trace
            },
            state,
        )

        return {
            "es_suggestions": to_json(suggestions),
        }
