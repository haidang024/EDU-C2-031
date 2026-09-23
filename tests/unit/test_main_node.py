# EDU-C2-031 — Unit Tests: MainNode (Cat 2 placeholder; actual logic in CareerSupportWorkflowGraphNode)

import inspect

import pytest
from framework.schemas.agent_status import AgentStatus
from src.nodes.main_node import MainNode


class TestMainNode:
    """Unit tests for the Cat 2 MainNode placeholder."""

    def setup_method(self):
        self.node = MainNode()

    def test_execute_method_signature(self):
        """Node contract: Node must implement execute(state), not _invoke_impl.

        Cat 2 MainNode is a structural placeholder. The contract still applies.
        """
        assert hasattr(MainNode, "execute"), "MainNode must implement execute()"
        sig = inspect.signature(MainNode.execute)
        params = list(sig.parameters.keys())
        assert len(params) >= 2, (
            f"execute() must accept (self, state), got params: {params}"
        )
        assert params[1] == "state", (
            f"Second parameter must be 'state', got '{params[1]}'"
        )
        assert "_invoke_impl" not in MainNode.__dict__, (
            "_invoke_impl() must not be defined in MainNode — use execute() instead"
        )

    def test_execute_returns_error_status(self):
        """Cat 2 MainNode placeholder: execute() returns ERROR (not used in outer graph)."""
        state = {
            "caller_trust_level": 0,
            "node_history": [],
            "error_log": [],
        }
        result = self.node.execute(state)
        # In Cat 2, MainNode is superseded by CareerSupportWorkflowGraphNode
        assert result["status"] == AgentStatus.ERROR.value
