"""Standalone HTTP adapter for EDU-C2-031."""

import os
import secrets
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.context import bound_secrets
from framework.utils.config_loader import load_config
from shared.secrets import factory as secrets_factory
from shared.secrets.chained_provider import ChainedSecretProvider
from shared.secrets.env_provider import EnvProvider
from src.graph.graph import Graph

app = FastAPI(title="EDU-C2-031 University Career Support Agent")

# Match AgentRegistry's runtime-config loading contract on the standalone path.
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
_config = load_config(str(_CONFIG_PATH)) if _CONFIG_PATH.exists() else {}

# The provider is created before Graph so optional provider clients can be
# threaded through graph configuration. The provisional STG smoke path uses a
# clearly non-production provider because its retrieval corpus is deterministic;
# normal runtime always delegates to the configured shared provider.
if os.environ.get("STG_MOCK_MODE", "").lower() in {"1", "true", "yes"}:
    from shared.secrets.inmemory_provider import InMemoryProvider

    _domain_secrets_provider = InMemoryProvider(
        values={"vector_store_key": "stg-mock-vector-store"},
        namespace="EDU",
        agent_name="University Career Support Agent",
    )
else:
    _domain_secrets_provider = secrets_factory(
        namespace="agent1000",
        agent_name="EDU-C2-031",
    )
_namespace = "agent1000"
_secrets_provider = ChainedSecretProvider(
    EnvProvider(namespace=_namespace, agent_name="EDU-C2-031"),
    _domain_secrets_provider,
)

_llm: None = None  # Compatibility seam; Azure clients are invocation-scoped.
agent = Graph(config=_config)

# HITL or memory requires a checkpointer for standalone invocation, matching the
# registry compile path. This agent currently enables neither by default.
_hitl_enabled = agent.config.get("hitl", {}).get("enabled", False)
_needs_checkpointer = agent.config.get("memory_enabled") or _hitl_enabled
agent.compile(checkpointer=MemorySaver() if _needs_checkpointer else None)
agent.provision_secrets(_secrets_provider)


class InvokeRequest(BaseModel):
    input: str
    session_id: str = ""


def _bearer_matches(supplied: str, expected: str) -> bool:
    """Compare bearer credentials in constant time, including non-ASCII input."""
    return secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode())


def _resolve_standalone_trust(
    current: TrustLevel,
    authorization: str,
    invoke_auth_token: str | None,
    internal_runner_token: str | None,
) -> TrustLevel:
    """Authenticate callers without allowing an external token to become INTERNAL."""
    if current is not TrustLevel.ANONYMOUS:
        return current
    if internal_runner_token and _bearer_matches(authorization, internal_runner_token):
        return TrustLevel.INTERNAL
    if invoke_auth_token and _bearer_matches(authorization, invoke_auth_token):
        return TrustLevel.VERIFIED_EXTERNAL
    if internal_runner_token or invoke_auth_token:
        raise HTTPException(status_code=401, detail="Token is invalid or expired.")
    return TrustLevel.ANONYMOUS


@app.post("/invoke")
async def invoke(req: InvokeRequest, request: Request) -> dict[str, object]:
    trust = _resolve_standalone_trust(
        getattr(request.state, "trust_level", TrustLevel.ANONYMOUS),
        request.headers.get("authorization", ""),
        os.environ.get("INVOKE_AUTH_TOKEN"),
        os.environ.get("STG_INTERNAL_RUNNER_TOKEN"),
    )
    with bound_secrets(agent._secrets_provider):
        ctx = InvocationContext(
            session_id=req.session_id or str(uuid4()),
            caller_trust_level=trust,
            caller_id=getattr(request.state, "caller_id", ""),
        )
        return cast(
            dict[str, object],
            agent.invoke(req.input, ctx=ctx, input_context={"raw": req.input}),
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": "EDU-C2-031"}
