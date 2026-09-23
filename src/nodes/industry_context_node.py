"""IndustryContextNode — load versioned industry profile and generate advisory checklist."""

from __future__ import annotations

import json
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.schemas.state import to_json

_PROFILE_VERSION = "v2025"
_ADVISORY_NOTICE = (
    "Employer-specific requirements and eligibility criteria must be confirmed "
    "directly with each employer. This checklist reflects general guidance only."
)

_INDUSTRY_PROFILES: dict[str, dict] = {
    "finance": {
        "profile_version": _PROFILE_VERSION,
        "profile_name": "Finance / Banking",
        "checklist_items": [
            {
                "item": "Research the company's core financial products, services, and recent earnings reports.",
                "rationale": "Finance interviewers expect candidates to discuss relevant market developments.",
                "citation": "Career Centre Finance Sector Guide, v2025, §2.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Prepare for competency-based questions on analytical thinking and risk awareness.",
                "rationale": "Finance roles emphasise quantitative and risk-management skills.",
                "citation": "Career Centre Finance Sector Guide, v2025, §3.2",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Review financial regulations relevant to the role (e.g. banking act, FSA guidelines) at a conceptual level.",
                "rationale": "Awareness of regulatory environment demonstrates sector readiness.",
                "citation": "Career Centre Finance Sector Guide, v2025, §3.3",
                "context_version": _PROFILE_VERSION,
                "safety_notice": "Verify current regulations; requirements change. Confirm specifics with the employer.",
            },
            {
                "item": "Dress in formal business attire unless the employer specifies otherwise.",
                "rationale": "Finance sector typically expects conservative dress code.",
                "citation": "Career Centre Interview Preparation Guide, AY2025-2026, §4.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": "Confirm dress code with each employer.",
            },
            {
                "item": "Prepare a concise self-introduction covering academic background and motivation for finance.",
                "rationale": "Jiko shoukai is standard in Japanese corporate interviews.",
                "citation": "Career Centre Interview Preparation Guide, AY2025-2026, §2.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
        ],
    },
    "it": {
        "profile_version": _PROFILE_VERSION,
        "profile_name": "IT / Technology",
        "checklist_items": [
            {
                "item": "Research the company's main technology products, recent releases, and tech stack (where publicly available).",
                "rationale": "IT interviewers value genuine product/technology interest.",
                "citation": "Career Centre IT Sector Guide, v2025, §2.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Prepare examples of technical projects with clear problem-solution-outcome structure.",
                "rationale": "Concrete evidence of technical skill is expected.",
                "citation": "Career Centre IT Sector Guide, v2025, §3.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Be ready to discuss collaborative development practices (version control, code review, agile/scrum).",
                "rationale": "Team engineering practices are core to IT roles.",
                "citation": "Career Centre IT Sector Guide, v2025, §3.2",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Prepare for logic/algorithm questions at entry level if the role is engineering-focused.",
                "rationale": "Technical screening varies by role; confirm format with each employer.",
                "citation": "Career Centre IT Sector Guide, v2025, §3.3",
                "context_version": _PROFILE_VERSION,
                "safety_notice": "Specific technical screening format must be confirmed with each employer.",
            },
            {
                "item": "Prepare a concise self-introduction highlighting technical background and motivation for IT.",
                "rationale": "Jiko shoukai is standard in Japanese corporate interviews.",
                "citation": "Career Centre Interview Preparation Guide, AY2025-2026, §2.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
        ],
    },
    "manufacturing": {
        "profile_version": _PROFILE_VERSION,
        "profile_name": "Manufacturing",
        "checklist_items": [
            {
                "item": "Research the company's key products, manufacturing processes, and quality certifications.",
                "rationale": "Manufacturing candidates are expected to understand core production concepts.",
                "citation": "Career Centre Manufacturing Sector Guide, v2025, §2.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Prepare examples demonstrating attention to detail, process improvement, or team coordination.",
                "rationale": "Quality and continuous improvement are central to manufacturing culture.",
                "citation": "Career Centre Manufacturing Sector Guide, v2025, §3.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Be ready to discuss safety awareness and compliance mindset.",
                "rationale": "Safety culture is fundamental in manufacturing environments.",
                "citation": "Career Centre Manufacturing Sector Guide, v2025, §3.2",
                "context_version": _PROFILE_VERSION,
                "safety_notice": "Specific safety requirements vary by facility; confirm with each employer.",
            },
            {
                "item": "Prepare a concise self-introduction covering academic background and motivation for manufacturing.",
                "rationale": "Jiko shoukai is standard in Japanese corporate interviews.",
                "citation": "Career Centre Interview Preparation Guide, AY2025-2026, §2.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Research the company's global supply chain and recent sustainability initiatives if publicly disclosed.",
                "rationale": "Shows broader business awareness beyond production floor.",
                "citation": "Career Centre Manufacturing Sector Guide, v2025, §2.2",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
        ],
    },
    "retail": {
        "profile_version": _PROFILE_VERSION,
        "profile_name": "Retail / Consumer",
        "checklist_items": [
            {
                "item": "Research the company's key product lines, target customers, and recent store/online strategy.",
                "rationale": "Retail candidates should demonstrate genuine brand and customer interest.",
                "citation": "Career Centre Retail Sector Guide, v2025, §2.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Prepare examples of customer-facing experience and service orientation.",
                "rationale": "Customer service values are central to retail culture.",
                "citation": "Career Centre Retail Sector Guide, v2025, §3.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Be ready to discuss teamwork in high-pressure or seasonal peak environments.",
                "rationale": "Retail operations depend on flexible teamwork during busy periods.",
                "citation": "Career Centre Retail Sector Guide, v2025, §3.2",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Prepare a concise self-introduction with clear motivation for the retail/consumer sector.",
                "rationale": "Jiko shoukai is standard in Japanese corporate interviews.",
                "citation": "Career Centre Interview Preparation Guide, AY2025-2026, §2.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Research the company's omnichannel strategy and any recent digital transformation initiatives.",
                "rationale": "Retail is rapidly evolving; showing awareness of digital shift demonstrates engagement.",
                "citation": "Career Centre Retail Sector Guide, v2025, §2.2",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
        ],
    },
    "general": {
        "profile_version": _PROFILE_VERSION,
        "profile_name": "General (cross-sector)",
        "checklist_items": [
            {
                "item": "Research the company's business model, products/services, and recent news before the interview.",
                "rationale": "All interviews benefit from demonstrated company knowledge.",
                "citation": "Career Centre Interview Preparation Guide, AY2025-2026, §2.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Prepare a concise self-introduction (jiko shoukai) covering background and motivation.",
                "rationale": "Self-introduction is expected in virtually all Japanese corporate interviews.",
                "citation": "Career Centre Interview Preparation Guide, AY2025-2026, §2.2",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Prepare 2-3 concrete examples of past experience with clear problem-action-result structure.",
                "rationale": "Behavioural examples are a universal interview staple.",
                "citation": "Career Centre Interview Preparation Guide, AY2025-2026, §3.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
            {
                "item": "Dress in standard business attire unless the employer specifies otherwise.",
                "rationale": "Business formal remains the default expectation in Japan.",
                "citation": "Career Centre Interview Preparation Guide, AY2025-2026, §4.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": "Confirm dress code with each employer.",
            },
            {
                "item": "Prepare thoughtful questions to ask the interviewer about the role and team.",
                "rationale": "Questions demonstrate interest and preparation.",
                "citation": "Career Centre Interview Preparation Guide, AY2025-2026, §5.1",
                "context_version": _PROFILE_VERSION,
                "safety_notice": None,
            },
        ],
    },
}


class IndustryContextNode(FunctionNode):
    """Inner node: load industry profile and generate advisory interview checklist.

    Only active for 'interview_preparation' and 'es_feedback' routes.
    Unknown industries degrade to general guidance — no fabrication.
    No hiring-success prediction or employer-specific guarantee in output.
    """

    # Inner DomainWorkflowGraph node — ANONYMOUS
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        resolved_route = state.get("resolved_route", "grounded_qa")

        # Only generate industry context for routes that use it
        if resolved_route not in {"interview_preparation", "es_feedback"}:
            emit_trace_event(
                "IndustryContextNode_skipped",
                {"resolved_route": resolved_route, "reason": "route_does_not_use_industry_context"},
                state,
            )
            return {"industry_context": to_json({})}

        target_industry = state.get("target_industry", "general").strip().lower()
        profile = _INDUSTRY_PROFILES.get(target_industry, _INDUSTRY_PROFILES["general"])
        used_industry = target_industry if target_industry in _INDUSTRY_PROFILES else "general"

        warnings: list = []
        if used_industry == "general" and target_industry and target_industry != "general":
            warnings.append(
                f"No specific industry profile found for '{target_industry}'. "
                "Showing general interview preparation guidance."
            )

        context_out = {
            "profile_name": profile["profile_name"],
            "profile_version": profile["profile_version"],
            "industry": used_industry,
            "checklist_items": profile["checklist_items"],
            "advisory_notice": _ADVISORY_NOTICE,
        }

        existing_warnings: list = []
        try:
            existing_warnings = json.loads(state.get("warnings", "[]") or "[]")
        except (TypeError, ValueError):
            existing_warnings = []

        emit_trace_event(
            "IndustryContextNode_profile_loaded",
            {
                "industry": used_industry,
                "profile_version": profile["profile_version"],
                "checklist_item_count": len(profile["checklist_items"]),
                "resolved_route": resolved_route,
            },
            state,
        )

        return {
            "industry_context": to_json(context_out),
            "warnings": to_json(existing_warnings + warnings),
        }
