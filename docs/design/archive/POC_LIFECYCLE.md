# GLADyS PoC Lifecycle

**Created**: 2026-01-30
**Status**: Living document
**Owners**: Mike Mulcahy, Scott Mulcahy

## Terminology Note

"PoC" in this project means **incremental development with a proof obligation** — not throwaway code. Each PoC limits *scope* (what we build) but not *standards* (how we build it). Code written in a PoC is production-quality code with tests, proper separation of concerns, and clean interfaces. The difference from a full release is that we're building fewer features per cycle, not that we're building them worse.

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
- **Salience cache not functioning as designed**: The Rust LRU cache was designed as the fast path for heuristic matching (cache → DB → LLM), but currently only tracks hit/miss stats — Python storage is always queried (`server.rs:242-295`). The cache must become authoritative for matching in PoC 1. This requires solving cache staleness (invalidation when heuristics are created, updated, or decayed). Whether to check cache and DB simultaneously (hedged request) is a separate design question.
- **Python Orchestrator viability**: Works under trivial load (manual event submission). No data on behavior under realistic concurrent event volume. Adequate for PoC scope; unknown beyond that.
- **Heuristic creation from feedback**: The LLM can respond to events, but the path from positive feedback → new heuristic is not proven. This is the core claim PoC 1 must validate.

### Lessons learned

- Embedding-based semantic matching is the right approach (replaced word overlap — see learning.md §28)
- Python is adequate for all services at PoC scale; no evidence C#/Rust rewrites are needed yet
- Current codebase structure doesn't match the architecture we've decided on — directory restructure needed before building more
- Integration gaps exist in the feedback pipeline (GetHeuristic RPC missing, feedback_source not propagated through gRPC)
- Orchestrator processes one event at a time (`event_queue.py:177-198`); executive handles one per RPC call (`gladys_executive/server.py:375-456`). Fine for PoC 0 but architectural constraint for real sensor data.

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

### Framing: Accuracy-Latency Tradeoff

PoC 1 doesn't need to solve the general resource allocation problem, but it lays the foundation. The heuristic firing threshold IS an accuracy-latency tradeoff decision — "when is a cached answer good enough to skip reasoning?" Getting this framing right now prevents rework in PoC 2 when real volume arrives. See `docs/design/questions/resource-allocation.md` for the full analysis and research questions.

### Workstreams

These run in parallel and converge on the integration test described below.

**Risk priority**: W4 (Heuristic Creation) is the highest-risk workstream — if the LLM can't generate usable condition_text, the core value proposition fails. W4 should reach a testable state first because it can be validated with manual dashboard events before real sensor data arrives, surfacing fundamental problems early.

#### W1: One Real Sensor

Build one real sensor that produces events without human intervention. Must emit events through the Orchestrator pipeline via gRPC. Packaged in pack structure (`packs/<domain>/sensors/`) with `manifest.yaml`.

**Prerequisite**: Define sensor event contract before building the sensor:

- Composable event interface model: base interface (all events) + domain interfaces (pack-defined) + event-type interfaces (conditional on discriminator fields). Not a single flat schema.
- Driver → Sensor → Orchestrator interface (driver sends raw data, sensor normalizes to interface model)
- Basic guidance for when to use preprocessors vs send raw events
- Contract must accommodate both push (event-driven) and polling sensor patterns

See `docs/design/questions/resource-allocation.md` (Sensor Event Contract Design) for full design questions.

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
- Fix cache to serve its designed role: cache must be authoritative for heuristic matching (cache → DB fallback → LLM). Currently bypassed — Python storage always queried (`server.rs:242-295`). Requires: cache population strategy, staleness detection/invalidation when heuristics are created/updated/decayed, and a design decision on whether to hedge (check cache and DB simultaneously)

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

Detailed findings: [`docs/design/questions/poc1-findings.md`](../questions/poc1-findings.md) (F-01 through F-24).

**Heuristic matching & source:**

- Source must carry significant weight in matching — cross-domain false positives without it (F-01)
- Matching quality is multi-causal: embedding model, source filtering, raw_text consistency, condition_text quality (F-02)

**Learning & confidence:**

- Positive feedback needs gradient scale (diminishing returns per heuristic) (F-03)
- Low-confidence heuristics should appear as options in LLM prompt — LLM convergence is a signal (F-04)
- Confidence must never reach 0 or 1 (F-05)
- LLM self-reported confidence needs calibration — unclear what it measures (F-06)

**Goals & response selection:**

- Goal statement needed in LLM prompt for quality responses (F-07)
- Goal-to-event matching is unresolved — needs design session (F-08)
- Response selection may be combinatorial, not single-choice (F-09)
- Multi-dimensional response scoring may be needed (F-10)

**Feedback & timing:**

- Feedback windows differ by type (manual vs implicit) and domain (F-11)
- User 3-point + dev 5-point dual feedback design (F-23)
- Pack heuristic constraints: locked, floor/ceiling, feedback_weight (F-24)

**Executive architecture:**

- Multi-threaded LLM exploration for complex scenarios (F-12)
- LLM could return multiple ranked options instead of single response (F-13)

**Sensor-specific:**

- Test mode: capture events to JSON for replay (F-14)
- Sensor metrics needed for health assessment (F-15)
- Suppression: sensor-level vs salience-level architectural decision (F-16)
- Streaming delivery pattern is confirmed real use case (F-17)
- Overlapping/duplicate data across app events needs dedup strategy (F-18)
- Solution/cheat data needs classification (evaluation_only) (F-19)
- Initial connection event flood: informational vs actionable distinction needed (F-20)
- App-buffered backfill events need historical flag (F-21)

---

## PoC 2: Multi-Sensor Pipeline

### Question to answer

Can GLADyS operate as a multi-sensor system — multiple sensors from different domains, written in different languages, running concurrently with events processed correctly and learning scoped to domains?

### Prerequisites

- PoC 1 convergence test passes
- Planning session incorporating PoC 1 lessons learned

### Workstreams

#### W5: Event Volume Management

Address the accuracy-latency tradeoff under real-world event volume. PoC 1 operates at manual/low volume; PoC 2 must handle sustained sensor output.

Implements:

- Concurrent event processing: configurable worker pool in orchestrator (N>1)
- Event deduplication: 3 layers (sensor, orchestrator cache, habituation)
- Suppression architecture: capability, flow control, habituation
- Executive concurrent LLM request handling

Design basis: `docs/design/questions/resource-allocation.md`

#### W6: Second Sensor

Add sensors from different domains. Validates protocol-first architecture, cross-domain behavior, event contract generality, and concurrent sensor handling. Protocol-first: language-agnostic contract with per-language SDKs (Python base class, Java SDK, JS/TS SDK).

Design basis: `docs/design/SENSOR_ARCHITECTURE.md`

### What to Prove

| # | Claim | How to test | Success criteria | Abort signal |
|---|-------|------------|-----------------|--------------|
| 1 | **Multiple sensors operate concurrently** | RuneScape (game) + Gmail (email) sensors running simultaneously for extended session. Both emit events. | Event count submitted = event count in `episodic_events` (stored) + events with timeout responses. No unaccounted events. Queue depth returns to 0 within 60s of last event. | Pipeline can't keep up with concurrent sensor output. Silent event drops despite bug fixes (#93, #94). |
| 2 | **Sensor protocol and SDKs are viable** | (a) Java sensor (RuneScape) registers and publishes. (b) JS/TS sensor (Gmail) registers and publishes. (c) Developer builds sensor from SDK + docs without needing GLADyS internals. | Two sensors in different languages running successfully. No unplanned protocol or proto changes required during implementation. Developer can build sensor from SDK + `SENSOR_ARCHITECTURE.md` alone. | SDK abstraction doesn't cover real sensor needs. Protocol requires fundamental redesign. Event schema inadequate at some pipeline stage. |
| 3 | **Source-domain heuristic scoping** | (a) Submit RuneScape events, verify only RuneScape-source heuristics considered during matching. (b) Submit email events, verify only email-source heuristics considered. (c) Verify heuristics correctly fire within their own domain. | Zero cross-domain heuristic matches (RuneScape heuristic never fires on email event and vice versa). Within-domain: same test events that matched at 10 heuristics still match the correct heuristic at 50+. | Source filtering too coarse (still cross-matches) or too fine (legitimate within-domain matches blocked). |
| 4 | **Source filtering improves heuristic success rate** | Run same event set with source filtering enabled vs disabled. Compare heuristic fire accuracy (correct match / total fires). | Measurably higher success rate with source filtering enabled. Fewer false positive matches. | No measurable difference — source filtering adds overhead without benefit. |
| 5 | **Event volume is manageable** | RuneScape sensor at realistic volume (100+ events/tick). Measure end-to-end latency, throughput, salience scoring time. | Heuristic path <500ms p95. LLM path <10s p95. Salience scoring doesn't become pipeline bottleneck. `QueryMatchingHeuristics` latency <20ms p95. | Salience scoring scales linearly with heuristic count. Pipeline throughput insufficient for realistic sensor volume. |
| 6 | **Executive handles concurrent LLM requests** | Multiple sensors trigger LLM-path decisions simultaneously. | Concurrent requests processed without serialization. Response quality comparable to serial processing. No request starvation. | Concurrent LLM requests cause errors, quality degradation, or deadlocks. |
| 7 | **Feedback model works under multi-sensor load** | Submit events across domains, give positive/negative feedback. Verify confidence adjustments per heuristic, scoped to correct domain. | Positive feedback increases heuristic confidence. Negative feedback decreases it. Feedback from RuneScape events does not affect email heuristic confidence and vice versa. | Cross-contamination in confidence updates. Feedback from one domain inappropriately affects another. |
| 8 | **Salience system performs under real load** | Run salience scoring against growing heuristic set with source filtering. Measure query latency and ranking quality. | `QueryMatchingHeuristics` <20ms p95. Correct heuristic ranked #1 for known test events. No rank displacement as heuristic set grows from 10 to 50+. | Embedding space crowded — false-positive near-matches dominate despite source filtering. |

### Design Questions to Answer

These are architecture-level questions PoC 2 needs to resolve through implementation experience:

1. Does source-based filtering actually prevent cross-domain heuristic pollution, or does it need additional mechanisms?
2. Can configuration-injected flow control work across language boundaries in practice?
3. Is the sensor protocol contract sufficient, or does real implementation reveal gaps?
4. Can the Executive handle concurrent LLM requests without response quality degradation?
5. Does the browser extension driver model work for Gmail?
6. Is the event schema (intent, evaluation_data, structured fields) adequate through the full pipeline?

### Convergence Test

All workstreams converge on this scenario:

1. RuneScape sensor (Java, push pattern) and Gmail sensor (JS/TS, poll pattern) both register and start
2. RuneScape emits game events at realistic volume (100+ events/tick via `PublishEvents`)
3. Gmail sensor emits email events concurrently
4. Events from both sensors are stored — event accounting balances (submitted = stored + timed-out, no unaccounted drops)
5. RuneScape event matches a RuneScape-source heuristic — heuristic fires, LLM skipped
6. Gmail event has no matching heuristic — routes to Executive (LLM path). Verify no RuneScape heuristics were considered.
7. User gives positive feedback on Gmail LLM response → new heuristic created with email source
8. Submit similar Gmail event → new email heuristic fires. Verify RuneScape heuristics unaffected.
9. Give negative feedback on a RuneScape heuristic → confidence drops. Verify email heuristic confidence unchanged.
10. Throughout: heuristic path <500ms p95, LLM path <10s p95, `QueryMatchingHeuristics` <20ms p95

### Baseline Metrics (from PoC 1)

Documented before PoC 2 implementation begins. These are the "before" numbers for comparison.

| Metric | PoC 1 value | Notes |
|--------|------------|-------|
| Heuristic success rate | ~0-3% | Nearly all events routed to LLM. Source filtering not implemented. |
| Heuristic count | Low (<20) | Single domain (Sudoku), manual event submission |
| Cross-domain false positives | Not measurable | Single domain only |
| Concurrent sensors | 0 | Single sensor, manual submission |
| Event throughput | Manual | No sustained sensor output |
| LLM concurrent requests | 1 | Serial processing only |

### Definition of Done

PoC 2 is done when:

- All 8 claims have been tested (no untested claims)
- No abort signals are active (an abort signal that fired, was addressed via design rethink, and the claim subsequently passed counts as resolved)
- All 6 design questions have documented answers
- Lessons learned section is populated
- Convergence test passes

An abort signal is not failure — it's a loop back to think → design → build (per PoC lifecycle process). PoC 2 only fails if a claim cannot pass after rethink, which becomes a lesson learned that reshapes the future roadmap.

### Deferred to Future PoC

The following claims were in the original PoC 2 plan but require sustained operation and significant heuristic volume that PoC 2 won't achieve. PoC 2 builds the infrastructure; a future "Learning Maturity" PoC validates these.

- **Learning works over time**: LLM fallback rate decreasing across sessions, heuristic reuse >50% session-over-session
- **Sleep-mode consolidation**: Merge, demote, staleness decay (ADR-0010 §3.3.4)
- **Heuristic scale at 100+**: Rank stability and query performance at large heuristic counts

### What was proven

*(To be populated after PoC 2 completes)*

### What was NOT proven (known gaps)

*(To be populated after PoC 2 completes. Be honest — see PoC 0 for the standard.)*

### Lessons Learned

*(To be populated after PoC 2 completes. Use F-XX format per PoC 1 convention. Organize by category.)*

---

## Future PoC Roadmap

Each item below is a candidate for its own PoC. Ordering, scope, and claims are determined during each PoC's planning session, informed by lessons learned from the previous PoC. The PoC 0→1→2 pattern holds: plan, implement, validate, learn, then plan the next one.

### PoC 3 (likely scope)

PoC 2 lessons learned impact + domain skills + orchestrator-executive improvements. Specific claims defined during PoC 3 planning session.

### Candidate PoC Topics

Each of these is substantial enough to be its own PoC. Some may combine; others may split further based on what earlier PoCs reveal.

| Topic | Description | Key questions |
|-------|-------------|---------------|
| **Learning maturity** | Learning over time, sleep-mode consolidation (merge/demote/decay), heuristic scale at 100+. Deferred from PoC 2. | Does LLM fallback rate decrease across sessions? Does consolidation preserve accuracy? |
| **Domain skills & pre-built heuristics** | Skill plugin interface, domain-specific confidence evaluation, pre-built heuristic packages. | Can skills accelerate learning? Is the plugin interface practical? |
| **Skill packs** | Sensor + domain skill + heuristics as a deployable unit. | Does the pack abstraction work end-to-end? |
| **Actuators** | The "doing" side — response execution, conflict resolution, output routing. | Can GLADyS take actions, not just observe? |
| **Response modeling** | How responses are structured, selected, and delivered. | What does a "response" look like beyond text? |
| **Personality** | Behavioral profiles that affect tone, reasoning style, response preference. | Does personality meaningfully change behavior, or is it just a prompt prefix? |
| **Episodic memory** | Structured episode detection, storage, and retrieval beyond raw event storage. | Can the system reason about sequences of events? |
| **Implicit feedback** | Feedback signals beyond explicit user input — behavioral, temporal, contextual. | Can the system learn without being told? |
| **Tuning** | System optimization, threshold calibration, confidence bootstrapping refinement. | What are the right knobs, and what values work? |
| **Cross-domain reasoning** | Executive responses that integrate information from multiple sensor domains. | Can retrieval scope queries across domains effectively? |

### Product Readiness (separate from technical PoC)

| # | Question | How to test | What we're looking for |
|---|----------|------------|----------------------|
| 1 | **Demonstrable to outsiders** | Someone outside the team watches the system handle a repeated scenario faster the second time, with a real sensor. | Observer understands what happened and finds it compelling without explanation of internals. |

This is product validation, not a technical proof. It depends on sufficient technical PoCs passing first.

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

### PoC 2: Multi-Sensor Pipeline Observability

- **Event accounting**: Submitted vs stored vs timed-out counts per sensor — verifies no silent drops (supports claim #1)
- **Latency metrics**: p50/p95/p99 for heuristic path and LLM path, visible per-session (supports claim #5)
- **Source filtering metrics**: Cross-domain match attempts vs blocks, within-domain match accuracy (supports claims #3, #4)
- **Concurrent LLM dashboard**: Outstanding request count, queue depth, per-request latency (supports claim #6)
- **Feedback scoping**: Per-domain confidence adjustment history — verify feedback stays within domain (supports claim #7)
- **Salience performance**: `QueryMatchingHeuristics` latency distribution, ranking quality metrics (supports claim #8)
- **Sensor dashboard / control plane**: Sensor registration, health, activate/deactivate, capture control (supports claim #2)

**CLI / scripts**:

- Load test harness: submit N events from M sensors simultaneously, report event accounting (submitted vs stored vs timed out)
- Source filtering comparison: run same events with/without source filtering, report accuracy difference
- Session metrics reporter: compute heuristic fire accuracy, false positive rate, per-domain breakdown

### Future PoCs

Tooling for each PoC is scoped during that PoC's planning session. The pattern: each PoC's claims determine what needs to be observable, which determines what tooling to build. Not pre-committed here.

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
| **Preprocessors** | Role defined (fast enrichment salience depends on), but no real sensor data to preprocess. | Real sensor produces data that needs enrichment before salience can evaluate it meaningfully, OR response accuracy suffers from raw event data quality. | PoC 1 or PoC 2 (depends on sensor choice and data quality) |
| **Context/Mode detection** | Needs an owner (Orchestrator or Salience). Design not started. | Second domain sensor added — system needs to distinguish contexts. | PoC 2 (multiple sensors/domains) |
| **Configuration subsystem** | Runtime config changes beyond .env-at-startup. Dashboard Settings tab needs a backend. | Settings tab is needed for practical use during testing. | PoC 1 or PoC 2 |
| **Plugin behavior enforcement** | "Immune system" for plugins. We control all plugins during PoC. | Third-party or community plugins considered. | Post-PoC 3 |
| **Episodic memory / EST** | Individual event storage is sufficient for PoC 2. Episode segmentation (boundary detection, episode summarization, cross-episode pattern extraction) layers on top of events, doesn't replace them. Research: `docs/research/event-segmentation-theory.md`. | PoC 2 W5 (volume management) reveals that individual event storage doesn't scale, OR heuristic extraction needs temporal context that single events don't provide. | Post-PoC 2 |
| **Brain subsystem audit** | Systematic review of brain regions mapped to GLADyS functions. Worth doing deliberately. | After PoC 1 when the learning system exists and we can compare design to implementation. | PoC 2 planning session |
| **Linux/WSL readiness** | Audit for Windows path assumptions. | Directory restructure (prerequisite phase). | Prerequisite phase |
| **Install package / dev setup** | Single-command setup. | New developer onboards, or setup friction slows iteration. | Any PoC |
| **Hot reload for Python gRPC** | Code velocity improvement. | Iteration speed becomes a bottleneck during implementation. | Any PoC |
| **Resource allocation research** | Formal models for accuracy-latency tradeoff (expected utility, cascade models, anytime algorithms). GLADyS System 1/2 is an instance of this class of problem. | PoC 1 heuristic threshold tuning reveals need for principled approach, or PoC 2 volume management needs theoretical grounding. | PoC 2 planning session |

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
