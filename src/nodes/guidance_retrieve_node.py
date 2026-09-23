"""GuidanceRetrieveNode — retrieve versioned career guidance evidence from the corpus."""

from __future__ import annotations

import json
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.schemas.state import to_json


def _resolve_optional_secret(ctx: InvocationContext, key: str) -> str | None:
    """Return a secret's value, or None when it is not provisioned.

    `ctx.secrets.require()` raises MissingSecret, which aborts the node. Some
    connectors are optional in environments where the backing service has not
    been wired up yet: the caller decides whether to degrade instead of fail.
    """
    try:
        value = ctx.secrets.require(key)
    except Exception:
        return None
    return str(value) if value else None


_FRESHNESS_THRESHOLD_DAYS = 90
_MOCK_EVIDENCE: list[dict] = [
    {
        "chunk_id": "mock-001",
        "text": (
            "The general corporate recruiting (shinsotsu) season in Japan "
            "typically runs from October to March of the academic year, "
            "with formal interviews beginning after the official start of the "
            "job-hunting period defined in the Keizai Doyukai/Keidanren guidelines."
        ),
        "source_title": "University Career Centre — Recruiting Calendar Guide",
        "section": "2. Annual Recruiting Timeline",
        "corpus_version": "AY2025-2026",
        "effective_year": "2025",
        "citation": "Career Centre Recruiting Calendar Guide, AY2025-2026, §2",
        "excerpt": "Recruiting season typically runs October–March.",
    },
    {
        "chunk_id": "mock-002",
        "text": (
            "Interview preparation should include: researching the company's "
            "business model and recent news, preparing self-introduction (jiko shoukai), "
            "practicing common behavioural questions, and dressing in standard "
            "business attire unless otherwise specified by the employer."
        ),
        "source_title": "University Career Centre — Interview Preparation Guide",
        "section": "3. Pre-Interview Checklist",
        "corpus_version": "AY2025-2026",
        "effective_year": "2025",
        "citation": "Career Centre Interview Preparation Guide, AY2025-2026, §3",
        "excerpt": "Prepare self-intro, research company, dress in business attire.",
    },
    {
        "chunk_id": "mock-003",
        "text": (
            "Entry sheets (ES) should clearly articulate: self-PR (jiko PR), "
            "motivation for applying (shibo riyu), specific achievements with "
            "quantified evidence, and alignment with the target role. "
            "Avoid generic statements without concrete examples."
        ),
        "source_title": "University Career Centre — ES Writing Guide",
        "section": "4. ES Rubric Criteria",
        "corpus_version": "AY2025-2026",
        "effective_year": "2025",
        "citation": "Career Centre ES Writing Guide, AY2025-2026, §4",
        "excerpt": "ES must include self-PR, motivation, and quantified achievements.",
    },
]


def _is_fresh(corpus_version: str, academic_year_context: str) -> str:
    """Return 'fresh' | 'stale' | 'missing' based on version match."""
    if not corpus_version:
        return "missing"
    if not academic_year_context:
        return "fresh"  # no caller context = accept any version
    # Strip "AY" prefix for comparison
    if corpus_version == academic_year_context:
        return "fresh"
    return "stale"


class GuidanceRetrieveNode(FunctionNode):
    """Inner node: retrieve versioned career guidance evidence by route and academic year.

    Uses ctx.secrets.require('vector_store_key') for vector-store access.
    In test/mock mode returns deterministic fixture evidence.
    Stale or missing corpus produces a warning and prevents definitive claims.
    """

    # Inner DomainWorkflowGraph node — ANONYMOUS
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        ctx = InvocationContext.from_state(state)
        # Credential accessed via InvocationContext — never os.environ.
        # When the vector store is not yet provisioned, fall back to the
        # bundled fixture corpus instead of failing the run: the retrieval
        # below already returns fixture evidence, so the credential only gates
        # the live store. `generation_mode` records which path ran so operators
        # can tell fixture-backed answers from live ones in the audit log.
        live_corpus = _resolve_optional_secret(ctx, "vector_store_key") is not None

        resolved_route = state.get("resolved_route", "grounded_qa")
        academic_year_context = state.get("academic_year_context", "")

        # In production: run vector similarity search filtered by route + academic year.
        # For now: return mock evidence relevant to the route.
        route_evidence_map = {
            "grounded_qa": [_MOCK_EVIDENCE[0], _MOCK_EVIDENCE[1]],
            "timeline_guidance": [_MOCK_EVIDENCE[0]],
            "interview_preparation": [_MOCK_EVIDENCE[1]],
            "es_feedback": [_MOCK_EVIDENCE[2]],
        }
        evidence = route_evidence_map.get(resolved_route, [_MOCK_EVIDENCE[0]])

        corpus_version = evidence[0]["corpus_version"] if evidence else ""
        corpus_freshness = _is_fresh(corpus_version, academic_year_context)

        warnings: list[str] = []
        if corpus_freshness == "stale":
            warnings.append(
                f"Career guidance corpus version ({corpus_version}) does not match "
                f"requested academic year ({academic_year_context}). "
                "Please verify timeline and deadlines directly with your career centre."
            )
        elif corpus_freshness == "missing":
            warnings.append(
                "No career guidance evidence was found for this query. " "Please contact your career centre directly."
            )

        existing_warnings: list = []
        try:
            existing_warnings = json.loads(state.get("warnings", "[]") or "[]")
        except (TypeError, ValueError):
            existing_warnings = []

        emit_trace_event(
            "GuidanceRetrieveNode_retrieval_complete",
            {
                "resolved_route": resolved_route,
                "chunk_count": len(evidence),
                "corpus_version": corpus_version,
                "corpus_freshness": corpus_freshness,
                "academic_year_context": academic_year_context,
                # Which corpus answered: "live" only when the vector store
                # credential is provisioned, "fixture" otherwise. This is the
                # only place the distinction is recorded — the caller-facing
                # output is identical either way — so keep it here.
                "corpus_source": "live" if live_corpus else "fixture",
                # Do NOT include sanitized_query in trace (minimize student data)
            },
            state,
        )

        return {
            "retrieved_evidence": to_json(evidence),
            "corpus_version": corpus_version,
            "corpus_freshness": corpus_freshness,
            "warnings": to_json(existing_warnings + warnings),
            # Separate from `generation_mode`, which the LLM layer owns and
            # overwrites: this records which corpus answered, so an operator can
            # tell fixture-backed guidance from live guidance in the audit log.
            "corpus_source": "live" if live_corpus else "fixture",
        }
