"""PreProcessNode — validate, sanitize, and PII-minimize incoming career support requests."""

from __future__ import annotations

import re
import uuid
from typing import Any, ClassVar

from framework.errors import SecurityViolationError
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

# Input limits
_QUERY_MAX_CHARS = 2000
_ES_DRAFT_MAX_CHARS = 3000

# Supported routes and academic-year format
_SUPPORTED_ROUTES = frozenset({"grounded_qa", "timeline_guidance", "interview_preparation", "es_feedback", ""})
_AY_PATTERN = re.compile(r"^AY\d{4}-\d{4}$")

# PII patterns to remove from query text and ES drafts before retrieval/trace
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(\+?\d[\d\s\-().]{7,}\d)")
_STUDENT_ID_RE = re.compile(r"\b[A-Z]{1,3}\d{5,10}\b")  # e.g. S1234567

# Student reference must be an opaque masked token (alphanum, 6-12 chars)
_MASKED_REF_RE = re.compile(r"^[A-Z0-9]{6,12}$")

# Supported target industries
_SUPPORTED_INDUSTRIES = frozenset({"finance", "it", "manufacturing", "retail", "general", ""})


def _redact_pii(text: str) -> str:
    """Remove emails, phone numbers, and student-ID patterns from text."""
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = _STUDENT_ID_RE.sub("[REDACTED_ID]", text)
    return text


class PreProcessNode(FunctionNode):
    """Outer boundary node: validate caller inputs, apply S-2 PII minimization."""

    # Cat 2 outer node — VERIFIED_EXTERNAL (S-1 trust boundary)
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2: enforce input limits and reject structurally malformed requests."""
        user_input = state.get("user_input", "")
        if not isinstance(user_input, str):
            raise SecurityViolationError("PreProcessNode S-2: user_input must be a plain string")
        if len(user_input) > _QUERY_MAX_CHARS:
            raise SecurityViolationError(f"PreProcessNode S-2: user_input exceeds {_QUERY_MAX_CHARS} chars")

        # Route hint validation
        route_hint = state.get("route_hint", "")
        if route_hint not in _SUPPORTED_ROUTES:
            raise SecurityViolationError(f"PreProcessNode S-2: unsupported route_hint '{route_hint}'")

        # ES draft length (if provided)
        es_draft = state.get("es_draft", "")
        if isinstance(es_draft, str) and len(es_draft) > _ES_DRAFT_MAX_CHARS:
            raise SecurityViolationError(f"PreProcessNode S-2: es_draft exceeds {_ES_DRAFT_MAX_CHARS} chars")

        return state

    def execute(self, state: dict) -> dict:
        user_input = state.get("user_input", "")
        input_context = state.get("input_context", {})

        if not user_input or not user_input.strip() or len(user_input.strip()) < 6:
            return {
                "status": AgentStatus.SUCCESS.value,
                "input_error_message": (
                    "No career support question was provided."
                    if not user_input or not user_input.strip()
                    else "The career support question is too short to understand."
                ),
                "input_error_guidance": [
                    "Describe the career question, target role, or interview topic you need help with.",
                    "Avoid including names, email addresses, phone numbers, or student IDs.",
                ],
            }

        # PII minimization — strip emails, phones, student IDs from query
        sanitized_query = _redact_pii(user_input.strip())

        # Academic year validation
        ay_context = state.get("academic_year_context", "")
        if ay_context and not _AY_PATTERN.match(str(ay_context)):
            ay_context = ""  # ignore malformed academic year

        # Target industry normalization
        target_industry = state.get("target_industry", "").strip().lower()
        if target_industry not in _SUPPORTED_INDUSTRIES:
            target_industry = "general"

        target_role = state.get("target_role", "").strip()

        # Route hint
        route_hint = state.get("route_hint", "").strip().lower()

        # ES draft — sanitize PII before storing (ephemeral; never in trace)
        es_draft = state.get("es_draft", "")
        sanitized_es_draft = ""
        if route_hint == "es_feedback" and isinstance(es_draft, str) and es_draft.strip():
            sanitized_es_draft = _redact_pii(es_draft.strip())

        # Masked student reference — accept opaque token or empty string
        raw_ref = state.get("student_ref", "")
        if isinstance(raw_ref, str) and _MASKED_REF_RE.match(raw_ref):
            masked_student_ref = raw_ref
        else:
            masked_student_ref = ""

        # Unique request ID for correlation (no PII)
        request_id = state.get("request_id", "") or str(uuid.uuid4())

        emit_trace_event(
            "PreProcessNode_validation_complete",
            {
                "route_hint": route_hint,
                "query_length": len(sanitized_query),
                "has_es_draft": bool(sanitized_es_draft),
                "target_industry": target_industry,
                "academic_year_context": ay_context,
                "channel": input_context.get("channel", "unknown"),
                "request_id": request_id,
            },
            state,
        )

        return {
            "sanitized_query": sanitized_query,
            "route_hint": route_hint,
            "target_role": target_role,
            "target_industry": target_industry,
            "academic_year_context": ay_context,
            "sanitized_es_draft": sanitized_es_draft,
            "masked_student_ref": masked_student_ref,
            "request_id": request_id,
            "status": AgentStatus.SUCCESS.value,
        }
