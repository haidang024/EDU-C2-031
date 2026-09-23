# Template Design Specification — EDU-C2-031 University Career Support Agent

## Position in AgentCore Architecture

- **Template ID**: EDU-C2-031
- **Agent Class**: Graph (outer), CareerSupportWorkflowGraph (inner)
- **L1 Base**: AgentBaseGraph (outer) + BaseGraph (inner)
- **Three-Layer Separation**:
  - State: flat TypedDict composition (msgpack-safe; no Pydantic, dataclass, secrets)
  - Node: FunctionNode inheritance (Template Method: `execute(self, state: dict) -> dict`)
  - Graph: Cat 2 composition (outer AgentBaseGraph + inner BaseGraph via GraphNode)

## Architecture Overview

### Node Configuration

| Node | Layer | Responsibility | Trust Level |
|------|-------|---------------|-------------|
| initialize | Outer backbone | AgentBaseGraph default | — |
| pre_process (PreProcessNode) | Outer | S-1/S-2 validation, PII minimization, input normalization | VERIFIED_EXTERNAL |
| main (CareerSupportWorkflowGraphNode) | Outer | Wraps inner workflow graph | — (GraphNode) |
| post_process (PostProcessNode) | Outer | S-3 output redaction, final response assembly | VERIFIED_EXTERNAL |
| finalize | Outer backbone | AgentBaseGraph default | — |
| intent_classify (IntentClassifyNode) | Inner | Keyword-based route classification | ANONYMOUS |
| guidance_retrieve (GuidanceRetrieveNode) | Inner | Versioned corpus evidence retrieval | ANONYMOUS |
| industry_context (IndustryContextNode) | Inner | Industry profile + advisory checklist generation | ANONYMOUS |
| es_feedback (ESFeedbackNode) | Inner | ES draft rubric evaluation | ANONYMOUS |
| synthesize (SynthesizeNode) | Inner | Route-specific response artifact assembly | ANONYMOUS |

### Data Flow

```
START → initialize → pre_process → [CareerSupportWorkflowGraphNode] → post_process → finalize → END
                                             │
                       ┌─────────────────────┴─────────────────────────┐
                       │         CareerSupportWorkflowGraph (inner)     │
                       │  START → intent_classify → guidance_retrieve   │
                       │        → industry_context → es_feedback        │
                       │        → synthesize → END                      │
                       └────────────────────────────────────────────────┘
```

### Routes

| Route | Trigger | Active Inner Nodes | Output |
|-------|---------|-------------------|--------|
| `grounded_qa` | General career question | guidance_retrieve + synthesize | Grounded answer + citations |
| `timeline_guidance` | Date/deadline/season query | guidance_retrieve + synthesize | Timeline guidance + verification notice |
| `interview_preparation` | Interview prep query | guidance_retrieve + industry_context + synthesize | Advisory checklist + citations |
| `es_feedback` | ES draft review | es_feedback + synthesize | Rubric-grounded suggestions + notices |

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| masked_student_ref | str | Opaque student reference token (no PII) | No |
| sanitized_query | str | PII-stripped query text | Yes |
| route_hint | str | Caller-supplied or detected route | No |
| target_role | str | Target role for interview/ES routes | No |
| target_industry | str | Industry profile selector | No |
| academic_year_context | str | AY2025-2026 format academic year | No |
| sanitized_es_draft | str | PII-stripped ES draft (ephemeral) | es_feedback route |
| resolved_route | str | Classified route after IntentClassifyNode | Yes (inner) |
| classification_confidence | str | JSON float [0.0, 1.0] | Yes (inner) |
| classification_rationale | str | Audit rationale code | Yes (inner) |
| retrieved_evidence | str | JSON list[dict] evidence chunks with citations | Yes (inner) |
| corpus_version | str | Evidence corpus version | Yes |
| corpus_freshness | str | fresh / stale / missing | Yes |
| industry_context | str | JSON dict industry profile + checklist | interview_preparation/es_feedback |
| es_suggestions | str | JSON list[dict] rubric-grounded suggestions | es_feedback route |
| response_artifact | str | JSON route-specific response | Yes |
| citations | str | JSON list of citations | Yes |
| advisory_notice | str | Non-removable advisory text | Yes |
| warnings | str | JSON list of warnings | Yes |
| request_id | str | Correlation ID (no PII) | Yes |

**State Constraints (mandatory):**
- Flat TypedDict only (all structured payloads JSON-encoded as str for msgpack safety)
- No JWT, API keys, credentials, or raw student PII in State
- InvocationContext reconstructed with `InvocationContext.from_state(state)` inside nodes (not stored in State)
- No Pydantic models, dataclass, arbitrary Python objects

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, caller trust, credential handle)
- [ ] ConnectionPolicy (no external network connector is active in the deterministic implementation)
- [x] SecurityViolationError
- [x] S-2: `_extra_security_gate_input()` on PreProcessNode: input size, route validation, ES draft length
- [x] S-3: `_extra_security_gate_output()` on PostProcessNode: PII redaction (email/phone), forbidden employment-outcome language
- [x] S-4: `emit_trace_event()` — domain-specific event in every `execute()` body (≥1 per node, no lifecycle duplication)
- [ ] HITL: disabled (`config/config.yaml`: `hitl.enabled: false`)

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclasses use the framework-final default gates and extend
>   them only through `_extra_security_gate_input()` and
>   `_extra_security_gate_output()`.
> - `GraphNode` deliberately delegates boundary enforcement to the outer and
>   inner workflow nodes.
> - No custom direct `BaseNode` subclass is used by this template.

### Security Controls Summary

| Control | Implementation |
|---------|---------------|
| S-1 trust gate | PreProcessNode + PostProcessNode: VERIFIED_EXTERNAL |
| S-2 input gate | PreProcessNode: size limits, route validation, PII regex |
| S-3 output gate | PostProcessNode: email/phone PII, employment-claim phrases |
| S-4 trace events | All nodes: ≥1 domain event per execute() |
| PII minimization | Email, phone, student-ID redacted at PreProcessNode boundary |
| Citation mandatory | All Q&A/timeline answers cite corpus source and version |
| Advisory notice | Non-removable across all routes |
| Forbidden content | Hiring predictions blocked at SynthesizeNode + S-3 gate |
| Prompt injection | ES rubric fields fixed in code; draft cannot alter criterion/rubric_ref |
| Corpus staleness | Stale/missing corpus triggers warning; no definitive timeline claims |

### Composition Pattern

- **Pattern**: GraphNode (Cat 2 subgraph)
- **Composition target**: CareerSupportWorkflowGraph (inner BaseGraph, 5 domain nodes)
- **Error propagation strategy**: `"propagate"` — fail fast; partial guidance is more harmful than a clear error

### Runtime Configuration and LLM Injection

The standalone adapter loads `config/config.yaml`, creates the shared secrets
provider, and reads `ANTHROPIC_API_KEY` with `.get()`. A missing key is a supported
boot path and produces `llm=None`. The resulting client is stored in
`Graph(config={"llm": ...})`, then explicitly passed to
`CareerSupportWorkflowGraphNode(llm=self.config.get("llm"), config=self.config)`.
The composite node forwards the same configuration to
`CareerSupportWorkflowGraph`. This is the Cat 2 equivalent of direct
`MainNode(llm=...)` injection and prevents nodes from relying on a hidden graph
configuration back-reference.

The current business workflow is deterministic (`generation_mode:
"deterministic"`); the injected client is optional and reserved for controlled
future classification or synthesis paths.

## EU AI Act Art.13 Design-Time Evidence

The proposal declares this advisory-only agent **Not in scope** for Annex III,
so mandatory Art.13 high-risk-system evidence is not applicable. The template
still exposes the following transparency controls:

| Evidence item | Design reference / description |
|---------------|--------------------------------|
| Intended purpose and operating context | Advisory university career guidance for shūkatsu; no admissions, learning-outcome, hiring, ranking, or eligibility decision |
| System capabilities and limitations | Four fixed routes, versioned mock corpus, deterministic routing, no guaranteed employer outcome, stale-data warning |
| User-facing transparency information | Citations, corpus version, warnings, uncertainty/verification fields, and non-removable advisory notice |
| Human oversight mechanism | Career advisers and employers remain authoritative; users are directed to verify eligibility, requirements, and deadlines |

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | Career Q&A is a single-round job; no autonomous iteration needed |
| Inner topology | Conditional branching | Linear (route-aware nodes) | Linear | Each inner node no-ops for irrelevant routes; simpler coverage and debuggability |
| ES draft storage | Full draft in State | Ephemeral PII-stripped | Ephemeral (sanitized_es_draft) | ADR-005 msgpack safety + privacy minimization |
| Structured state fields | list/dict directly | JSON-encoded str | JSON-encoded str | msgpack checkpoint safety |
| Industry context | LLM-generated | Static versioned profiles | Static versioned profiles | Eliminates hallucinated employer requirements; citations are authoritative |
| Error strategy | propagate | handle | propagate | A partial/silent career-support response is worse than an explicit error |
