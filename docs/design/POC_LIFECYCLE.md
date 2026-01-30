# GLADyS PoC Lifecycle

**Created**: 2026-01-30
**Status**: Living document
**Owners**: Mike Mulcahy, Scott Mulcahy

## Purpose

This document defines the PoC phases for GLADyS — what each phase proves, its success criteria, abort signals, and deferred items with triggers. This is NOT an implementation plan. Each PoC gets its own planning session before implementation begins, incorporating lessons learned from the previous phase.

## Design Approach

Each PoC follows an iterative cycle:

1. **Think** about the problem
2. **Design** a basic approach
3. **Exploratory coding** — iterate until issues become clear, tweaking the design
4. **Build** using the draft design, continue tweaking until the design is solid

Repeat within each PoC. Abort signals are the trigger to loop back to step 1 rather than push forward on a broken assumption.

## How to Read This Document

- **What to prove**: The specific claims this PoC validates
- **Success criteria**: Observable evidence that the claim holds
- **Abort signals**: Evidence that the current approach won't work — triggers a design rethink, not project abandonment
- **Lessons learned**: Populated after each PoC completes, feeds into the next PoC's planning session
- **Deferred items**: Things explicitly not in scope, with triggers for when to revisit

---

## PoC 0: Exploratory (COMPLETE)

### Question answered

Can we build the individual subsystems and get them communicating?

### What was proven

- Event pipeline exists: sensor → orchestrator → salience → executive → response
- Heuristic storage and retrieval via embeddings (CBR with pgvector cosine similarity)
- LLM integration via Ollama (Executive stub responds to events)
- Salience gateway evaluates events using cached heuristics (Rust)
- Dashboard for dev/QA observation (FastAPI + htmx)
- Explicit feedback endpoint exists (SubmitFeedback RPC)

### What was NOT proven (known gaps)

- **Confidence updates from feedback**: Explicit feedback path exists but effect on confidence scores is unverified. We don't know if feedback actually changes heuristic behavior.
- **Salience cache correctness**: The Rust LRU cache works, but there's no mechanism for cache invalidation when heuristics are updated or new heuristics are created. The cache may serve stale data indefinitely.
- **Python Orchestrator viability**: Works under trivial load (manual event submission). No data on behavior under realistic concurrent event volume. Adequate for PoC scope; unknown beyond that.
- **Heuristic creation from feedback**: The LLM can respond to events, but the path from positive feedback → new heuristic is not proven. This is the core claim PoC 1 must validate.

### Lessons learned

- Embedding-based semantic matching is the right approach (replaced word overlap — see learning.md §28)
- Python is adequate for all services at PoC scale; no evidence C#/Rust rewrites are needed yet
- Current codebase structure doesn't match the architecture we've decided on — directory restructure needed before building more
- Integration gaps exist in the feedback pipeline (GetHeuristic RPC missing, feedback_source not propagated through gRPC)

---

## Prerequisite: Directory Restructure

Not a PoC phase — infrastructure work that enables everything after it.

**Why now**: The architecture decisions from 2026-01-29 define a subsystem taxonomy and pack structure that the current directory layout doesn't support. Restructuring now (small codebase) is cheaper than restructuring later (more code to move, more paths to update).

**Scope**: Reorganize per `ARCHITECTURE.md` §9:
- `src/services/` — each subsystem gets its own directory; salience extracted from memory/
- `src/lib/` — `gladys_common` + new `gladys_client` (unified service client)
- `packs/` — domain-first plugin structure
- `cli/` — replaces scripts/ (pure CLI tools, shared libs moved to src/lib/)
- `src/db/migrations/` — database schema as shared concern, not memory-owned
- `tests/` — consolidated

**Done when**: All services start, all existing tests pass, import paths updated, Dockerfiles updated.

---

## PoC 1: Closed-Loop Learning with Real Data

### Question to answer

Can the system learn from experience with real data flowing through it?

This is the core value proposition: "the second time is faster." It requires multiple co-dependent workstreams that must converge — you can't test learning without real data, and you can't get meaningful data without real sensors.

### Workstreams

These run in parallel and converge on the integration test described below.

**Risk priority**: W4 (Heuristic Creation) is the highest-risk workstream — if the LLM can't generate usable condition_text, the core value proposition fails. W4 should reach a testable state first because it can be validated with manual dashboard events before real sensor data arrives, surfacing fundamental problems early.

#### W1: One Real Sensor

Build one real sensor that produces events without human intervention. Must emit events through the Orchestrator pipeline via gRPC. Packaged in pack structure (`packs/<domain>/sensors/`) with `manifest.yaml`.

Candidate selection is a planning-session decision. Options: Discord (Mike's domain), file watcher (simplest), game log reader (closest to target use case).

#### W2: Learning Module

Orchestrator-owned module with clean interface (typed inputs/outputs, no shared mutable state with Orchestrator). Per `ARCHITECTURE.md` §10.

Implements:
- Outcome channel consumption → confidence updates
- Basic pattern extraction (LLM-assisted, not automated batch)
- Implicit feedback signals: action undone within 60s, suggestion ignored 3+ times, no complaint within timeout (ADR-0010 §3.10)
- Explicit feedback continues working (and is verified to actually affect confidence — PoC 0 gap)

Interface must stay clean enough to extract into a separate process later without surgery.

#### W3: Feedback Pipeline Fixes

- Add `feedback_source` field to `UpdateHeuristicConfidenceRequest` in proto — implicit vs explicit must be distinguishable
- Add `GetHeuristic` RPC to proto (learning.md Gap 1 — currently a blocker for dynamic heuristic lookup)
- Resolve cache staleness: mechanism for salience cache to learn when heuristics are updated or new heuristics created

#### W4: Heuristic Creation from Feedback

Not proven in PoC 0 (see "What was NOT proven" above). This is the highest-risk workstream.

- LLM extracts generalizable pattern from successful reasoning (learning.md §22)
- New heuristics start at confidence 0.3, must earn trust through firing and positive feedback
- Instrument: log similarity scores for ALL candidates during matching, not just the winner (data for PoC 2 garbage collection decisions)

### Convergence Test

All four workstreams converge on this scenario:

1. Real sensor emits event (W1)
2. No heuristic matches → routes to Executive (LLM reasons about it)
3. Executive responds, user gives positive feedback
4. System creates heuristic from the successful interaction (W4)
5. Sensor emits semantically similar (not identical) event
6. Heuristic fires, LLM skipped — response is faster
7. Learning module records the fire and tracks outcome (W2)
8. Implicit feedback (user doesn't complain / follows through) reinforces confidence (W3)

### Success Criteria

| # | Criterion | Observable evidence |
|---|-----------|-------------------|
| 1 | Heuristic creation works | Positive feedback on LLM response → new heuristic appears in heuristics table with condition_text, condition_embedding, confidence=0.3 |
| 2 | Semantic matching works | Heuristic fires on semantically similar (not identical) real events with >0.6 similarity |
| 3 | Confidence tracks reality | Query `heuristics` table: after 10+ fires with majority-positive feedback, confidence > 0.6. After 10+ fires with majority-negative feedback, confidence < 0.4. Trend visible in dashboard Learning tab or `heuristic_fires` table time series. |
| 4 | Bad heuristics decay | Repeated negative feedback → confidence drops below firing threshold (0.7). Event routes to LLM instead. Observable: dashboard event row shows LLM path, not heuristic path. |
| 5 | Specificity holds | Submit events from two different domains. Query `heuristic_fires`: no fire records where the heuristic's condition domain doesn't match the event's source domain. |
| 6 | Implicit/explicit distinguishable | Query `heuristic_fires`: records show correct `feedback_source` ('implicit' vs 'explicit') matching how the feedback was generated. |
| 7 | Cache reflects reality | After storing a new heuristic, submit a matching event. Heuristic fires within N requests (where N depends on cache TTL or invalidation mechanism — specific bound determined during W3 implementation). |

### Abort Signals

| Signal | What it means | Response |
|--------|--------------|----------|
| Embeddings don't discriminate | Similar events don't match, or dissimilar events match too broadly | Evaluate different embedding models per ADR-0013 §11. May need source_filter as hard constraint, not hint. |
| LLM generates bad condition_text | Conditions are consistently too vague ("user asks a question") or too specific ("user asks about Minecraft combat in the Nether on Tuesday") | Constrained generation, structured condition templates, or human-in-the-loop condition editing |
| Confidence oscillates | Beta-Binomial doesn't converge — swings wildly with each feedback signal | Parameter tuning. If fundamental, evaluate alternative confidence models. |
| Implicit feedback too noisy | "No complaint within timeout" fires too often as positive signal, drowning out real signal | Adjust signal weights (ADR-0010 §3.10), increase timeout, reduce implicit weight |

### Lessons Learned

*(To be populated after PoC 1 completes)*

---

## PoC 2: Real-World Viability

### Question to answer

Can the system handle real-world conditions — multiple sensors, concurrent events, acceptable latency, and heuristic scale?

### Prerequisites

- PoC 1 convergence test passes
- Planning session incorporating PoC 1 lessons learned

### What to Prove

| # | Claim | How to test | Success criteria | Abort signal |
|---|-------|------------|-----------------|--------------|
| 1 | **Multiple concurrent sensors** | Add a second sensor from a different domain. Both emit events simultaneously. | Event count submitted = event count in `episodic_events` (stored) + events with timeout responses. No unaccounted events. Queue depth returns to 0 within 60s of last event. | asyncio single-threaded model can't keep up. Known fire-and-forget issues cause silent failures. |
| 2 | **Latency is acceptable** | Measure end-to-end p50/p95/p99 under realistic load. | Heuristic path <500ms. LLM path <10s. Measured from `PublishEvents` call to response delivery, logged in structured logs with trace ID. | LLM path consistently >15s with no architectural fix available. |
| 3 | **Heuristic scale** | Run system through extended real sessions. Track heuristic count, similarity space crowding, query time as count grows. | Same test events that matched correctly at 10 heuristics still match the correct heuristic at 100+ (no rank displacement). `QueryMatchingHeuristics` RPC latency stays under 20ms p95 per structured logs. | Embedding space gets crowded — too many false-positive near-matches. |
| 4 | **Learning works over time** | Track heuristic hit rate, false positive rate, LLM fallback rate across sessions. | LLM fallback rate (events routed to Executive / total events) is lower in session N+1 than session 1. Stabilizes (varies <10% between consecutive sessions) after sufficient sessions. >50% of heuristics created in session N fire on a matching event in session N+1 — verified via `heuristic_fires` joined to `heuristics` by `created_at` window. | Heuristics are too specific (only fire on near-identical events) or too broad (fire on everything). |
| 5 | **Sleep-mode consolidation** | Implement merge (similar conditions + similar effects → combine), demote (low confidence + sufficient evidence → frozen), staleness decay (ADR-0010 §3.3.4). Similarity and confidence thresholds are tuning parameters determined during implementation. | Heuristic count stabilizes over extended sessions. Merged heuristics retain matching accuracy — same events still trigger correct responses. Stale heuristics stop firing without manual intervention. Consolidation runs without degrading live pipeline performance. | Merging destroys nuance — consolidated heuristics produce worse responses than originals. Staleness decay removes heuristics that are still valid but infrequently triggered. |

### Lessons Learned

*(To be populated after PoC 2 completes)*

---

## PoC 3: Product Viability

### Question to answer

Does this generalize beyond one domain, and would someone actually want to use it?

### Prerequisites

- PoC 2 demonstrates learning works at scale with real data
- Planning session incorporating PoC 2 lessons learned

### What to Prove

| # | Claim | How to test | Success criteria | Abort signal |
|---|-------|------------|-----------------|--------------|
| 1 | **Cross-domain reasoning** | Two sensors from different domains active. Query requiring information from both. | Executive response references entities or facts from both domains. Verified by inspecting logged LLM context window — retrieval included memories from both sensor sources. | Memory retrieval can't scope queries well enough, or Executive prompt can't handle multi-source context. |
| 2 | **Domain skill plugins** | Build one real skill. Verify it loads, receives events, provides domain-specific confidence via `evaluate_outcome()`. | Compare confidence convergence rate: heuristics in the skill-equipped domain reach confidence >0.7 in fewer fires than heuristics in a domain without skills, using comparable event volume. Measured from `heuristic_fires` and `heuristics.confidence` time series. | Plugin interface too complex to implement practically, or skill overhead negates benefit. |
| 3 | **Personality affects behavior** | Same events, two personality packs. Personality heuristics (tagged by origin) fire correctly under right personality, disable on swap. | Personality-tagged heuristics (`origin LIKE 'personality:%'`) fire only when their personality is active. After personality swap, previously-active personality heuristics have zero fires. Tone/reasoning difference validated by human review of response pairs (subjective — intentionally a UX judgment). | Personality is just prompt-prefix with no meaningful behavioral change. |
### Lessons Learned

*(To be populated after PoC 3 completes)*

### Product Readiness (separate from technical PoC)

| # | Question | How to test | What we're looking for |
|---|----------|------------|----------------------|
| 1 | **Demonstrable to outsiders** | Someone outside the team watches the system handle a repeated scenario faster the second time, with a real sensor. | Observer understands what happened and finds it compelling without explanation of internals. |

This is product validation, not a technical proof. It depends on PoC 3's technical criteria passing first.

---

## Validation Tooling

If a success criterion says "observable," there must be a tool that lets you observe it. Tooling that directly supports proving or observing a PoC's claims is in-scope for that PoC — it's part of making the claims verifiable, not separate work.

Tooling takes three forms:

- **Dashboard extensions**: New tabs, panels, or visualizations for ongoing observation
- **CLI / scripts**: Repeatable commands for running convergence tests, submitting event batches, computing metrics
- **Ad-hoc queries**: SQL or gRPC queries run manually — acceptable for one-off validation, but if you run the same query repeatedly, it should become a dashboard feature or CLI command

Each PoC's planning session should identify which success criteria need dedicated tooling vs. which can be verified with existing tools. The lists below are starting points — actual scope is determined during planning.

### Dashboard Evolution

The dashboard is a dev/QA tool that grows alongside the system. Each PoC introduces features that need to be observable — the dashboard should be extended during each PoC to support validation of that phase's success criteria.

### PoC 1: Learning Observability

- **Confidence history**: Visualize confidence over time per heuristic (supports criterion #3 — "confidence tracks reality")
- **Heuristic creation events**: Show when a heuristic was created, from which event/feedback, with what condition_text (supports criterion #1)
- **Feedback source labels**: Display implicit vs explicit in fire records (supports criterion #6)
- **Candidate similarity scores**: Show all candidates evaluated during matching, not just the winner (instruments for PoC 2 garbage collection)
- **Cache state visibility**: Show cache contents, staleness, last refresh (supports criterion #7)

**CLI / scripts**:
- Convergence test runner: submit event → give feedback → submit similar event → verify heuristic fired (automates the PoC 1 convergence scenario)
- Heuristic inspector: query a heuristic's full history — creation source, fires, feedback, confidence trajectory

### PoC 2: Scale and Performance Observability

- **Latency metrics**: p50/p95/p99 for heuristic path and LLM path, visible per-session (supports criterion #2)
- **Event accounting**: Submitted vs stored vs timed-out counts — verifies no silent drops (supports criterion #1)
- **Heuristic density**: Visualization of similarity space crowding — how close are heuristic embeddings to each other? (supports criterion #3)
- **LLM fallback rate**: Per-session trend line — is the system learning? (supports criterion #4)
- **Consolidation log**: What was merged/demoted/decayed during sleep mode (supports criterion #5)

**CLI / scripts**:
- Load test harness: submit N events from M sensors simultaneously, report event accounting (submitted vs stored vs timed out)
- Rank stability checker: submit fixed test events at different heuristic counts, verify same heuristic wins each time
- Session metrics reporter: compute LLM fallback rate, heuristic hit rate, false positive rate for a given time window

### PoC 3: Multi-Domain and Plugin Observability

- **Cross-domain retrieval**: Show which memory sources contributed to a response (supports criterion #1)
- **Skill activity**: Which skills are loaded, which evaluated outcomes, what valence they returned (supports criterion #2)
- **Personality state**: Active personality, which personality heuristics are enabled/disabled (supports criterion #3)

**CLI / scripts**:
- Cross-domain query test: submit events from two domains, issue a query requiring both, verify retrieval sources in logged context
- Personality swap test: activate personality A, submit events, swap to B, verify A's heuristics stop firing

Tooling for a PoC phase is scoped during that phase's planning session, not pre-committed here. The lists above are starting points — actual needs will be clearer once implementation begins.

---

## Deferred Items and Triggers

Items explicitly out of scope for all PoC phases, with conditions that would bring them back in.

| Item | Why deferred | Trigger to revisit | Best evaluated during |
|------|-------------|-------------------|----------------------|
| **C# Executive rewrite** | Python stub works at PoC scale. No evidence it's needed. | Latency data from PoC 2 shows Python is the bottleneck, not LLM inference or I/O. | PoC 2 (latency measurements) |
| **Actuator conflict resolution** | No actuators exist yet. Can't design conflict resolution without at least two competing actuators. | Building the second actuator that claims an overlapping capability. | PoC 3 (multi-domain) |
| **Deferred validation / experience replay** | ADR-0010 §3.12 describes it but needs working learning loop and significant data first. | S1 accuracy <70% in any domain after 1000+ decisions (ADR-0010 §3.13.2). | PoC 2 (learning-over-time metrics) |
| **Prioritized replay** | Post-MVP per ADR-0010 §3.13.2. | S1 accuracy <70% after 1000+ decisions AND basic FIFO replay doesn't improve it. | PoC 2 |
| **Exploration epsilon** | Post-MVP per ADR-0010 §3.13.2. | S1 decision diversity < threshold (system stuck in local optima). | PoC 2 (heuristic diversity metrics) |
| **Fine-tuning strategy** | Requires Leah input. Post-MVP. | PoC 3 complete and online learning alone is insufficient. | Post-PoC 3 |
| **Multi-user households** | Post-MVP. Single user is hard enough. | Product viability discussions after PoC 3. | Post-PoC 3 |
| **Supervisor subsystem** | No real sensors/plugins to monitor yet. | Multiple sensors running concurrently need health monitoring. | PoC 2 (multiple sensors) |
| **Preprocessors** | Role defined (fast enrichment salience depends on), but no real sensor data to preprocess. | Real sensor produces data that needs enrichment before salience can evaluate it meaningfully. | PoC 1 or PoC 2 (depends on sensor choice) |
| **Context/Mode detection** | Needs an owner (Orchestrator or Salience). Design not started. | Second domain sensor added — system needs to distinguish contexts. | PoC 2 (multiple sensors/domains) |
| **Configuration subsystem** | Runtime config changes beyond .env-at-startup. Dashboard Settings tab needs a backend. | Settings tab is needed for practical use during testing. | PoC 1 or PoC 2 |
| **Plugin behavior enforcement** | "Immune system" for plugins. We control all plugins during PoC. | Third-party or community plugins considered. | Post-PoC 3 |
| **Brain subsystem audit** | Systematic review of brain regions mapped to GLADyS functions. Worth doing deliberately. | After PoC 1 when the learning system exists and we can compare design to implementation. | PoC 2 planning session |
| **Linux/WSL readiness** | Audit for Windows path assumptions. | Directory restructure (prerequisite phase). | Prerequisite phase |
| **Install package / dev setup** | Single-command setup. | New developer onboards, or setup friction slows iteration. | Any PoC |
| **Hot reload for Python gRPC** | Code velocity improvement. | Iteration speed becomes a bottleneck during implementation. | Any PoC |

---

## PoC Lifecycle Process

Each PoC follows this lifecycle:

```
┌──────────────────────────────────────────────────────────────┐
│  1. PLANNING SESSION                                          │
│     - Review lessons learned from previous PoC                │
│     - Evaluate deferred item triggers                         │
│     - Create implementation plan for this PoC                 │
│     - Identify workstreams and dependencies                   │
│                                                               │
│  2. IMPLEMENTATION (iterative)                                │
│     - Think → Design → Exploratory code → Build               │
│     - Repeat within PoC until design solidifies               │
│     - Monitor abort signals continuously                      │
│                                                               │
│  3. VALIDATION                                                │
│     - Run success criteria tests                              │
│     - Document what was actually proven vs assumed             │
│     - Be honest about gaps (see PoC 0 corrections)            │
│                                                               │
│  4. LESSONS LEARNED                                           │
│     - What worked, what didn't, what surprised us             │
│     - Update this document                                    │
│     - Feed into next PoC's planning session                   │
└──────────────────────────────────────────────────────────────┘
```
