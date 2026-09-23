"""Regression tests for invocation-scoped Azure OpenAI resolution."""

import sys
from types import SimpleNamespace

from framework.schemas.invocation_context import InvocationContext


def test_resolve_azure_llm_uses_invocation_secrets(monkeypatch):
    captured = {}
    values = {
        "AZURE_OPENAI_API_KEY": "test-key",
        "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
        "AZURE_OPENAI_DEPLOYMENT": "test-deployment",
    }

    class Secrets:
        def require(self, key):
            return values[key]

    class Client:
        def __init__(self, config):
            captured.update(config)

    context = type("Ctx", (), {"secrets": Secrets()})()
    monkeypatch.setattr(InvocationContext, "from_state", classmethod(lambda cls, state: context))
    monkeypatch.setitem(
        sys.modules,
        "shared.services.llm.azure_openai_client",
        SimpleNamespace(AzureOpenAIClient=Client),
    )

    from src.services.llm_runtime import resolve_azure_llm

    resolve_azure_llm({}, timeout_s=12.5, max_retry=1)

    assert captured["api_key"] == "test-key"
    assert captured["azure_endpoint"] == values["AZURE_OPENAI_ENDPOINT"]
    assert captured["azure_deployment"] == "test-deployment"
    assert captured["timeout"] == 12.5
    assert captured["max_retries"] == 1


def test_request_advisory_falls_back_on_provider_error():
    class BrokenClient:
        def complete(self, messages):
            raise RuntimeError("provider unavailable")

    from src.services.llm_runtime import request_advisory

    state = {}
    assert request_advisory(state, "review", BrokenClient()) is None
    assert state["generation_mode"] == "deterministic_fallback"
    assert "failed or timed out" in state["provider_error_message"]


def test_complete_text_supports_an_injected_client():
    class Client:
        def complete(self, messages):
            assert messages[0]["role"] == "system"
            return {"content": "synthetic response"}

    from src.services.llm_runtime import complete_text

    assert complete_text({}, [{"role": "system", "content": "review"}], Client()) == "synthetic response"


def test_graph_exposes_provider_status():
    from src.graph.graph import Graph

    graph = Graph(config={})
    output = graph.get_output(
        {
            "status": "success",
            "formatted_output": "ok",
            "generation_mode": "deterministic_fallback",
            "provider_error_message": "provider unavailable",
        }
    )

    assert output["generation_mode"] == "deterministic_fallback"
    assert output["provider_error_message"] == "provider unavailable"
