"""Prove optional server LLM construction and standalone trust mapping."""

import importlib
import sys
import types


class TestServerBootsWithoutAnthropicKey:
    def test_server_imports_and_app_constructs_with_no_key(self, monkeypatch):
        from shared.secrets.inmemory_provider import InMemoryProvider

        monkeypatch.delenv("STG_MOCK_MODE", raising=False)
        monkeypatch.setattr(
            "shared.secrets.factory",
            lambda namespace, agent_name: InMemoryProvider({}),
        )

        import src.api.server as server

        importlib.reload(server)

        assert server.app is not None
        assert server._llm is None
        assert server.agent._nodes["main"]._llm is None


class TestServerConstructsLlmWithKey:
    def test_llm_is_constructed_and_reaches_composite_main_node(self, monkeypatch):
        from shared.secrets.inmemory_provider import InMemoryProvider

        monkeypatch.delenv("STG_MOCK_MODE", raising=False)
        class FakeAnthropicClient:
            def __init__(self, config):
                self.config = config

        fake_module = types.ModuleType("shared.services.llm.anthropic_client")
        fake_module.AnthropicClient = FakeAnthropicClient
        monkeypatch.setitem(
            sys.modules,
            "shared.services.llm.anthropic_client",
            fake_module,
        )
        monkeypatch.setattr(
            "shared.secrets.factory",
            lambda namespace, agent_name: InMemoryProvider(
                {"ANTHROPIC_API_KEY": "dummy-test-key"}
            ),
        )

        import src.api.server as server

        importlib.reload(server)

        assert server._llm is None
        assert server.agent._nodes["main"]._llm is server._llm
        assert server.agent._nodes["main"]._parent_config()["llm"] is server._llm


class TestStandaloneTrustPromotion:
    def test_external_bearer_never_promotes_to_internal(self):
        import src.api.server as server
        from framework.schemas.trust_level import TrustLevel

        assert server._resolve_standalone_trust(
            TrustLevel.ANONYMOUS, "Bearer external", "external", "runner"
        ) is TrustLevel.VERIFIED_EXTERNAL

    def test_runner_bearer_promotes_to_internal(self):
        import src.api.server as server
        from framework.schemas.trust_level import TrustLevel

        assert server._resolve_standalone_trust(
            TrustLevel.ANONYMOUS, "Bearer runner", "external", "runner"
        ) is TrustLevel.INTERNAL

    def test_wrong_or_missing_bearer_is_rejected_when_auth_is_enabled(self):
        import pytest
        import src.api.server as server
        from fastapi import HTTPException
        from framework.schemas.trust_level import TrustLevel

        for authorization in ("", "Bearer wrong"):
            with pytest.raises(HTTPException) as exc:
                server._resolve_standalone_trust(
                    TrustLevel.ANONYMOUS,
                    authorization,
                    "external",
                    "runner",
                )
            assert exc.value.status_code == 401
