"""CareerSupportWorkflowGraph — inner 5-node domain pipeline for EDU-C2-031."""

# Inner graph for the Cat 2 career support workflow.
# Instantiated by CareerSupportWorkflowGraphNode.get_subgraph() in graph.py.
# Inherits BaseGraph for fully custom 5-node topology.
#
# Pipeline:
#   START → intent_classify → guidance_retrieve → industry_context
#         → es_feedback → synthesize → END
#
# All nodes are ANONYMOUS (trust verified at outer PreProcessNode boundary).

from __future__ import annotations

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from src.nodes.es_feedback_node import ESFeedbackNode
from src.nodes.guidance_retrieve_node import GuidanceRetrieveNode
from src.nodes.industry_context_node import IndustryContextNode
from src.nodes.intent_classify_node import IntentClassifyNode
from src.nodes.synthesize_node import SynthesizeNode
from src.schemas.state import State


class CareerSupportWorkflowGraph(BaseGraph):
    """Inner career-support domain workflow graph for EDU-C2-031.

    Pipeline (linear; all 5 nodes always execute in order — each is route-aware
    and no-ops for irrelevant routes):
        START → intent_classify → guidance_retrieve → industry_context
              → es_feedback → synthesize → END
    """

    @property
    def name(self) -> str:
        return "edu_c2_031_career_support_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        """No mandatory config keys for the inner graph (outer config forwarded as needed)."""
        pass

    def register_nodes(self) -> None:
        """Register all 5 domain nodes. No super() — BaseGraph.register_nodes() is abstract."""
        self._nodes["intent_classify"] = IntentClassifyNode()
        self._nodes["guidance_retrieve"] = GuidanceRetrieveNode()
        self._nodes["industry_context"] = IndustryContextNode()
        self._nodes["es_feedback"] = ESFeedbackNode()
        self._nodes["synthesize"] = SynthesizeNode()

    def add_edges(self) -> None:
        """Wire the linear topology. Every registered node is reachable from START."""
        self._sg.add_edge(START, "intent_classify")
        self._sg.add_edge("intent_classify", "guidance_retrieve")
        self._sg.add_edge("guidance_retrieve", "industry_context")
        self._sg.add_edge("industry_context", "es_feedback")
        self._sg.add_edge("es_feedback", "synthesize")
        self._sg.add_edge("synthesize", END)

    def route(self, state: AgentState) -> str:
        """Required by BaseGraph ABC; this linear graph has no conditional edges."""
        return str(END if state.get("status") == AgentStatus.ERROR.value else "synthesize")

    def get_output(self, state: AgentState) -> dict:
        """Shape the sub_result dict returned to CareerSupportWorkflowGraphNode.merge_output()."""
        return {
            "response_artifact": state.get("response_artifact", ""),
            "citations": state.get("citations", ""),
            "warnings": state.get("warnings", ""),
            "advisory_notice": state.get("advisory_notice", ""),
            "resolved_route": state.get("resolved_route", ""),
            "corpus_version": state.get("corpus_version", ""),
            "corpus_source": state.get("corpus_source", ""),
            "corpus_freshness": state.get("corpus_freshness", ""),
            "status": state.get("status"),
            "error_log": state.get("error_log", []),
        }
