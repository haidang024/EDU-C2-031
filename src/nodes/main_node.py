"""MainNode — Cat 2 outer main slot; replaced by CareerSupportWorkflowGraphNode in graph.py."""

# In Cat 2, the outer `main` slot is occupied by CareerSupportWorkflowGraphNode (a GraphNode),
# not this FunctionNode. This file is retained for structural completeness and import tests.
# Do NOT use MainNode directly in graph.py register_nodes().

from __future__ import annotations

from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event


class MainNode(FunctionNode):
    """Cat 2 main slot placeholder — superseded by CareerSupportWorkflowGraphNode in the outer graph."""

    # Cat 2 inner context — not used in outer graph; kept ANONYMOUS for correctness
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        emit_trace_event(
            "MainNode_execute_called",
            {"note": "Cat 2 main logic is in CareerSupportWorkflowGraphNode"},
            state,
        )
        return {
            "status": AgentStatus.ERROR.value,
            "error_log": ["MainNode: not used in Cat 2; use CareerSupportWorkflowGraphNode via graph.py"],
        }
