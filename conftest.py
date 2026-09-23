"""conftest.py — framework stubs for EDU-C2-031; test isolation without real SDK."""

from __future__ import annotations

import os
import re
import sys
import types
from enum import Enum

ROOT = os.path.abspath(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _register_module(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


# ── HTTP adapter stubs ───────────────────────────────────────────────────────
fastapi = _register_module("fastapi")


class FastAPI:
    def __init__(self, title: str = "") -> None:
        self.title = title

    def post(self, _path: str):
        return lambda func: func

    def get(self, _path: str):
        return lambda func: func


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = "") -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class Request:
    pass


fastapi.FastAPI = FastAPI
fastapi.HTTPException = HTTPException
fastapi.Request = Request

pydantic = _register_module("pydantic")


class BaseModel:
    pass


pydantic.BaseModel = BaseModel


# ── langgraph stubs (register BEFORE any src imports that use langgraph) ──────
langgraph = _register_module("langgraph")
langgraph_graph = _register_module("langgraph.graph")
langgraph_graph.START = "START"
langgraph_graph.END = "END"
langgraph.graph = langgraph_graph

langgraph_types = _register_module("langgraph.types")
langgraph_types.interrupt = lambda value: value   # HITL stub — returns immediately
langgraph.types = langgraph_types

langgraph_checkpoint = _register_module("langgraph.checkpoint")
langgraph_checkpoint_memory = _register_module("langgraph.checkpoint.memory")


class MemorySaver:
    pass


langgraph_checkpoint_memory.MemorySaver = MemorySaver
langgraph_checkpoint.memory = langgraph_checkpoint_memory
langgraph.checkpoint = langgraph_checkpoint

# ── AgentStatus (str, Enum) ───────────────────────────────────────────────────
class AgentStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    HITL = "hitl"


# ── TrustLevel (int, Enum) ────────────────────────────────────────────────────
class TrustLevel(int, Enum):
    ANONYMOUS = 0
    VERIFIED_EXTERNAL = 1
    INTERNAL = 2


# ── Exceptions ────────────────────────────────────────────────────────────────
class SecurityViolationError(Exception):
    pass


class ConfigError(Exception):
    pass


# ── AgentState ────────────────────────────────────────────────────────────────
class AgentState(dict):
    pass


# ── emit_trace_event (3-arg form) ─────────────────────────────────────────────
def emit_trace_event(event_type: str, payload: dict, state: dict | None = None) -> None:
    pass   # no-op stub; PB-6 monkeypatches base_node_mod.emit_trace_event


# ── framework.nodes.base_node (required by PB-6 test monkeypatching) ──────────
base_node_mod = _register_module("framework.nodes.base_node")
base_node_mod.emit_trace_event = emit_trace_event


class BaseNode:
    required_trust_level = None

    # Real FunctionNode takes NO constructor arguments
    def __init__(self) -> None:
        pass

    def execute(self, state: dict) -> dict:
        raise NotImplementedError

    def __call__(self, state: dict) -> dict:
        # S-1 trust gate
        required = getattr(self.__class__, "required_trust_level", None)
        if required is not None:
            caller_level = state.get("caller_trust_level", TrustLevel.ANONYMOUS.value)
            if isinstance(caller_level, str):
                try:
                    caller_level = TrustLevel[caller_level.upper()].value
                except KeyError:
                    caller_level = TrustLevel.ANONYMOUS.value
            if int(caller_level) < int(required.value):
                import framework.nodes.base_node as _bn

                _bn.emit_trace_event("s1_denied", {}, state)
                return {
                    "status": AgentStatus.ERROR.value,
                    "error": f"S-1 trust gate denied: required {required.name}",
                    "error_log": [f"S-1 trust gate denied: required {required.name}"],
                }

        # PB-6 invoke order: node_start → _security_gate_input → execute → _security_gate_output → node_complete
        import framework.nodes.base_node as _bn
        _bn.emit_trace_event("node_start", {}, state)
        try:
            state = self._security_gate_input(state)
        except SecurityViolationError as exc:
            return {
                "status": AgentStatus.ERROR.value,
                "error": str(exc),
                "error_log": [str(exc)],
            }
        try:
            result = self.execute(state)
        except Exception as exc:
            return {
                "status": AgentStatus.ERROR.value,
                "error": str(exc),
                "error_log": [str(exc)],
            }
        try:
            result = self._security_gate_output(result)
        except SecurityViolationError as exc:
            return {
                "status": AgentStatus.ERROR.value,
                "error": str(exc),
                "error_log": [str(exc)],
            }
        _bn.emit_trace_event("node_complete", {}, state)
        return result

    def _security_gate_input(self, state: dict) -> dict:
        if hasattr(self, "_extra_security_gate_input"):
            return self._extra_security_gate_input(state)
        return state

    def _security_gate_output(self, result: dict) -> dict:
        if hasattr(self, "_extra_security_gate_output"):
            return self._extra_security_gate_output(result)
        return result


base_node_mod.BaseNode = BaseNode


class FunctionNode(BaseNode):
    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        for gate in ("_security_gate_input", "_security_gate_output"):
            if gate in cls.__dict__:
                raise TypeError(
                    f"Overriding {gate} is forbidden in FunctionNode subclasses; "
                    "use the corresponding _extra_security_gate_* hook."
                )


class GraphNode(FunctionNode):
    error_strategy = "propagate"
    propagate_hitl = False

    def __init__(self, config: dict | None = None, **kwargs) -> None:
        # GraphNode IS allowed to take config= (it is not a FunctionNode wrapper)
        super().__init__()
        self._config = config or {}

    def execute(self, state: dict) -> dict:
        """Invoke the inner subgraph and merge its output into the outer state."""
        subgraph = self.get_subgraph()
        user_input = self.extract_input(state)
        # Pass the full outer state into the inner graph so inner nodes can read it
        sub_result = subgraph.invoke(user_input, ctx=None, _outer_state=state)
        return self.merge_output(state, sub_result)

    def get_subgraph(self):
        raise NotImplementedError("Subclass must implement get_subgraph()")

    def extract_input(self, state: dict) -> str:
        return state.get("sanitized_query", state.get("user_input", ""))

    def merge_output(self, state: dict, sub_result: dict) -> dict:
        return sub_result


# ── BaseGraph / AgentBaseGraph ─────────────────────────────────────────────────
class _SimpleStateGraph:
    def add_edge(self, _a, _b) -> None:
        pass

    def add_conditional_edges(self, _source, _fn, _mapping=None) -> None:
        pass


class BaseGraph:
    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._secrets_provider = None
        self._nodes: dict = {}
        self._sg = _SimpleStateGraph()
        # NOTE: _validate_config() NOT called — tests need empty-config construction
        self.register_nodes()
        self.add_edges()

    def register_nodes(self) -> None:
        pass

    def add_edges(self) -> None:
        pass

    def route(self, state: dict) -> str:
        return "END"

    def get_output(self, state: dict) -> dict:
        return dict(state)

    @property
    def config(self) -> dict:
        return self._config

    def compile(self, checkpointer=None) -> "BaseGraph":
        return self

    def provision_secrets(self, provider: object) -> None:
        self._secrets_provider = provider

    def invoke(
        self,
        user_input: str,
        session_id: str = "",
        ctx: object = None,
        input_context: dict | None = None,
        _outer_state: dict | None = None,
        **kwargs,
    ) -> dict:
        # Start from outer state if provided (inner graph inherits outer context)
        state: dict = dict(_outer_state) if _outer_state else {"user_input": user_input}
        state["user_input"] = user_input
        if input_context:
            state["input_context"] = input_context
        if ctx is not None:
            state.update({
                "session_id": getattr(ctx, "session_id", session_id or ""),
                "caller_trust_level": getattr(
                    getattr(ctx, "caller_trust_level", None), "value", 1
                ),
                "caller_id": getattr(ctx, "caller_id", ""),
            })
        for node in self._nodes.values():
            result = node(state)
            if isinstance(result, dict):
                state.update(result)
        return self.get_output(state)


class _InitializeNode(FunctionNode):
    def execute(self, state: dict) -> dict:
        return {}


class _FinalizeNode(FunctionNode):
    def execute(self, state: dict) -> dict:
        return {}


class AgentBaseGraph(BaseGraph):
    required_trust_level: TrustLevel = TrustLevel.VERIFIED_EXTERNAL

    def register_nodes(self) -> None:
        self._nodes["initialize"] = _InitializeNode()
        self._nodes["finalize"] = _FinalizeNode()


# ── Register all framework / shared modules ───────────────────────────────────
framework = _register_module("framework")

framework_graph = _register_module("framework.graph")
framework_graph_abg = _register_module("framework.graph.agent_base_graph")
framework_graph_abg.AgentBaseGraph = AgentBaseGraph
framework_graph_bg = _register_module("framework.graph.base_graph")
framework_graph_bg.BaseGraph = BaseGraph
framework.graph = framework_graph

framework_nodes = _register_module("framework.nodes")
framework_nodes_fn = _register_module("framework.nodes.function_node")
framework_nodes_fn.FunctionNode = FunctionNode
framework_nodes_gn = _register_module("framework.nodes.graph_node")
framework_nodes_gn.GraphNode = GraphNode
framework_nodes.function_node = framework_nodes_fn
framework_nodes.graph_node = framework_nodes_gn
framework.nodes = framework_nodes

framework_schemas = _register_module("framework.schemas")
framework_schemas_as = _register_module("framework.schemas.agent_state")
framework_schemas_as.AgentState = AgentState
framework_schemas_astat = _register_module("framework.schemas.agent_status")
framework_schemas_astat.AgentStatus = AgentStatus
framework_schemas_tl = _register_module("framework.schemas.trust_level")
framework_schemas_tl.TrustLevel = TrustLevel
framework_schemas_ic = _register_module("framework.schemas.invocation_context")


class InvocationContext:
    def __init__(
        self,
        session_id: str = "",
        caller_trust_level: TrustLevel = TrustLevel.VERIFIED_EXTERNAL,
        caller_id: str = "",
    ) -> None:
        self.session_id = session_id
        self.caller_trust_level = caller_trust_level
        self.caller_id = caller_id
        self.secrets = _MockSecrets()

    @classmethod
    def from_state(cls, state: dict) -> "InvocationContext":
        raw_trust = state.get("caller_trust_level", TrustLevel.VERIFIED_EXTERNAL.value)
        if isinstance(raw_trust, int):
            trust = TrustLevel(raw_trust)
        else:
            try:
                trust = TrustLevel[str(raw_trust).upper()]
            except KeyError:
                trust = TrustLevel.VERIFIED_EXTERNAL
        ctx = cls(
            session_id=state.get("session_id", ""),
            caller_trust_level=trust,
            caller_id=state.get("caller_id", ""),
        )
        return ctx


class _MockSecrets:
    _store: dict = {
        "vector_store_key": "mock-vector-store-key",
        "llm_api_key": "mock-llm-api-key",
    }

    def get(self, key: str, default=None):
        return self._store.get(key, default)

    def require(self, key: str) -> str:
        return self._store.get(key, f"mock-{key}")


framework_schemas_ic.InvocationContext = InvocationContext
framework.schemas = framework_schemas

framework_errors = _register_module("framework.errors")
framework_errors.SecurityViolationError = SecurityViolationError
framework_errors.ConfigError = ConfigError
framework.errors = framework_errors

framework_utils = _register_module("framework.utils")
framework_utils_config = _register_module("framework.utils.config_loader")


def _load_config(path: str) -> dict:
    import yaml

    with open(path, encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


framework_utils_config.load_config = _load_config
framework_utils.config_loader = framework_utils_config
framework.utils = framework_utils

shared = _register_module("shared")
shared_utils = _register_module("shared.utils")
shared_utils_al = _register_module("shared.utils.audit_logger")
shared_utils_al.emit_trace_event = emit_trace_event
shared.utils = shared_utils

shared_security = _register_module("shared.security")
shared_security.detect_credentials = lambda _text: False
shared.security = shared_security

shared_secrets = _register_module("shared.secrets")


class InMemoryProvider:
    def __init__(
        self,
        values: dict | None = None,
        namespace: str = "",
        agent_name: str = "",
    ) -> None:
        self._store = dict(values or {})
        self.namespace = namespace
        self.agent_name = agent_name

    def get(self, key: str, default=None):
        return self._store.get(key, default)

    def require(self, key: str) -> str:
        if key not in self._store:
            raise KeyError(key)
        return self._store[key]

class _DummySecretsFactory:
    def __call__(self, namespace: str = "", agent_name: str = "") -> "_MockSecrets":
        return _MockSecrets()

shared_secrets.factory = _DummySecretsFactory()
shared_secrets_inmemory = _register_module("shared.secrets.inmemory_provider")
shared_secrets_inmemory.InMemoryProvider = InMemoryProvider


class ChainedSecretProvider:
    def __init__(self, *providers) -> None:
        self._providers = providers

    def get(self, key: str, default=None):
        for provider in self._providers:
            value = provider.get(key)
            if value is not None:
                return value
        return default

    def require(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value


class EnvProvider(InMemoryProvider):
    pass


shared_secrets_chained = _register_module("shared.secrets.chained_provider")
shared_secrets_chained.ChainedSecretProvider = ChainedSecretProvider
shared_secrets_env = _register_module("shared.secrets.env_provider")
shared_secrets_env.EnvProvider = EnvProvider
shared.secrets = shared_secrets

shared_services = _register_module("shared.services")
shared_services_llm = _register_module("shared.services.llm")
shared_services.llm = shared_services_llm


class AzureOpenAIClient:
    def __init__(self, config: dict) -> None:
        self.config = config


shared_services_azure = _register_module("shared.services.llm.azure_openai_client")
shared_services_azure.AzureOpenAIClient = AzureOpenAIClient
shared_services_llm.azure_openai_client = shared_services_azure
shared.services = shared_services

framework_secrets = _register_module("framework.secrets")
framework_secrets_ctx = _register_module("framework.secrets.context")

import contextlib

@contextlib.contextmanager
def _bound_secrets(provider: object):
    yield provider

framework_secrets_ctx.bound_secrets = _bound_secrets
framework.secrets = framework_secrets
