"""SynthesizeNode — assemble route-specific response artifact from verified evidence."""

from __future__ import annotations

import json
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.schemas.state import from_json, to_json

_ADVISORY_NOTICE = (
    "Advisory career-centre support only. "
    "Advisers and employers remain authoritative for eligibility, requirements, and deadlines."
)
_VERIFY_SUFFIX = (
    " Please verify this information directly with your career centre or the employer " "before making any decisions."
)

# Guardrail: these phrases must not appear in synthesized output
_FORBIDDEN_PHRASES = [
    "you will be hired",
    "you are guaranteed",
    "guaranteed employment",
    "this employer requires",
    "you will get the job",
    "certain to pass",
    "will succeed",
]


def _build_qa_artifact(
    sanitized_query: str,
    evidence: list[dict],
    corpus_freshness: str,
    corpus_version: str,
    warnings: list[str],
) -> dict:
    """Build grounded Q&A response artifact."""
    if not evidence or corpus_freshness == "missing":
        return {
            "route": "grounded_qa",
            "answer": (
                "No relevant career guidance was found for your query. " "Please contact your career centre directly."
            ),
            "citations": [],
            "corpus_version": corpus_version or "unknown",
            "uncertainty": "high",
            "verification_next_step": "Contact career centre for authoritative guidance.",
        }

    citations = [
        {"source": e.get("source_title"), "section": e.get("section"), "citation": e.get("citation")} for e in evidence
    ]
    answer = evidence[0].get("text", "No guidance text available.")
    if corpus_freshness == "stale":
        answer += _VERIFY_SUFFIX

    return {
        "route": "grounded_qa",
        "answer": answer,
        "citations": citations,
        "corpus_version": corpus_version,
        "uncertainty": "low" if corpus_freshness == "fresh" else "medium",
        "verification_next_step": "Confirm current details with your career centre."
        if corpus_freshness != "fresh"
        else "",
    }


def _build_timeline_artifact(
    evidence: list[dict],
    corpus_freshness: str,
    corpus_version: str,
    academic_year_context: str,
    warnings: list[str],
) -> dict:
    """Build timeline guidance artifact — no date claims without current-year citation."""
    if not evidence or corpus_freshness in {"missing", "stale"}:
        return {
            "route": "timeline_guidance",
            "guidance": (
                "Current-year recruiting timeline information is not available in the corpus. "
                "Please verify all dates and deadlines directly with your career centre "
                "or the relevant employers."
            ),
            "timeline_highlights": [],
            "source_academic_year": corpus_version or "unknown",
            "requested_academic_year": academic_year_context or "unspecified",
            "corpus_freshness": corpus_freshness,
            "citations": [],
            "verification_required": True,
        }

    citations = [
        {"source": e.get("source_title"), "section": e.get("section"), "citation": e.get("citation")} for e in evidence
    ]
    guidance = evidence[0].get("text", "No timeline guidance available.")
    highlights = [e.get("excerpt", "") for e in evidence if e.get("excerpt")]

    return {
        "route": "timeline_guidance",
        "guidance": guidance + _VERIFY_SUFFIX,
        "timeline_highlights": highlights,
        "source_academic_year": corpus_version,
        "requested_academic_year": academic_year_context or "unspecified",
        "corpus_freshness": corpus_freshness,
        "citations": citations,
        "verification_required": True,
    }


def _build_interview_artifact(
    evidence: list[dict],
    industry_context: dict,
    corpus_version: str,
    warnings: list[str],
) -> dict:
    """Build interview preparation artifact with checklist."""
    checklist_items = industry_context.get("checklist_items", [])
    profile_name = industry_context.get("profile_name", "General")
    profile_version = industry_context.get("profile_version", "unknown")

    citations = [
        {"source": e.get("source_title"), "section": e.get("section"), "citation": e.get("citation")} for e in evidence
    ]

    return {
        "route": "interview_preparation",
        "introduction": (
            f"The following advisory interview preparation checklist is based on "
            f"{profile_name} sector guidance ({profile_version}) and general career "
            f"centre resources ({corpus_version}). "
            "Employer-specific requirements must be confirmed directly with each employer."
        ),
        "checklist_items": checklist_items,
        "citations": citations,
        "industry": profile_name,
        "profile_version": profile_version,
        "corpus_version": corpus_version,
        "advisory_notice": industry_context.get("advisory_notice", _ADVISORY_NOTICE),
    }


def _build_es_artifact(
    es_suggestions: list[dict],
    corpus_version: str,
) -> dict:
    """Build ES feedback artifact — no raw draft; suggestions only."""
    return {
        "route": "es_feedback",
        "authorship_notice": (
            "These suggestions are advisory only. You retain full authorship of your entry sheet. "
            "Do not submit AI-generated text directly; revise in your own words."
        ),
        "advisory_notice": (
            "ES feedback does not constitute a hiring assessment, score, or ranking. "
            "Your career adviser remains authoritative."
        ),
        "suggestion_count": len(es_suggestions),
        "suggestions": es_suggestions,
        "rubric_source": corpus_version,
    }


def _contains_forbidden_content(text: str) -> bool:
    tl = text.lower()
    return any(phrase in tl for phrase in _FORBIDDEN_PHRASES)


class SynthesizeNode(FunctionNode):
    """Inner node: assemble route-specific JSON response from verified retrieval/context.

    LLM may phrase text but cannot create citations, dates, scores, or employer rules.
    Forbidden content (hiring predictions, fabricated claims) is blocked before output.
    No raw student PII in any output field.
    """

    # Inner DomainWorkflowGraph node — ANONYMOUS
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        resolved_route = state.get("resolved_route", "grounded_qa")
        sanitized_query = state.get("sanitized_query", "")
        corpus_version = state.get("corpus_version", "unknown")
        corpus_freshness = state.get("corpus_freshness", "missing")
        academic_year_context = state.get("academic_year_context", "")

        evidence: list[dict] = list(from_json(state.get("retrieved_evidence"), default=[]))  # type: ignore
        industry_context: dict = dict(from_json(state.get("industry_context"), default={}))  # type: ignore
        es_suggestions: list[dict] = list(from_json(state.get("es_suggestions"), default=[]))  # type: ignore
        warnings: list = list(from_json(state.get("warnings"), default=[]))  # type: ignore

        # Build route-specific artifact
        if resolved_route == "timeline_guidance":
            artifact = _build_timeline_artifact(
                evidence, corpus_freshness, corpus_version, academic_year_context, warnings
            )
        elif resolved_route == "interview_preparation":
            artifact = _build_interview_artifact(evidence, industry_context, corpus_version, warnings)
        elif resolved_route == "es_feedback":
            artifact = _build_es_artifact(es_suggestions, corpus_version)
        else:
            artifact = _build_qa_artifact(sanitized_query, evidence, corpus_freshness, corpus_version, warnings)

        # Guardrail: block forbidden content before it reaches PostProcessNode
        artifact_text = json.dumps(artifact, ensure_ascii=False)
        if _contains_forbidden_content(artifact_text):
            warnings.append(
                "Output contained disallowed language (hiring prediction or guarantee). " "Content was blocked."
            )
            # Replace forbidden artifact with safe fallback
            artifact = {
                "route": resolved_route,
                "answer": (
                    "The generated response contained content that cannot be included "
                    "in advisory career support output. Please rephrase your query."
                ),
                "citations": [],
                "verification_next_step": "Contact career centre for authoritative guidance.",
            }

        # Extract citations for top-level state field
        citations = artifact.get("citations", [])

        emit_trace_event(
            "SynthesizeNode_synthesis_complete",
            {
                "resolved_route": resolved_route,
                "corpus_freshness": corpus_freshness,
                "corpus_version": corpus_version,
                "citation_count": len(citations),
                "warning_count": len(warnings),
                # No student query or draft content in trace
            },
            state,
        )

        return {
            "response_artifact": to_json(artifact),
            "citations": to_json(citations),
            "warnings": to_json(warnings),
            "advisory_notice": _ADVISORY_NOTICE,
            "status": AgentStatus.SUCCESS.value,
        }
