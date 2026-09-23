"""PostProcessNode — apply S-3 redaction and format final output for the caller."""

from __future__ import annotations

import json
import re
from typing import Any, ClassVar

from framework.errors import SecurityViolationError
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.error_presenter import classify, present
from src.services.llm_runtime import provider_metadata, request_advisory
from src.schemas.state import from_json

# PII patterns that must not appear in output
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Phone pattern: must include separator (space, hyphen, parens) to avoid UUID/ID false positives
_PHONE_RE = re.compile(r"\+?\d[\d]{1,3}[-\s()]\d{2,4}[-\s]\d{3,4}[-\s]?\d{4}")

# Phrases that constitute definitive employment outcome claims — must not pass S-3
_FORBIDDEN_OUTPUT_PHRASES = [
    "you will be hired",
    "you are guaranteed",
    "guaranteed employment",
    "you will get the job",
    "certain to pass",
    "you will succeed",
    "hiring probability",
]

# Fallback shown when the run errored but error_log is empty.
_GENERIC_ERROR = "The career support guidance could not be completed because of a temporary internal error."

_ADVISORY_NOTICE = (
    "Advisory career-centre support only. "
    "Advisers and employers remain authoritative for eligibility, requirements, and deadlines."
)


class PostProcessNode(FunctionNode):
    """Outer boundary node: apply S-3 output redaction and build the final caller response."""

    # Cat 2 outer node — VERIFIED_EXTERNAL
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, config: dict | None = None) -> None:
        super().__init__()
        self._config: dict = config or {}
        self._llm: object | None = self._config.get("llm")

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        """S-3: block PII leakage, fabricated claims, and biased employment language."""
        formatted = result.get("formatted_output", {})
        output_str = json.dumps(formatted, ensure_ascii=False) if isinstance(formatted, dict) else str(formatted)

        # Block email/phone PII in output
        if _EMAIL_RE.search(output_str):
            raise SecurityViolationError(
                "PostProcessNode S-3: formatted_output contains an email address — PII must not appear in output"
            )
        if _PHONE_RE.search(output_str):
            raise SecurityViolationError(
                "PostProcessNode S-3: formatted_output contains a phone number — PII must not appear in output"
            )

        # Block definitive employment outcome language
        output_lower = output_str.lower()
        for phrase in _FORBIDDEN_OUTPUT_PHRASES:
            if phrase in output_lower:
                raise SecurityViolationError(
                    f"PostProcessNode S-3: formatted_output contains disallowed employment outcome phrase: '{phrase}'"
                )

        return result

    def execute(self, state: dict) -> dict:
        if state.get("input_error_message"):
            message = str(state["input_error_message"])
            return {
                "status": AgentStatus.SUCCESS.value,
                "result": message,
                "formatted_output": message,
            }

        # Inner workflow failed (e.g. an unavailable credential or connector).
        # Report it on a SUCCESS envelope: the Marketplace runner only forwards
        # `output` when status == "success", so status=error would leave the
        # caller with no reason at all.
        if state.get("workflow_error_message"):
            # present() re-classifies defensively: workflow_error_message is
            # already classified by on_subgraph_error(), but any other writer of
            # this field must not be able to route a raw traceback to the caller.
            message = present(
                str(state["workflow_error_message"]),
                request_id=str(state.get("request_id", "")),
            )
            return {
                "status": AgentStatus.SUCCESS.value,
                "result": message,
                "formatted_output": message,
            }

        request_advisory(
            state,
            "Review the EDU-C2-031 workflow result for completeness.",
            self._llm,
            timeout_s=float(self._config.get("timeout_s", 30.0)),
            max_retry=int(self._config.get("max_retry", 3)),
        )
        metadata = provider_metadata(state)
        # Short-circuit on upstream error
        if state.get("status") == AgentStatus.ERROR.value:
            error_log = state.get("error_log") or []
            return {
                "formatted_output": {
                    # Classified reason only — the raw entry carries a traceback.
                    "error": classify(str(error_log[-1])) if error_log else _GENERIC_ERROR,
                    "request_id": state.get("request_id", ""),
                    "advisory_notice": _ADVISORY_NOTICE,
                },
                "status": AgentStatus.ERROR.value,
                **metadata,
            }

        response_artifact = from_json(state.get("response_artifact"), default={})
        citations = from_json(state.get("citations"), default=[])
        warnings = from_json(state.get("warnings"), default=[])
        advisory_notice = state.get("advisory_notice") or _ADVISORY_NOTICE
        resolved_route = state.get("resolved_route", "grounded_qa")
        corpus_version = state.get("corpus_version", "unknown")
        request_id = state.get("request_id", "")

        formatted_output = {
            "route": resolved_route,
            "response": response_artifact,
            "citations": citations,
            "warnings": warnings,
            "advisory_notice": advisory_notice,
            "corpus_version": corpus_version,
            "request_id": request_id,
        }

        emit_trace_event(
            "PostProcessNode_output_formatted",
            {
                "resolved_route": resolved_route,
                "citation_count": len(citations) if isinstance(citations, list) else 0,
                "warning_count": len(warnings) if isinstance(warnings, list) else 0,
                "corpus_version": corpus_version,
                "request_id": request_id,
                # No student content in trace
            },
            state,
        )

        return {
            "formatted_output": formatted_output,
            "status": AgentStatus.SUCCESS.value,
            **metadata,
        }
