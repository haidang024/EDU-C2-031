"""Graph — outer Cat 2 AgentBaseGraph for EDU-C2-031 University Career Support Agent."""

# Cat 2 outer graph. Fixed 5-node backbone:
#   initialize → pre_process → main → post_process → finalize
# Domain complexity is in CareerSupportWorkflowGraphNode (`main` slot),
# which wraps the inner CareerSupportWorkflowGraph.
# Do NOT override add_edges() here — backbone wiring belongs to the framework.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.schemas.state import State
from src.services.error_presenter import classify

if TYPE_CHECKING:
    from src.graph.domain_workflow_graph import CareerSupportWorkflowGraph


class CareerSupportWorkflowGraphNode(GraphNode):
    """Wraps the inner CareerSupportWorkflowGraph; assigned to the outer `main` slot."""

    # Fail fast: a partial or silent career-support response is misleading
    # "handle" (not "propagate"): a propagated SubgraphError aborts the run
    # before merge_output(), so post_process never executes and the Marketplace
    # runner returns a bare RuntimeError with no reason. on_subgraph_error()
    # converts the failure into a domain field instead.
    error_strategy: ClassVar[str] = "handle"
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, llm: object | None = None, config: dict | None = None) -> None:
        super().__init__()
        self._llm = llm
        self._config: dict = dict(config or {})
        self._config["llm"] = llm

    def get_subgraph(self) -> "CareerSupportWorkflowGraph":
        """Instantiate and return the inner career-support workflow graph."""
        from src.graph.domain_workflow_graph import CareerSupportWorkflowGraph

        return CareerSupportWorkflowGraph(config=self._parent_config())

    def extract_input(self, state: AgentState) -> str:
        """Return the sanitized query to pass into inner_graph.invoke()."""
        return str(state.get("sanitized_query", state.get("user_input", "")))

    def execute(self, state: AgentState) -> dict[str, Any]:
        if state.get("input_error_message"):
            return {"status": AgentStatus.SUCCESS.value}
        return cast(dict[str, Any], super().execute(state))

    def on_subgraph_error(self, state: AgentState, error: Exception) -> dict[str, Any]:
        """Carry an inner failure as a domain field so the pipeline keeps running.

        Returning status=error here would route straight to finalize, skipping the
        post-process node; the Marketplace runner then drops `output` and the caller
        sees only "invocation did not succeed". post_process renders
        workflow_error_message into an actionable message instead.
        """
        error_log = getattr(error, "error_log", None) or []
        records = [str(e) for e in error_log if str(e).strip()]
        # Classify here; never carry the raw record forward. error_log entries
        # embed a traceback with absolute paths, source lines, and secret names,
        # and workflow_error_message is rendered to the caller by post_process.
        # The full record stays in error_log for operator/S-4 audit use.
        return {
            "status": AgentStatus.SUCCESS.value,
            "workflow_error_message": classify(records[-1] if records else str(error)),
        }

    def merge_output(self, state: AgentState, sub_result: dict) -> dict:
        """Map inner graph sub_result fields back into the outer state.

        Designed together with CareerSupportWorkflowGraph.get_output().
        Return ONLY changed keys.
        """
        return {
            "response_artifact": sub_result.get("response_artifact", ""),
            "citations": sub_result.get("citations", ""),
            "warnings": sub_result.get("warnings", ""),
            "advisory_notice": sub_result.get("advisory_notice", ""),
            "resolved_route": sub_result.get("resolved_route", ""),
            "corpus_version": sub_result.get("corpus_version", ""),
            "corpus_source": sub_result.get("corpus_source", ""),
            "corpus_freshness": sub_result.get("corpus_freshness", ""),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict:
        """Forward runtime configuration, including the optional LLM client."""
        return dict(self._config)


class Graph(AgentBaseGraph):
    """EDU-C2-031 — University Career Support Agent outer graph.

    Cat 2: outer AgentBaseGraph backbone + CareerSupportWorkflowGraphNode
    wrapping the 5-node inner career-support workflow.
    """

    @property
    def name(self) -> str:
        return "edu_c2_031_university_career_support"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        super()._validate_config()

    def register_nodes(self) -> None:
        super().register_nodes()  # injects: initialize, finalize
        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = CareerSupportWorkflowGraphNode(
            llm=self.config.get("llm"),
            config=self.config,
        )
        self._nodes["post_process"] = PostProcessNode(config=self.config)

    def get_output(self, state: AgentState) -> dict[str, Any]:
        output = cast(dict[str, Any], super().get_output(state))
        output["generation_mode"] = state.get("generation_mode")
        output["provider_error_message"] = state.get("provider_error_message")
        # Operator-facing: distinguishes fixture-backed guidance from live.
        # Deliberately not rendered into the caller-visible output.
        output["corpus_source"] = state.get("corpus_source")
        context = state.get("input_context")
        is_marketplace = isinstance(context, dict) and "conversation_history" in context
        if not is_marketplace:
            return output

        if _set_marketplace_guidance(output, state, "Career support request"):
            return output

        payload = output.get("output", output.get("formatted_output"))
        if isinstance(payload, dict):
            output["output"] = self._render_marketplace_response(payload)
        return output

    @staticmethod
    def _render_marketplace_response(payload: dict[str, Any]) -> str:
        if payload.get("error"):
            return f"Career support request failed.\n\nReason: {payload['error']}"

        response = payload.get("response")
        response = response if isinstance(response, dict) else {}
        route = payload.get("route", response.get("route", "career support"))
        lines = ["Career support guidance prepared.", "", f"Support route: {route}"]
        for key in ("answer", "guidance", "introduction", "authorship_notice"):
            if response.get(key):
                lines.extend(["", str(response[key])])

        for heading, key in (
            ("Timeline highlights", "timeline_highlights"),
            ("Interview checklist", "checklist_items"),
            ("Suggestions", "suggestions"),
        ):
            items = response.get(key)
            if isinstance(items, list) and items:
                lines.extend(["", f"{heading}:"])
                for item in items[:20]:
                    if isinstance(item, dict):
                        text = item.get("item", item.get("suggestion", item.get("criterion", "Guidance")))
                        detail = item.get("rationale")
                        lines.append(f"- {text}")
                        if detail:
                            lines.append(f"  {detail}")
                    else:
                        lines.append(f"- {item}")

        citations = payload.get("citations", response.get("citations"))
        if isinstance(citations, list) and citations:
            lines.extend(["", "Sources:"])
            for citation in citations[:10]:
                if isinstance(citation, dict):
                    label = citation.get("citation") or citation.get("source") or citation.get("title")
                    lines.append(f"- {label or 'Source'}")
                else:
                    lines.append(f"- {citation}")
        warnings = payload.get("warnings")
        if isinstance(warnings, list) and warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"- {warning}" for warning in warnings)
        notice = payload.get("advisory_notice") or response.get("advisory_notice")
        if notice:
            lines.extend(["", str(notice)])
        return "\n".join(lines)

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.


def _set_marketplace_guidance(output: dict[str, Any], state: AgentState, subject: str) -> bool:
    context = state.get("input_context")
    message = state.get("input_error_message")
    if not (isinstance(context, dict) and "conversation_history" in context and message):
        return False
    lines = [f"{subject} could not be processed.", "", f"Reason: {message}"]
    guidance = state.get("input_error_guidance")
    if isinstance(guidance, list) and guidance:
        lines.extend(["", "How to continue:"])
        lines.extend(f"- {item}" for item in guidance)
    output["output"] = "\n".join(lines)
    return True
