# Test Specification — EDU-C2-031 University Career Support Agent

## Test Strategy
- Coverage target: 80%+
- Test types: Unit (nodes), Integration (graph invoke), Proof-of-Boundary

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Status |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | ✅ Pass |
| TC-02 | SecurityViolationError fires on PII input (S-2) | SecurityViolationError raised → __call__ returns ERROR | ✅ Pass |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan` and PB-2 AST scan: 0 violations | ✅ Pass |
| TC-04 | InvocationContext constructed only via `from_state()` inside nodes | GuidanceRetrieveNode reconstructs context with `InvocationContext.from_state(state)`; the standalone adapter is the authenticated entry-point exception | ✅ Pass |
| TC-05 | S-4: no duplicate lifecycle events in execute() | node_start / node_complete / node_error absent from execute() body | ✅ Pass |
| TC-06 | S-2: `_security_gate_input()` not overridden (FunctionNode subclass) | Framework raises `TypeError` at class definition | ✅ Pass |
| TC-07 | S-3: `_security_gate_output()` not overridden (FunctionNode subclass) | Framework raises `TypeError` at class definition | ✅ Pass |
| TC-08 | `required_trust_level` declared and enforced through `node(state)` | Insufficient trust is refused before `execute()` and normal lifecycle events | ✅ Pass |
| TC-09 | S-2: _extra_security_gate_input() non-trivial | Input size, route, ES draft length validated | ✅ Pass |
| TC-10 | S-3: _extra_security_gate_output() non-trivial | Email/phone PII blocked; employment-outcome phrases blocked | ✅ Pass |
| TC-11 | S-4: ≥1 domain emit_trace_event() per execute() | Domain event emitted on every node invocation path | ✅ Pass |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Status |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | emit_trace_event() fires on every invocation path | No silent failures | ✅ Pass |
| PB-2 | State serialization | Post-invoke State fields are JSON-serializable primitives | No Pydantic/dataclass | ✅ Pass |
| PB-3 | L1 template boundary → External service | GuidanceRetrieveNode resolves `vector_store_key`; deterministic fixture evidence remains the provisional local path | Credential boundary resolved; real vector-store connection required before production cutover | ⚠️ Provisional |
| PB-4 | Import isolation | No Level 0 (agenticstar) imports in src/ | AST scan: 0 violations | ✅ Pass |
| PB-5 | Checkpoint safety *(conditional)* | Inspect checkpoint payload, metadata, and pending writes only when runtime checkpointing and framework ingress hooks are enabled | Auto-waived — checkpointing disabled | ✅ Auto-waived |
| PB-6 | Invoke execution order | __call__(): S-1 trust gate → node_start → _security_gate_input → execute() → _security_gate_output → node_complete | Order verified for all nodes | ✅ Pass |
| PB-7 | HITL interrupt propagation *(conditional)* | **Auto-waived — non-HITL** (`hitl.enabled: false` in `config/config.yaml`) | N/A | ✅ Auto-waived |

> PB-1 through PB-4 and PB-6 are mandatory. PB-5 applies only after runtime
> checkpointing is enabled and the installed framework exposes both ingress
> protection hooks. PB-7 applies only to HITL-enabled templates.

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Status |
|-------|------|-------|----------------|--------|
| BL-01 | Valid Q&A query produces SUCCESS | "career support services" | status=SUCCESS, sanitized_query set | ✅ Pass |
| BL-02 | Empty input returns ERROR | "" | status=ERROR, error_log set | ✅ Pass |
| BL-03 | Email PII redacted from query | "student@example.com" in input | [REDACTED_EMAIL] in sanitized_query | ✅ Pass |
| BL-04 | Phone PII redacted from query | "+81 90-1234-5678" in input | REDACTED in sanitized_query | ✅ Pass |
| BL-05 | Invalid route hint blocked by S-2 | route_hint="INVALID" | status=ERROR | ✅ Pass |
| BL-06 | Oversized input blocked by S-2 | 2001 chars | status=ERROR | ✅ Pass |
| BL-07 | Valid route hint honored | route_hint="interview_preparation" | resolved_route="interview_preparation" | ✅ Pass |
| BL-08 | ES draft PII redacted | "john@example.com" in es_draft | email removed from sanitized_es_draft | ✅ Pass |
| BL-09 | Malformed academic year cleared | "INVALID" | academic_year_context="" | ✅ Pass |
| BL-10 | Unknown industry defaults to general | target_industry="aerospace" | target_industry="general" | ✅ Pass |
| BL-11 | Caller route hint honored | route_hint="grounded_qa" | resolved_route="grounded_qa", confidence=1.0 | ✅ Pass |
| BL-12 | Timeline keywords route correctly | "When does recruiting start?" | resolved_route="timeline_guidance" | ✅ Pass |
| BL-13 | Interview keywords route correctly | "How to prepare for interview" | resolved_route="interview_preparation" | ✅ Pass |
| BL-14 | ES keywords route correctly | "review my entry sheet" | resolved_route="es_feedback" | ✅ Pass |
| BL-15 | Ambiguous query routes to QA with warning | "help" | resolved_route="grounded_qa" + warning | ✅ Pass |
| BL-16 | Timeline route retrieves evidence with citation | timeline_guidance route | ≥1 chunk with citation field | ✅ Pass |
| BL-17 | Stale corpus produces warning | AY mismatch | corpus_freshness="stale" + warning | ✅ Pass |
| BL-18 | Finance industry produces ≥5 checklist items | target_industry="finance" | ≥5 items with citation | ✅ Pass |
| BL-19 | Unknown industry falls back gracefully | target_industry="aerospace" | general profile + warning | ✅ Pass |
| BL-20 | No hiring guarantee in checklist | any interview route | No "guaranteed employment" in output | ✅ Pass |
| BL-21 | Non-interview route skips industry context | grounded_qa route | industry_context={} | ✅ Pass |
| BL-22 | Advisory notice present in industry context | interview_preparation route | advisory_notice key present | ✅ Pass |
| BL-23 | Valid ES draft produces ≥3 suggestions | "I want to work here" | ≥3 rubric-grounded suggestions | ✅ Pass |
| BL-24 | Non-ES route skips feedback | grounded_qa route | es_suggestions=[] | ✅ Pass |
| BL-25 | Empty ES draft produces warning | route_hint=es_feedback, no draft | warning emitted | ✅ Pass |
| BL-26 | No score/rank in suggestions | any draft | "score:", "hiring probability" absent | ✅ Pass |
| BL-27 | Prompt injection cannot alter rubric fields | malicious draft | criterion stays in valid set | ✅ Pass |
| BL-28 | Q&A route produces grounded answer with citations | fresh corpus | answer + ≥1 citation | ✅ Pass |
| BL-29 | Stale corpus prevents definitive timeline claim | stale corpus | verification_required=true | ✅ Pass |
| BL-30 | Forbidden content blocked at synthesis | "you will be hired" scenario | blocked in artifact | ✅ Pass |
| BL-31 | Interview route includes checklist | interview_preparation | checklist_items ≥1 | ✅ Pass |
| BL-32 | ES route includes authorship + advisory notice | es_feedback | authorship_notice + advisory_notice present | ✅ Pass |
| BL-33 | Email in formatted_output blocked by S-3 | email in artifact | S-3 blocks or sanitizes | ✅ Pass |
| BL-34 | Hiring guarantee phrase blocked by S-3 | "you will be hired" in artifact | S-3 blocks or sanitizes | ✅ Pass |
| BL-35 | Upstream ERROR propagates cleanly | status=ERROR from inner | formatted_output with error + advisory_notice | ✅ Pass |
| BL-36 | Advisory notice present in all formatted output | any route | advisory_notice in formatted_output | ✅ Pass |
| BL-I01 | Q&A happy path — full invoke | generic career question | status=SUCCESS, formatted_output with advisory_notice | ✅ Pass |
| BL-I02 | Timeline happy path — full invoke | "When does recruiting start?" | verification_required or timeline route | ✅ Pass |
| BL-I03 | Interview happy path — full invoke | "Finance interview prep" | status=SUCCESS, advisory_notice | ✅ Pass |
| BL-I04 | ES feedback happy path — full invoke | "review my entry sheet" | status=SUCCESS, advisory_notice | ✅ Pass |
| BL-I05 | Empty input — full invoke | "   " | returns result without raising | ✅ Pass |
| BL-I06 | PII not in output — full invoke | "student@example.com" in input | email absent from formatted_output | ✅ Pass |
| BL-I07 | Prompt injection — full invoke | injection asking for fabricated citations | forbidden phrases absent from output | ✅ Pass |
| BL-I08 | Standalone server boots without Anthropic key | secrets provider returns no key | app and graph construct with `llm=None` | ✅ Pass |
| BL-I09 | Optional Anthropic client reaches Cat 2 composite node | secrets provider returns test key | identical client stored on main GraphNode and forwarded in inner-graph config | ✅ Pass |
| BL-I10 | Standalone bearer trust mapping | external, runner, and invalid bearer tokens | VERIFIED_EXTERNAL, INTERNAL, and HTTP 401 respectively | ✅ Pass |

## Test Execution Summary
- Execution date: 2026-08-18
- Total tests: 75
- Pass: 72 / Fail: 0 / Skip: 3 (PB-5 and PB-7 conditional waivers)
- Coverage: Not collected by `check-local.sh`; lint, type, unit, proof-of-boundary, and Stage 5 gates passed

**PB-5 waiver record:** `config/config.yaml` sets `memory_enabled: false` and `hitl.enabled: false`; checkpoint persistence is disabled.

**PB-7 waiver record:** `config/config.yaml` sets `hitl.enabled: false`. PB-7 is **Auto-waived — non-HITL**. The conditional test file is present with appropriate skip markers.
