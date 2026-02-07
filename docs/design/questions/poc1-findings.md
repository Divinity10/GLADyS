# PoC 1 Findings & Design Questions

**Created**: 2026-02-06
**Status**: Captured, needs discussion
**Source**: Scott + Mike post-PoC 1 analysis session
**Feeds into**: PoC 2 planning, sensor contract design, extensibility work

---

## How to Use This Document

Each finding is numbered for reference (F-01, F-02, etc.). Findings are grouped by primary subsystem but many are cross-cutting. Each includes:
- **Observation**: What was seen during PoC 1
- **Impact**: What this means for the system
- **Design questions**: What needs to be decided
- **Affects**: Which subsystems / specs

Status key: `open` (needs design discussion), `captured` (documented, not yet actionable), `resolved` (decision made)

---

## Heuristic Matching & Source

### F-01: Source must carry significant weight in heuristic selection

**Status**: resolved
**Affects**: Sensor contract, Salience scorer, proto schema, heuristic storage

**Observation**: Heuristic matching without source context produces cross-domain false positives. A calendar event about "meeting in 5 minutes" should not match a gaming heuristic about "5 minutes until boss spawn." MiniLM-L6 embeddings alone can't distinguish these — they're semantically similar.

**Impact**: Source is not just metadata — it's a primary input to the matching algorithm. Currently `source` is a flat string in the proto Event message. It may be missing from the heuristic matching query path entirely (see #56, #99).

**Design questions**:
1. Should source be a hard filter (only match heuristics from same source) or a weighted signal (prefer same-source, allow cross-source at high similarity)?
   - **Resolved**: Hard filter for PoC 2 default. Config option for exact vs domain-level matching — domain-level match is genuinely new signal worth testing (distinct from PoC 1's "no filter"). Pluggable filter architecture so PoC 3 can swap in weighted/cross-domain matcher without architectural changes.
2. How granular is "source"? Sensor ID? Domain? Pack? (e.g., `runescape-sensor` vs `gaming` vs `runescape-pack`)
   - **Resolved**: Sensor decides source string per event. Flat string sufficient for PoC 2 (one sensor per domain). No proto changes needed.
3. Does the heuristic store its source context? If so, at what granularity?
   - **Resolved**: Already implemented. `HeuristicDetail.source` (memory.proto:417) and `QueryHeuristicsRequest.source_filter` (memory.proto:301) exist.
4. How does this interact with cross-domain reasoning (PoC 3 goal)?
   - **Resolved**: Cross-domain reasoning is context enrichment (executive having multi-source awareness), not heuristic matching. Hard filter doesn't conflict with PoC 3 goals.

**Related**: working_memory.md discovery ("MiniLM-L6 similarity too coarse for cross-domain"), #56, #99

---

### F-02: Heuristic-to-event matching needs to improve

**Status**: resolved
**Affects**: Salience scorer, event contract (raw_text quality), embedding strategy

**Observation**: Current matching quality is insufficient. Heuristics sometimes fire on wrong events or fail to fire on correct ones.

**Impact**: This is multi-causal. Possible factors:
- Embedding model limitations (MiniLM-L6)
- Missing source filtering (F-01)
- Inconsistent `raw_text` generation across sensors
- `condition_text` quality from heuristic creation (F-04)
- Similarity threshold tuning

**Design questions**:
1. How much of the matching problem is solvable by fixing source filtering (F-01) vs requiring a better embedding model?
   - **Resolved**: Source filtering (F-01) first — it eliminates the biggest class of false positives (cross-domain). Defer embedding model changes. Measure matching quality after source filtering lands. If within-domain matching is still poor, revisit embedding model for PoC 3.
2. Should `raw_text` generation follow a template/pattern per event type to improve embedding consistency?
   - **Resolved**: Yes, as convention not enforcement. Document best practices in sensor base class docs: natural-language sentences, not key-value pairs. No proto validation or enforcement. Sensors that follow guidance get better matching.
3. Should we log all candidate matches (not just winner) to diagnose matching quality? (POC_LIFECYCLE already suggests this)
   - **Resolved**: Yes, in dev mode only (same opt-in pattern as F-14). Log all heuristics above a minimum threshold with similarity scores, source, and filter pass/fail. Essential for evaluating whether F-01 source filtering solves the matching problem.

---

## Learning & Confidence

### F-03: Positive feedback should increase confidence on a gradient scale

**Status**: resolved
**Affects**: Learning strategy, confidence update algorithm

**Observation**: Liking a heuristic response should increase confidence, but by how much? First-time approval should count more than repeated approval of the same pattern.

**Impact**: Current Beta-Binomial update treats all positive feedback equally. A gradient scale (1st like = significant boost, 2nd = moderate, 3rd+ = diminishing) would better model trust-building.

**Design questions**:
1. Is this a modification to the Beta-Binomial parameters, or a separate scaling function applied before the update?
   - **Resolved**: Separate scaling function applied before the Beta-Binomial update. `effective_signal = raw_signal * decay(n)` where `n` is prior approvals. Composable, removable, doesn't complicate the core model. Decay function e.g. `1 / (1 + k * n)`.
2. Should the gradient be per-heuristic (Nth approval of THIS heuristic) or per-event-type (Nth approval of this TYPE of response)?
   - **Resolved**: Per-heuristic. Uses existing feedback history (alpha/beta counts). No new concepts or taxonomy required. Per-event-type would require defining event types, which doesn't exist yet.
3. Does this interact with the implicit feedback timing (F-11)?
   - **Resolved**: No architectural interaction — decay function is source-agnostic. Design principle: **implicit feedback weighted higher than explicit** (correctness > user happiness). Implicit = "it worked in practice"; explicit = "user opinion" (noisy, biased negative — users rarely give explicit feedback and when they do it skews negative). Each event allows **at most one implicit + one explicit** signal. Implicit is a single discrete signal (e.g., "user didn't undo within timeout"), NOT continuous accumulation (no "every second of non-complaint counts"). Both signals can coexist for the same event.

---

### F-04: Low-confidence heuristics should be included in LLM prompt as options

**Status**: resolved
**Affects**: Decision strategy, executive prompt design

**Observation**: When a low-confidence heuristic reasonably matches an event, its response should be presented to the LLM as a neutral option — not as the answer, but as "here's what was tried before."

**Impact**: If the LLM independently generates a near-identical response to a low-confidence heuristic, that's strong evidence the heuristic is good. This creates a new implicit signal: "LLM convergence."

**Design questions (all resolved)**:

1. **What similarity threshold qualifies as "reasonably matches" for inclusion?**
   **Resolved**: Cosine similarity confirmed as metric — the problem was embedding model (MiniLM-L6), not the distance function. Source filtering (F-01) is the biggest lever for match quality. Candidate inclusion threshold: **0.4** (configurable), applied after source filtering. Below the 0.7 heuristic firing threshold. Model upgrade deferred to PoC 2.

2. **How are heuristic options presented in the prompt?**
   **Resolved**: Show **condition text + action only**. No confidence scores, fire count, similarity scores, or age — all create anchoring bias. Candidates framed as "previous responses to similar situations (for context, not selection)." Order **randomized** to avoid positional bias. Explicit permission for LLM to ignore them.

3. **If LLM response is near-identical to a heuristic option, what's the confidence boost?**
   **Resolved**: **No direct confidence boost.** Record convergence in `DecisionResult.metadata` only. LLM saw the candidates, so agreement isn't fully independent (statistical contamination). Real confidence signal comes from user feedback. F-25 sleep-cycle provides clean convergence signals (no candidates shown). Metadata format: `{"convergence": {"converged_heuristic_id": "...", "similarity": 0.82}}`.

4. **If LLM response diverges from all heuristic options, is that negative signal?**
   **Resolved**: **No.** LLM has more context than the heuristic. A better response for this specific situation doesn't mean the general-purpose heuristic is wrong. Would create a ratchet effect (converge=boost, diverge=penalize → LLM becomes sole arbiter without user input).

5. **How many heuristic options before prompt quality degrades?**
   **Resolved**: **Max 5, default 3**, configurable via `HeuristicFirstConfig.max_candidates`. If more than max pass the inclusion threshold, take top N by similarity, then randomize order. Budget: ~30-50 tokens per candidate. With gemma:2b (~8k context), 5 candidates fit comfortably.

**Prompt approach**: **Approach A** — generate with candidates as context, not as a selection menu. Candidates described as "previous responses to similar situations." LLM generates independently; post-processing compares for convergence via embedding similarity. Not Approach B (evaluate-then-generate) which creates anchoring and pollutes the convergence signal.

**Personality in prompt**: Goes in **system prompt** (instruction), not alongside candidates (data). Clean separation between behavioral guidance and domain knowledge.

**Data model changes for Decision Strategy:**
- `DecisionContext.suggestion` → `DecisionContext.candidates: list[HeuristicCandidate]`
- New `HeuristicCandidate` dataclass: `heuristic_id`, `condition_text`, `suggested_action`
- `HeuristicFirstConfig` gains: `candidate_inclusion_threshold: float = 0.4`, `max_candidates: int = 3`

**Directly relevant to**: `impl-decision-strategy.md`, `DECISION_STRATEGY.md`

---

### F-05: Confidence must never reach 0 or 1

**Status**: resolved
**Affects**: Learning strategy, confidence update algorithm

**Observation**: Nothing should ever be absolutely certain or absolutely impossible. A confidence of 1.0 means "this will always work" — which is never true. A confidence of 0.0 means "this will never work" — also never true (context might change).

**Impact**: Beta-Binomial with proper priors naturally prevents exact 0 or 1, but the bounds should be explicit: e.g., [0.01, 0.99] or [0.05, 0.95].

**Design questions**:
1. What are the hard bounds? `[0.05, 0.95]` seems reasonable.
   - **Resolved**: `[0.05, 0.95]` as defaults. Configurable — we don't know what values produce best results yet. 0.05 floor preserves recoverability (~4-5 consecutive positives to climb back to 0.3). 0.95 ceiling consistent with LLM confidence ceiling of 0.8 (F-06).
2. Should this be configurable or fixed?
   - **Resolved**: Configurable. Answered together with Q1.
3. Does this need to be in the proto definition or just enforced in the update logic?
   - **Resolved**: Enforce in update logic only. Proto is a transport contract — clamping is a learning policy decision. Belongs where confidence is calculated, not where it's transmitted. Configurable bounds may change at runtime or per-domain in PoC 3. Proto allows full `[0.0, 1.0]` range for forward compatibility.

---

### F-06: LLM-generated response confidence seems unusually high

**Status**: resolved (PoC 2 implementation)
**Affects**: Executive, decision strategy, confidence semantics

**Observation**: The LLM reports high confidence in its responses, but it's unclear what "confidence" means in this context.

**Impact**: If confidence means "how sure am I this text is grammatically correct" — of course it's high. If it means "how confident am I this response will produce the desired outcome for the user" — it should be much lower, especially for novel situations.

**Design questions (all resolved)**:

1. **What should LLM response confidence measure?**
   **Resolved**: Two distinct measures: `predicted_success` = "probability this response leads to the goal state" (requires goal context — see F-07). `prediction_confidence` = "how much information do I have to make this prediction" (epistemic uncertainty). Both need goal context to be meaningful.

2. **Should we calibrate LLM confidence externally?**
   **Resolved**: Yes. Keep asking the LLM but improve the prompt (define "success" explicitly with goal context) and cap raw LLM confidence at **0.8** (`HeuristicFirstConfig.llm_confidence_ceiling`). No LLM response should claim >80% confidence without user validation.

3. **Does the confidence definition need to be in the LLM prompt explicitly?**
   **Resolved**: Yes. The prediction prompt must define success in terms of goals (F-07), ask "what could go wrong?" to force failure mode consideration, and specify the scale means "probability of achieving the stated goal." Improved prompt is a config value (`prediction_prompt_template`).

4. **How does this interact with heuristic initial confidence (0.3)?**
   **Resolved**: LLM-path responses that become heuristics (via positive feedback) start at 0.3 regardless of LLM self-assessment. The 0.3 reflects "never been validated by a user." LLM's prediction is stored in the trace for analytics but does NOT override the bootstrap value.

---

## Goals & Response Selection

### F-07: Goal statement needed in LLM prompt

**Status**: resolved (minimal for PoC 2, full design deferred to F-08)
**Affects**: Executive, sensor contract (goal context), orchestrator context

**Observation**: Without a goal statement, the LLM generates generic responses. Quality improves significantly when the system knows what the user is trying to achieve.

**Impact**: This requires goals to be part of the system context. Where do goals come from? How are they selected per-event?

**Design questions**:

1. **Where are goals stored?**
   **Resolved (PoC 2 minimal)**: Static per-domain goals via config file or environment variable (e.g., `EXECUTIVE_GOALS="Survive combat;Level up efficiently;Have fun"`). Or passed from orchestrator in ProcessEvent request (requires proto change). Full goal storage design deferred to F-08.

2. **How is a goal selected for a given event?**
   **Deferred to F-08**: For PoC 2, all active goals are included in every prompt. Dynamic goal selection per event is a dedicated design session (F-08).

3. **Can multiple goals be active simultaneously?**
   **Resolved**: Yes. `DecisionContext.goals: list[str]` supports multiple concurrent goals.

4. **How are conflicting goals handled?**
   **Deferred to F-08**: PoC 2 doesn't resolve conflicts — it includes all goals and lets the LLM balance them. Explicit priority/conflict resolution is PoC 3.

**Decision Strategy impact**: Add `goals: list[str]` to `DecisionContext`. Goals are injected into the system prompt (after personality, before event data). The strategy doesn't care where goals come from — that's the caller's responsibility.

**Related**: SUBSYSTEM_OVERVIEW.md §7 lists "Goal management — where do user goals come from?" as unspecified

---

### F-08: Goal selection for events is unresolved

**Status**: open — **needs dedicated design session**
**Affects**: Executive, orchestrator, potentially sensor contract

**Observation**: Even if goals are defined, how does the system pick which goal applies to a given event? A combat event might relate to "survive" or "level up" or "have fun" depending on context.

**Impact**: This is a core reasoning problem. It's related to context detection (PoC 2 deferred item) and salience (goal_relevance dimension in the vector).

**Design questions**:
1. Is goal selection an Executive responsibility (reasoning) or an Orchestrator responsibility (routing)?
2. Can salience scoring include goal matching? (The `goal_relevance` dimension exists but isn't implemented)
3. Should domain skills define goal-event mappings? (e.g., RuneScape skill knows "combat event → survival goal")
4. Is this PoC 2 scope or PoC 3 scope?

---

### F-09: Non-exclusive and combinatorial response selection

**Status**: captured — current Protocol accommodates future extension; **needs dedicated design session** for PoC 3
**Affects**: Decision strategy, executive, response model

**Observation**: Not all responses are mutually exclusive. Example scenario (wounded teammate):
- Option 1: Bind wound (5% health improvement)
- Option 2: Healing potion (50% health improvement)
- Option 3: Point and laugh (0% health, but funny)
- Option 4: Sacrifice teammate (kills them, but your survival +40%)

Options 1 & 2 are complementary (55% together). Option 3 can combine with any. Option 4 excludes 1 & 2.

**Impact**: Current model assumes one response per event. Real situations have combinatorial response spaces where the optimal action is a SET of responses, not a single one.

**Design questions**:
1. How does the system represent response compatibility? (exclusion groups? dependency graph?)
2. Should the LLM evaluate combinations, or should a separate optimizer compose them?
3. Is this a PoC 2 concern or PoC 3? (Likely PoC 3 — current system can function with single-response model)
4. How does this interact with multi-dimensional response scoring (F-10)?

---

### F-10: Multi-dimensional response scoring

**Status**: captured — `metadata: dict[str, Any]` accommodates additional scoring dimensions without Protocol changes
**Affects**: Decision strategy, executive, SalienceResult model

**Observation**: Responses may need scoring on multiple dimensions, not just overall confidence. Example: option scoring 10% + 30% = 40% improvement vs single option at 35%.

**Impact**: This extends beyond scalar confidence into response utility. Related to the SalienceResult vector model — if salience has dimensions, should responses also have dimensional scores?

**Design questions**:
1. What dimensions? Effectiveness, risk, humor, time-cost, reversibility?
2. How are dimensional scores aggregated? Weighted sum (like salience)? User preference-weighted?
3. Is this the same problem as F-09 (combinatorial selection) or separate?

---

## Feedback & Timing

### F-11: Feedback windows differ by type

**Status**: resolved
**Affects**: Learning strategy, implicit feedback design

**Observation**: Manual feedback (user explicitly approves/rejects) needs a much longer window than implicit feedback (user undoes an action or ignores a suggestion). But what unit measures the window — time? Number of subsequent events? Some combination?

**Impact**: Currently unclear how feedback attribution works temporally. If a user gives thumbs-up 30 minutes later, does it count? If 3 events pass without complaint, is that implicit approval?

**Design questions**:
1. What's the manual feedback window? Time-based (e.g., 5 minutes)? Session-based? Unlimited until next event?
   - **Resolved**: Unlimited window, last click wins. Corrections allowed — UI displays most recent submission. Confidence model uses latest value only (not cumulative). PoC 2: no anti-spam (trust devs). Production: revisit UX guardrails if needed. At most one explicit feedback *value* applies per event at any time (the latest).
2. What's the implicit feedback window? Time-based? Event-count-based? Both?
   - **Resolved**: Time-based only, configurable default (30 seconds). Event-count is unreliable across domains (3 events = 2 seconds in gaming, 3 hours in home automation). Time is intuitive to configure and reason about. Single mechanism = less to debug.
3. Should the window vary by domain? (Gaming events are rapid — 3 events might be 2 seconds. Home automation events are sparse — 3 events might be 3 hours.)
   - **Resolved**: Yes, via per-domain config. The configurable timeout from Q2 handles this — each domain sets its own implicit feedback timeout. No separate mechanism needed.
4. How does this interact with the gradient confidence scale (F-03)?
   - **Resolved**: No interaction with decay function (F-03 gradient is source-agnostic). Implicit and explicit are **independent channels** — both fire regardless of each other. Contradictory signals are expected and handled by weighting: implicit > explicit (F-03 Q3: correctness > user happiness). Example: user says "Bad" but doesn't undo → implicit positive + explicit negative. Both are true — "it worked but user didn't like it." The confidence model receives both and weights implicit higher. No timer cancellation, no coupling between feedback paths. For PoC 2, explicit feedback corrections (last click wins) simply overwrite the previous explicit value.

**Related**: ADR-0010 §3.10 defines implicit signal types but not windows

---

## Executive Architecture

### F-12: Multi-threaded LLM calls for scenario exploration

**Status**: captured — deferred to PoC 3+, covered by F-04 and F-25
**Affects**: Executive architecture, latency budget

**Observation**: Sometimes the Executive should explore multiple scenarios simultaneously. If done serially, latency is too high (each LLM call is 500-2000ms).

**Impact**: This is an architectural change. Currently the Executive processes one event with one LLM call. Parallel exploration means multiple concurrent LLM calls per event, then selecting among results.

**Resolution**: Two distinct problems here — scenario exploration and concurrent event processing:

**Scenario exploration** (multiple LLM calls per event): Deferred to PoC 3+.
- **F-04** handles it in a single call — candidates as context, LLM considers multiple options without parallel calls
- **F-25** sleep-cycle handles offline exploration with enriched context, no latency pressure
- Parallel live LLM calls add resource management, result reconciliation, and cost complexity — especially on local hardware (local-first constraint)

**Concurrent event processing** (multiple events in-flight simultaneously): **PoC 2 scope.**
- Current `EventQueue._worker_loop()` processes events serially — dequeues one, awaits full processing (including LLM call), then dequeues next
- With multiple sensors in PoC 2, events arrive simultaneously. Serial processing creates unacceptable latency (5 queued events × 2-5s LLM = 10-25s for last event)
- Fix is at the orchestrator layer: multiple concurrent worker tasks or `asyncio.gather` with a semaphore. The executive already supports concurrency (gRPC server has 4 workers, LLM provider is async, decision strategy is async)
- Concurrency limit should be configurable (default 3-4, bounded by local LLM throughput)

**Design questions**:
1. ~~When should the Executive explore multiple scenarios vs commit to one?~~ **Deferred**: F-04 single-call approach for PoC 2.
2. ~~How many concurrent explorations?~~ **Deferred**: Moot until parallel calls are needed.
3. ~~Does this interact with F-04?~~ **Resolved**: Yes — F-04 makes parallel calls redundant for the stated problem.
4. ~~Is this PoC 2 or PoC 3 scope?~~ **Resolved**: PoC 3+ at earliest.

**Related**: resource-allocation.md concurrent processing question

---

### F-13: Should LLM provide multiple response options with confidence levels?

**Status**: captured — a future `MultiOptionStrategy` can implement this behind the current Protocol abstraction
**Affects**: Executive, decision strategy, response model

**Observation**: Instead of the LLM returning one response, it could return multiple options each with a confidence score. The system (not the LLM) then selects based on goals, risk tolerance, and response compatibility.

**Impact**: Changes the Executive→Orchestrator contract. Currently one response per event. This would be N responses with metadata.

**Design questions**:
1. How many options should the LLM generate? (3-5 seems reasonable)
2. Who selects — the system automatically, or the user?
3. How does this interact with F-09 (combinatorial selection)?
4. Does this replace or complement F-12 (parallel LLM exploration)?

---

---

## Sensor-Specific Findings

### F-14: Test mode that captures events to JSON

**Status**: resolved
**Affects**: Sensor base class, testing infrastructure

**Observation**: Need test modes that capture data to JSON for replay at two distinct boundaries in the pipeline. Required for testing, development, and post-hoc analysis.

**Impact**: This is different from the existing `--mock` mode (which reads FROM a JSON file). This is capture mode — record live data TO a file. Both modes should exist at each boundary: capture (record) and replay (mock).

#### Two capture/replay boundaries

**1. Driver → Sensor boundary**: Capture what the driver sends to the sensor. Replay feeds this data back into the sensor without needing the real app running.
- Enables sensor development and testing without the target application
- The driver uses its native transport (HTTP POST, file write, socket, etc.) — capture doesn't change that
- The **sensor's ingestion layer** serializes incoming driver data to JSON at capture time, regardless of the driver's native format
- Replay reads JSON and feeds it into the sensor's normalization pipeline — no transport simulation needed

**2. Sensor → Orchestrator boundary**: Capture the normalized GLADyS events the sensor sends to orchestrator/preprocessors. Replay feeds normalized events into the pipeline without needing a real sensor.
- Enables orchestrator/preprocessor/salience testing without real sensors
- Format is the GLADyS event contract (always JSON, same structure regardless of domain)
- Replay calls gRPC PublishEvents with the captured events

**Both captures are JSON, both written by the sensor.** The driver never knows capture is happening — it continues using its native format. The sensor handles all serialization. This means replay at both levels is generic: read JSON, feed into the appropriate pipeline stage. The base class can fully implement both.

#### Capture mode constraints

Capture is a **troubleshooting/dev mode**, not always-on. It must be explicitly enabled and rate-limited to prevent runaway disk usage.

**Stop conditions (whichever hits first):**
- **Time-based**: Capture for N seconds/minutes (e.g., `--capture-duration 60s`)
- **Record-based**: Capture N events (e.g., `--capture-count 500`)

Both settings should be configurable. Capture stops automatically when either limit is reached.

**Design questions**:
1. Should capture/replay be a base class feature (all sensors get it for free)?
   - **Resolved**: Yes. Both capture levels are JSON in/out. The base class knows when data arrives from the driver (ingestion layer) and when normalized events are published. Replay reads JSON and feeds into the pipeline at the appropriate stage. No domain-specific logic needed — sensors get it for free.
2. ~~Capture parameters: max events? max time? max file size?~~ **Resolved**: Time-based + record-count-based, whichever hits first. Must be explicitly enabled.
3. File format: JSONL (one event per line, appendable) or JSON array (structured but harder to stream)?
   - **Resolved**: JSONL. Each line includes a capture timestamp. Appendable (crash-safe — partial capture still has complete records), streamable (can `tail -f` during capture), trivial to parse line-by-line. JSON arrays require reading the entire file to parse and need closing bracket management if capture is interrupted.
4. ~~For driver-level capture, who captures — the driver itself or the sensor's ingestion layer?~~ **Resolved**: Sensor's ingestion layer captures driver data. Drivers must stay lightweight — capture logic belongs in the sensor (Python), not duplicated across driver languages.
5. Should replay support speed control?
   - **Resolved**: Default is **original timing** — replay preserves the inter-event deltas from capture. Each JSONL record has a timestamp; replay computes the delta to the previous record and waits that duration before emitting. Optional `--replay-speed` multiplier (e.g., `2x` for double speed, `0.5x` for half speed). No "max speed" dump mode as default — flooding the orchestrator queue guarantees timeouts and produces unrealistic test conditions. The point of replay is realistic live testing.

---

### F-15: Sensor metrics for health and quality assessment

**Status**: resolved
**Affects**: Sensor base class, sensor dashboard (design question #62), manifest

**Observation**: Need basic metrics to assess how a sensor is performing. Two levels:
- **Driver metrics**: Is the driver missing app-specific events? (e.g., RuneLite fires an event but the driver didn't capture it)
- **Sensor metrics**: Events received, events published, events dropped/filtered, latency, error counts

**Impact**: Without metrics, a misconfigured or degraded sensor is invisible. The sensor dashboard design question (#62) needs these metrics to display.

#### Metrics schema

**Sensor metrics** (base class maintains in-memory counters):

| Metric | Type | Description |
|--------|------|-------------|
| `events_received` | counter | Raw events from driver |
| `events_published` | counter | Normalized events sent to orchestrator |
| `events_filtered` | counter | Intentionally suppressed (F-16) |
| `events_errored` | counter | Failed during processing |
| `last_event_at` | timestamp | Most recent event received |
| `started_at` | timestamp | Sensor start time |
| `avg_latency_ms` | gauge | Rolling avg processing latency |
| `error_count` | counter | Total errors (all types) |

**Driver metrics** (driver reports to sensor, sensor aggregates):

| Metric | Type | Description |
|--------|------|-------------|
| `driver.events_handled` | counter | App events the driver captured |
| `driver.events_dropped` | counter | App events the driver couldn't capture |
| `driver.errors` | counter | Driver-side errors |
| `driver.last_report_at` | timestamp | Last time driver sent metrics |

Driver sends metrics to sensor via existing transport (HTTP POST, socket, etc.) — a different message type alongside events. Driver metrics stored as JSONB since different drivers report different things (RuneLite has app-specific categories, calendar sensor doesn't).

#### Delivery: event subscription model

Sensor emits metrics as `system.metrics` events through the existing `PublishEvents` path. These are tagged as `internal` (F-19 intent) — they never touch salience or executive. The orchestrator routes `system.*` events to system handlers, not the salience pipeline.

**Subscription model**: Build event-subscription routing now. Orchestrator subscribes to `system.metrics` initially (writes to DB). Can move to a dedicated metrics service later without changing the sensor side.

**Persistence**: `sensor_metrics` table. One row per metrics push (every 30s configurable via `heartbeat_interval_s`). Schema: sensor_id, timestamp, sensor counters as columns, `driver_metrics` as JSONB. Rolling retention (e.g., 7 days raw, aggregate to hourly after that).

**Dashboard (#62)**: Queries `sensor_metrics` table directly.

#### Manifest rate info

**All rate settings are per-sensor, not global.** Each sensor has its own domain characteristics — a global rate would be meaningless across sensors with fundamentally different event patterns.

**`heartbeat_interval_s`** (required, per-sensor): How often the sensor reports, even when idle. Dead sensor detection: no heartbeat within 2× interval = presumed dead. This is the only rate info with a PoC 2 consumer.

**`poll_interval_s`** and **`driver_tick_rate_s`** (optional, per-sensor): Document sensor characteristics. No consumer in PoC 2. The orchestrator could use these for capacity planning later — that's PoC 3+ scope.

**Anomaly detection**: Learned from historical data in `sensor_metrics`, not from declared rates. Actual event rates vary too much by context (combat vs idle, meeting time vs midnight). Simple threshold for PoC 2 (e.g., error rate > 3× rolling average).

**Design questions**:
1. What metrics should every sensor report?
   - **Resolved**: See metrics schema above. Split events_dropped into events_filtered (intentional, F-16) and events_errored (failures). Added avg_latency_ms as early warning for degradation.
2. Should driver-level metrics be reported through the sensor?
   - **Resolved**: Yes. Driver collects its own metrics (events handled, dropped, errors) and sends them to the sensor via existing transport. Sensor aggregates and reports everything. Drivers stay lightweight — collection logic in driver, aggregation/reporting in sensor.
3. How are metrics exposed?
   - **Resolved**: Event subscription model. Sensor emits `system.metrics` events via `PublishEvents`. Orchestrator subscribes and writes to `sensor_metrics` DB table. No polling. Sensor fires and forgets. Dashboard queries DB. Subscription model built now; orchestrator is first subscriber, can offload to dedicated service later.
4. Should the manifest declare expected event rates?
   - **Resolved**: `heartbeat_interval_s` required (dead sensor detection). `poll_interval_s` and `driver_tick_rate_s` optional (documentation only, no PoC 2 consumer). Anomaly detection uses learned baselines from historical metrics, not declared rates — variance is too high for static declarations to be useful.

---

### F-16: System-directed event type suppression at sensor level

**Status**: resolved
**Affects**: Sensor contract, orchestrator→sensor communication, habituation model

**Observation**: The system should be able to tell a sensor to stop capturing specific event types. Example: RuneScape emits sound events, which are probably useless unless a future audio preprocessor exists.

**Impact**: This raises a fundamental question: should suppression happen at the sensor level or the salience level?

- **Sensor-level suppression**: Prevents the event from being recorded at all. Saves bandwidth, storage, and processing. But: we lose the ability to retroactively analyze suppressed events if we later decide they're useful.
- **Salience-level suppression (habituation)**: Event is captured and stored but not routed to Executive. Preserves the data for future analysis. But: still costs bandwidth and storage for events we're ignoring.

#### Resolution: Three layers, each solving a different problem

**Layer 1 — Capability suppression (static, config-driven):**
"Can the system even process this event type?" Sound events with no audio preprocessor = useless. This is a configuration fact, not learned or adaptive. Sensor manifest declares event types with `enabled: true/false` defaults. Per-sensor config can override. Reversible via config change.

```yaml
event_types:
  - type: "player.position"
    enabled: true
  - type: "player.combat"
    enabled: true
  - type: "audio.sound_effect"
    enabled: false  # no audio preprocessor yet
```

"Measure before optimizing" (ADR-0004) doesn't conflict — this isn't optimization, it's capability. You don't measure to know sound events are useless without an audio processor. F-14 capture mode covers "record everything temporarily" when needed.

**Layer 2 — Flow control / back-pressure (dynamic, automatic):**
Inspired by TCP BBR (Bottleneck Bandwidth and Round-trip propagation time). Model-based, not loss-based — uses latency increase as early congestion signal, doesn't wait for events to be dropped/timed out.

| TCP/BBR Concept | GLADyS Equivalent |
|-----------------|-------------------|
| Bandwidth | Orchestrator throughput (events/sec) |
| RTT | `PublishEvents` response latency |
| Queue buildup | Orchestrator event queue → latency increase |
| Packet loss | Event timeout (too late — want to avoid) |
| BDP (optimal point) | Keep orchestrator busy without queue buildup |

**Sensor self-regulates using response latency:**
- Base class tracks `PublishEvents` response time (rolling avg + min baseline)
- Latency increase → orchestrator is queueing → reduce publish rate
- Latency returns to baseline → increase rate (probe for available capacity)
- Sensor decides HOW to throttle (domain-specific: gaming sensor drops position updates first, keeps combat events)
- **No orchestrator→sensor communication needed** for primary flow control

**Explicit orchestrator hints as secondary mechanism** for non-observable conditions (restart, maintenance). Piggybacked on `PublishEvents` response as a `throttle_hint` field.

**PoC 2**: Simple threshold-based implementation (latency > N× baseline → reduce rate). Sensor base class provides default; subclasses override with domain-specific priority.

**PoC 3+**: Full BBR-style probing phases, per-event-type priority during throttling, automatic congestion pattern learning from metrics history.

**Layer 3 — Salience-level suppression (habituation):**
"Is this event interesting right now?" Already designed in the salience model (habituation dimension). Learned, adaptive, operates on events that passed layers 1 and 2. Not changed by this finding.

#### Driver event toggles

The per-category toggle pattern (e.g., RuneLite enabled/disabled event categories) is the driver-level equivalent of Layer 1 capability suppression. Applies to any event-driven driver, not RuneScape-specific. For event-driven drivers, the sensor can send a control message via existing transport ("stop sending audio events"). For poll-based sensors, the sensor skips polling suppressed categories. F-15 `events_filtered` metric tracks suppression volume.

**Design questions**:
1. Should there be two suppression layers?
   - **Resolved**: Three layers. (1) Capability suppression: static, config/manifest-driven. (2) Flow control: dynamic, BBR-inspired, automatic using `PublishEvents` response latency. (3) Salience habituation: learned, adaptive (already designed).
2. Who controls sensor-level suppression?
   - **Resolved**: Layer 1 (capability) — sensor manifest + config. Layer 2 (flow control) — sensor self-regulates using response latency (BBR-style), with orchestrator hints as secondary mechanism. Orchestrator-driven automatic suppression of specific event types based on observed patterns is PoC 3.
3. Should the manifest declare suppressible event types?
   - **Resolved**: Yes. Manifest declares all event types with `enabled: true/false` defaults. Serves as both documentation and suppression config.
4. Is suppression reversible at runtime?
   - **Resolved**: Layer 1 — reversible via config change, sensor restart. Layer 2 — automatic (self-regulating, adjusts continuously).
5. Related to driver per-category toggles?
   - **Resolved**: Yes — same concept, general pattern for any event-driven driver. Not RuneScape-specific.

---

### F-17: Streaming connection for realtime sensors (prepare, don't build)

**Status**: captured (PoC 2 awareness, not PoC 2 implementation)
**Affects**: Sensor contract (delivery pattern), event interface model

**Observation**: A future sensor type captures realtime app window activity (screen capture, OCR) for apps that can't be modded. This requires a streaming connection — continuous data, not discrete events. Not needed now, but the contract should not preclude it.

**Impact**: The delivery pattern interface already has a `stream` type in the design ([resource-allocation.md:214](docs/design/questions/resource-allocation.md#L214)). This finding confirms it's a real use case, not hypothetical.

**Design questions**:
1. Does the event contract need any changes to accommodate streaming, or is `event_type: "stream"` + `sample_rate` + `sequence_id` sufficient as designed?
2. Should the base class have a streaming mixin, or is that a PoC 3+ concern?
3. Is the transport (gRPC bidirectional stream) adequate for continuous data, or would something like WebSocket/shared memory be needed?

**Decision for now**: Design the contract to accommodate it (don't close the door). Don't build it.

---

### F-18: Overlapping/duplicate data across app events

**Status**: resolved
**Affects**: Sensor contract, orchestrator caching, salience habituation
**Consolidates**: `cross-cutting.md` §36 (Event Condensation Strategy), `resource-allocation.md` (Dynamic Heuristic Behavior)

**Observation**: Game events often contain overlapping data. RuneScape example:
- Position event fires every game tick (contains entity position)
- Movement event fires when an entity moves (also contains entity position)
- Both events carry the same position data

Other overlapping patterns exist across event types.

**Resolution**: Three enforcement points at different pipeline stages. Not semantic dedup — each layer solves a different sub-problem.

**1. Sensor emit schedule (rate control, not semantic dedup)**
The sensor controls its own emit cadence, independent of the driver's event rate. The sensor buffers driver events and emits consolidated events on a timer or on meaningful change (domain-specific). This is rate control — the sensor decides *how often* to emit, not *what* to emit.

- Example: Driver fires position every tick (600ms). Sensor emits position every 5s unless movement exceeds a threshold.
- Authoritative source is domain-specific: the sensor's domain logic decides which event type owns which data fields.
- No `supersedes_event_id` needed — the sensor emit schedule eliminates the need for explicit event relationships.

**2. Orchestrator event-response cache (memoization, not buffering)**
A lightweight cache in the orchestrator maps `(event_type, source, content_hash) → response`. Before sending an event to the salience pipeline, the orchestrator checks the cache. Cache hit = return the cached response without re-evaluation. TTL-based invalidation.

- No event buffering or holding — events are processed immediately or served from cache.
- Simple TTL for PoC 2. Context-aware cache invalidation (e.g., invalidate position cache when movement event arrives) deferred to PoC 3.

**3. Salience habituation (already designed)**
Catches remaining redundancy that passes through the first two layers. Repeated similar events naturally score lower on novelty and higher on habituation.

**Observability at every layer**:
- Sensor: tracks events_received vs events_emitted (consolidation ratio)
- Orchestrator: tracks cache hits/misses per event type
- Salience: tracks habituation scores (existing)

**Design question answers**:
1. **Where does dedup happen?** All three layers, each solving a different problem. Sensor = rate control. Orchestrator = memoization. Salience = learned suppression.
2. **Event relationships?** No explicit `supersedes_event_id` or `related_event_ids`. Sensor emit schedule handles consolidation; cross-event relationships are implicit via temporal proximity and shared context.
3. **Authoritative source?** Domain-specific, handled by sensor domain logic. The sensor decides which event type is authoritative for each data field.
4. **Sensor-specific or platform?** Sensor emit schedule is domain-specific. Orchestrator cache and salience habituation are platform-level.

**Scope**: Sensor emit schedule + simple TTL cache in PoC 2. Context-aware cache invalidation in PoC 3.

---

### F-19: Solution/cheat data — flagging data not for normal use

**Status**: resolved
**Affects**: Sensor contract, event interface model, orchestrator stripping

**Observation**: Some apps contain both state and solution. Sudoku exposes the solution in the DOM. Math apps might show answers. Capturing this data helps GLADyS evaluate its own responses (was the hint correct?) but using it in a response would be cheating, not helping.

**Impact**: The event contract needs a way to flag data as "available for evaluation/learning but not for response generation." This is a data classification concern.

**Resolution**: Two-bucket model on the event. No per-field annotations — the event structure *is* the classification.

- **`data`**: Normal event data. Forwarded everywhere (salience, executive, learning, storage).
- **`evaluation_data`** (optional): Solution/answer data. Stored for learning and evaluation, stripped by the orchestrator before the executive sees it.

This replaces the proposed `visibility` enum. The structure itself encodes the classification — no metadata annotations needed. Sensor developers put data in the right bucket; the orchestrator enforces the boundary.

**`internal`** (sensor bookkeeping) is not a data classification — it's an event routing concern, already handled by F-15's `system.*` event routing. System events never enter the salience pipeline.

**Design question answers**:
1. **Field-level or event-level?**
   - **Resolved**: Two-bucket model — coarse-grained field-level. `data` + optional `evaluation_data` on the event. No per-attribute annotations (too complex, nesting problems, heavy burden on sensor devs). Not pure event-level either (avoids splitting one observation into two events).
2. **Classification values?**
   - **Resolved**: Two buckets replace the enum. `normal` → `data`, `evaluation_only` → `evaluation_data`, `internal` → already handled by F-15 (`system.*` routing).
3. **Who enforces?**
   - **Resolved**: Sensor labels (puts data in the right bucket). Orchestrator enforces (strips `evaluation_data` before passing to executive, stores both). Executive never sees it — defense in depth. Single enforcement point, easy to audit.
4. **Can classification change over time?**
   - **Resolved**: No runtime reclassification. "Show me the answer" is a user command — the executive handles it as a request, not a data visibility change. The solution data stays in `evaluation_data` forever. What changes is the user explicitly asking for it.
5. **Audit interaction?**
   - **Resolved**: No new audit system needed. Existing logging standard (`LOGGING_STANDARD.md`) covers it. Implementation guidance: log `evaluation_data_present: true/false` in structured context, never log `evaluation_data` content. The DB stores both buckets — that's the audit source if needed (PoC 3+), not logs.

**Scope**: Contract definition in PoC 2 (add `evaluation_data` field). Simple orchestrator strip before executive context. No runtime reclassification.

---

### F-20: Initial connection event flood — informational vs actionable

**Status**: resolved — mostly covered by F-16 (flow control) and F-18 (emit schedule)
**Affects**: Sensor contract (new `intent` field), orchestrator routing

**Observation**: When a driver connects, there's often an initial flood of events that then become sparse. Much of the flood is informational — no action needed. RuneScape example: user logs in → character appears → burst of inventory events. Only the login might need a response; the inventory events are context.

Two sub-problems:
1. **Informational vs actionable**: Need to indicate whether an event expects a response, is strictly informational (context), or unknown.
2. **Event bundling**: Multiple app events during a burst could be combined into a single GLADyS event (e.g., "user logged in with inventory: [...]"). This bundling logic belongs in the sensor or a sensor-specific preprocessor.

**Impact**: Without this distinction, the orchestrator will try to route every burst event through salience → executive, creating a processing storm on connect.

**Resolution**: One new contract element (`intent` field). Bundling and burst handling are already solved by F-16 and F-18.

**`intent` field on event contract:**
- `actionable`: May need a response. Routed through full pipeline (salience → executive).
- `informational`: Context only. Orchestrator stores in memory for future retrieval but does not route through salience → executive.
- `unknown` (default): Let salience decide. Sensors that don't know don't need to decide.

The sensor knows best whether an event expects a response. Inventory dump on login = `informational`. User takes an action = `actionable`. New sensor that hasn't classified its events yet = `unknown`.

**Design question answers**:
1. **Intent field?**
   - **Resolved**: Yes. `intent` with three values: `actionable`, `informational`, `unknown` (default). Lightweight — one field. Sensor sets it based on domain knowledge.
2. **Event bundling?**
   - **Resolved**: Already handled by F-18's sensor emit schedule. The sensor controls its own emit cadence and can consolidate multiple driver events into one emitted event. No new mechanism needed — bundling *is* the emit schedule applied to burst conditions.
3. **Burst signaling?**
   - **Resolved**: Neither explicit sensor signaling nor orchestrator detection needed. F-16's BBR flow control handles volume automatically (latency-based back-pressure). The `intent: informational` field prevents unnecessary executive calls. The sensor emit schedule (F-18) naturally consolidates burst events. No explicit burst protocol needed.
4. **Who handles bundling?**
   - **Resolved**: Sensor domain logic, per F-18. Not a separate preprocessor.
5. **Informational data into context?**
   - **Resolved**: Orchestrator stores `informational` events in memory (available for retrieval by the executive when processing a future `actionable` event) but does not route them through salience → executive. Same routing concept as F-15's `system.*` events generalized — different intents get different routing.

**Scope**: Add `intent` field to event contract in PoC 2. Orchestrator routing logic for `informational` events (store only, no pipeline).

---

### F-21: App-buffered events released on mod connect

**Status**: resolved — specific case of F-20, one additional contract field
**Affects**: Sensor contract, driver design

**Observation**: Some apps (RuneScape) buffer events during startup before mods are allowed to receive them. Once the mod becomes live, all buffered events are sent in a flood. This is a specific case of F-20 but with an additional nuance: these events occurred BEFORE the driver was active, so timestamps may not be accurate, and the events represent pre-existing state, not changes.

**Impact**: The sensor needs to distinguish between:
- **Live events**: Happened while sensor was active (accurate timestamps, represents changes)
- **Backfill events**: Buffered from before sensor was active (may have inaccurate timestamps, represents initial state)

**Resolution**: One boolean flag (`backfill: true`) on the event contract. Combined with F-20's `intent: informational`, this fully handles backfill events.

- **`backfill`** (boolean, default `false`): Marks events as pre-existing state dumped on connect. Signals to downstream consumers that timestamps may be inaccurate and the data represents initial state, not real-time changes.
- Backfill events are implicitly `intent: informational` — pre-existing state doesn't need a response. The sensor should set both fields.
- Orchestrator stores backfill events as context (available for retrieval) but does not route through the pipeline. Same routing as F-20's `informational` events.
- Learning system should not treat backfill events as missed response opportunities — GLADyS wasn't active when they occurred.

**Design question answers**:
1. **Backfill flag?**
   - **Resolved**: Yes. `backfill: true` boolean on the event. Lightweight, one field. Sensor sets it when it detects the driver is dumping buffered state (e.g., burst of events with identical or near-identical timestamps on connect).
2. **Different delivery pattern?**
   - **Resolved**: No. Same `PublishEvents` path. The `backfill` flag + `intent: informational` tells the orchestrator how to handle them. No separate delivery mechanism needed.
3. **Orchestrator handling?**
   - **Resolved**: Store as context, don't trigger pipeline. Same as F-20's `informational` routing. The `backfill` flag additionally signals "don't trust timestamps" and "not a missed opportunity" for learning.

**Scope**: Add `backfill` boolean to event contract in PoC 2 alongside F-20's `intent` field.

---

### F-22: Sudoku and Melvor sensor-specific findings

**Status**: resolved — no additional findings

Sudoku and Melvor were exploratory sensors with near-identical HTTP Bridge architectures. Their sensor-relevant lessons are already captured in the general findings (F-14 through F-21). No sensor-specific findings beyond what's already documented.

---

## Feedback & Learning System Findings

### F-23: Granular feedback — user scale + dev dual rating

**Status**: resolved
**Affects**: Learning strategy, dashboard UI, feedback proto, pack development tooling

**Observation**: Binary good/bad feedback is too coarse. Users and developers need different feedback interfaces, both feeding the same confidence model.

**Impact**: Two audiences, two interfaces, one learning system.

#### User feedback (end-user, low friction)

**3-point scale (one click):**

| Rating | Label | Confidence effect |
|--------|-------|-------------------|
| Good | "This helped" | Moderate positive (condition + action) |
| Meh | "Not wrong, not helpful" | Tiny positive (didn't hurt) |
| Bad | "Wrong or unhelpful" | Moderate negative (split by attribution) |

**On "Bad" only — optional follow-up (one more click):**

| Option | User means | System learns |
|--------|-----------|---------------|
| "Shouldn't have said anything" | Wrong match / irrelevant | Penalize condition confidence |
| "Right idea, wrong response" | Correct trigger, bad action | Penalize action, preserve condition |
| "Bad timing" | Right heuristic, wrong moment | Flag timing/context, not heuristic |

If no follow-up: penalty split across both condition and action (default).

#### Dev feedback (pack author, during live and mock use)

**5-point labeled dual rating for rule and response separately:**

**Rule (condition match):**
| Score | Label |
|-------|-------|
| 1 | Wrong match — shouldn't have fired |
| 2 | Weak match — loosely relevant, too broad |
| 3 | Reasonable — right ballpark |
| 4 | Good match — correct situation |
| 5 | Exact match — precisely this scenario |

**Response (action quality):**
| Score | Label |
|-------|-------|
| 1 | Harmful — actively wrong |
| 2 | Unhelpful — not wrong but not useful |
| 3 | Adequate — good enough |
| 4 | Good — helpful, would keep |
| 5 | Ideal — exactly the right response |

**Purpose**: Dev feedback tunes pack-shipped heuristics before release. Dev ratings are real usage observations (mock and live), not separate from the confidence model. They feed into the same Beta-Binomial update but with more precise attribution (independent condition and action updates).

#### Feedback source field

Expand `feedback_source` (from F-11) to: `user_implicit`, `user_explicit`, `dev`. Learning system uses source to determine:
- What signal is available (3-point vs 5-point dual)
- How to attribute the update (aggregate vs independent condition/action)

#### Update magnitudes

All magnitudes are **configurable tuning parameters**, not constants. Constraints:
- Must be small enough that confidence converges over dozens of observations, not 3-5
- Must respect F-05 bounds (confidence never reaches 0.0 or 1.0)
- Interact with F-03 gradient (1st feedback counts more than Nth for same heuristic)

**Design questions**:

**Q1: Should dev and user feedback be shown in the same dashboard view or separate tabs?**

Same view, mode toggle via settings. Dev feedback is for pack development prior to release. User feedback is for production use. A settings toggle switches which scale is displayed — only one scale is visible at a time. No need to show both simultaneously.

**Q2: Should dev feedback include a free-text notes field?**

Yes. Optional free-text notes field on dev feedback for pack development context (e.g., "fired correctly but response tone is too aggressive for this game state"). Stored alongside the feedback record. Not consumed by the learning system — purely for pack author reference and development history.

**Q3: How does the 5-point score map to update magnitude?**

Linear mapping centered at score 3 (neutral). Magnitudes are explicit per-score configuration values, independently configurable for rule and response scales:

```yaml
dev_feedback_magnitudes:
  rule: [-0.4, -0.2, 0.05, 0.2, 0.4]     # scores 1-5
  response: [-0.4, -0.2, 0.05, 0.2, 0.4]  # scores 1-5
```

Score 3 maps to a tiny positive (0.05) — "adequate" means the heuristic didn't hurt. Independent config allows tuning rule confidence updates separately from response confidence updates. Values are starting defaults; pack authors and operators tune via config.

**Q4: Can dev feedback override user feedback?**

No explicit override mechanism. Both dev and user feedback are observations feeding the same Beta-Binomial model. Dev uses F-24 pack constraints (`locked`, `floor`, `ceiling`) for guardrails when "I know better" than accumulated feedback.

In practice, dev and user feedback are temporally separated: dev feedback happens during pack development (pre-release), user feedback happens during production use (post-release). The settings toggle (Q1) reflects this — the active feedback mode matches the deployment phase.

**Scope**: PoC 2. Feedback proto changes, dashboard UI mode toggle, learning strategy config for magnitudes.

---

### F-24: Pack constraints on heuristic learning

**Status**: resolved — **SDK design, some YAGNI-ignoring warranted**
**Affects**: Learning strategy, heuristic storage, pack manifest, decision strategy, dashboard (heuristic detail view)

**Observation**: Packs that ship heuristics need control over how the learning system treats those heuristics. Different heuristics have different certainty levels and different tolerance for user-driven change.

**Impact**: This is part of the heuristic SDK. Pack authors are the first "external" developers — the contract established now is hard to change later.

#### Heuristic-level constraints

Packs can declare per-heuristic learning constraints:

```yaml
heuristic:
  condition: "player near creeper, creeper not aggroed"
  action: "sprint away, turn, hit, repeat"
  confidence: 0.85
  constraints:
    locked: false           # true = confidence cannot change (objectively correct)
    floor: 0.6              # confidence cannot drop below this
    ceiling: 0.95           # confidence cannot rise above this
    feedback_weight: 1.0    # multiplier on feedback updates (bounded: 0.25 - 2.0)
```

**Use cases:**
- `locked: true`: Objectively best response (how to kill creepers). User feedback cannot erode domain knowledge.
- `floor: 0.6`: Well-tested heuristic that should be resilient to noise but still adaptable.
- `feedback_weight: 0.5`: Stable, well-established heuristic — slow to change. `2.0`: Experimental heuristic — learn fast.

**Feedback weight bounds**: `[0.25, 2.0]`. A pack can slow learning (stable heuristics) or speed it (experimental). Cannot effectively disable learning (that's what `locked` is for). Cannot make learning so fast that one bad rating tanks a good heuristic.

#### Pack-level response biases

Personality and skill packs can influence response selection without modifying decision logic:

```yaml
response_bias:
  violence: 1.3        # GLaDOS: prefer violent responses when multiple options exist
  cooperation: 0.7     # GLaDOS: deprioritize cooperative responses
```

**Boundary — bias vs logic:**
- **OK**: Response bias as weighted preferences applied during selection. Same mechanism as user preferences. The decision strategy sees this as input, not replacement logic.
- **Not OK**: Packs replacing or overriding the decision function itself. That's code injection, not personality.

Personality affects **selection among options**, not **what options exist** or **how they're evaluated**.

#### Resolved: Personality affects bias, not strategy

**Decision**: Personalities introduce bias (weighted preferences, threshold adjustments). They do NOT replace or override the decision strategy. This is the confirmed boundary.

**What personality CAN do** (bias):
- Adjust response selection weights (prefer certain response types)
- Modify thresholds (cautious personality = higher confidence required to act)
- Lower/raise salience thresholds for specific dimensions (proactive personality lowers opportunity threshold)
- Suppress informational notifications (terse personality)

**What personality CANNOT do** (strategy override):
- Replace the decision function
- Bypass confidence checks
- Override safety constraints
- Ignore user feedback

**Experimental feature (off by default)**: Personality heuristics — heuristics whose conditions/actions are influenced by personality config. Already designed in [THEORETICAL_FOUNDATIONS.md:218-242](../../research/THEORETICAL_FOUNDATIONS.md#L218-L242). Known research questions in [OPEN_QUESTIONS.md:78-99](../../research/OPEN_QUESTIONS.md#L78-L99):
- Confirmation bias: proactive personalities learn faster but from lower-quality actions
- Personality swap: how much confidence decay when personality changes?
- Factoring out personality: keep domain knowledge, discard behavioral bias

**Design questions**:

**Q1: Where do heuristic constraints live — per-heuristic or pack manifest?**

Per-heuristic is the primary mechanism. Pack manifest provides defaults as a convenience layer (since this is SDK design, the layering is worth building even if pack-level defaults aren't immediately needed):

```yaml
# Pack manifest (defaults for all heuristics in this pack)
defaults:
  constraints:
    floor: 0.3
    feedback_weight: 1.0

# Per-heuristic override
heuristics:
  - condition: "creeper near player"
    action: "sprint, turn, hit"
    constraints:
      locked: true   # overrides pack default
```

Per-heuristic wins over pack default. If no per-heuristic constraints, pack defaults apply. If no pack defaults, system defaults apply (`locked: false`, no floor/ceiling, `feedback_weight: 1.0`).

**Q2: Should locked heuristics allow dev feedback overrides?**

No. Locked means locked — no confidence changes from any feedback source. To change a locked heuristic, the dev updates the pack definition (change `locked: false`, edit the condition/action, adjust constraints). This is a source control operation, not a runtime operation. "Locked but overridable" creates confusing semantics.

**Q3: Should feedback_weight be per-heuristic or per-pack?**

Per-heuristic, with pack-level default (same layering as Q1). A pack's stable heuristics and experimental heuristics live side-by-side — they need different learning rates.

**Q4: How do pack response biases interact with user preferences?**

Deferred. Response biases require the multi-response selection system (F-09, PoC 3). Designing the interaction model now risks YAGNI. The body text captures the concept and the bias-vs-strategy boundary well enough for future design work.

**Q5: Should constraints be visible to the user?**

Yes, in the dashboard heuristic detail view. Users should understand why a heuristic doesn't change confidence. Simple labels: "Locked by [pack name]", "Floor: 0.6 (set by [pack name])". Not in the response UI — users don't need to see this during normal interaction.

**Q6: Personality bias vs strategy override boundary?**

Already resolved in body text above ("Resolved: Personality affects bias, not strategy"). The boundary is confirmed: bias affects **selection weights among existing options**, strategy controls **what options exist and how they're evaluated**. No additional design work needed.

**Scope**: PoC 2 — per-heuristic constraints in heuristic storage, pack manifest defaults, learning strategy enforcement. Dashboard heuristic detail view shows constraint labels. Response biases deferred to PoC 3 (F-09 dependency).

---

### F-25: Sleep-cycle heuristic re-evaluation with stratified random selection

**Status**: captured (PoC 2 scope — Decision Strategy must not preclude it)
**Affects**: Decision strategy, learning strategy, confidence model

**Observation**: Creativity is how new solutions are found. A "sleep cycle" process could randomly select heuristics, send their context to an LLM without any candidate options, and ask for a suggested response. Because it's a sleep cycle (not real-time), enriched context can be provided.

**Impact**: This produces a **clean convergence signal** — the LLM has no candidate anchoring, so if it independently generates something similar to the heuristic's action, that's genuine convergence evidence. Contrasts with real-time F-04 convergence which is contaminated by candidate exposure.

**Stratified random selection by confidence tier:**

| Tier | Selection | Benefit |
|------|-----------|---------|
| Low confidence | Random subset | Strengthen valid ones, generate new/better heuristics to replace weak ones |
| Medium confidence | Random subset | Course correct before a heuristic becomes falsely strong |
| High confidence | Random subset | Break out of overfitting, detect stale heuristics |

Each tier provides different learning benefits. The number selected per tier (X from low, Y from medium, Z from high) is configurable.

**Primary goal: creativity.** The sleep cycle is an exploration tool that also produces convergence signals as a side effect. LLM response variance is the feature, not noise — divergent responses are creative output that can improve or replace existing heuristics.

**Enriched context = episodic memory.** During live processing, context is a single event. During sleep, context can be the episodic memory — the sequence of events that led to a heuristic firing. This is qualitatively different input. It also creates an opportunity for **episodic heuristics** — heuristics grounded in event sequences, not single events. (Requires episodes to be implemented first — later PoC work.)

**Single LLM constraint.** For current and near-term PoCs, one reasoning LLM handles both live and sleep-cycle work. Accepted limitation. Using separate LLMs for independent validation is a potential future exploration.

**Key properties:**
- No candidates shown → clean convergence signal (unlike real-time F-04)
- Enriched context (episodic memory) possible because not latency-bound
- Divergence is productive — generates better responses, not just a measurement
- Convergence is a side-effect signal, not the primary goal
- Relates to existing deferred item (exploration epsilon) and PoC 2 W5 (sleep-mode consolidation)

**Design questions:**
1. What defines the confidence tier boundaries? (e.g., low < 0.4, medium 0.4-0.7, high > 0.7)
2. How many heuristics per tier per sleep cycle?
3. What enriched context is available? (Episodic memory, recent events from same source, related heuristics, user goals)
4. How is the convergence/divergence signal fed back into the confidence model?
5. How often does the sleep cycle run? (Nightly? After N events? Configurable?)
6. How are episodic heuristics represented? (Depends on episode design — later PoC)

**For Decision Strategy spec**: The Protocol must not preclude sleep-cycle evaluation. The `decide()` method should work for both real-time (with candidates) and sleep-cycle (without candidates, for re-evaluation). This is naturally satisfied by `candidates: list[HeuristicCandidate]` being an empty list.

---

## Cross-Reference: Findings by Subsystem

| Subsystem | Findings |
|-----------|----------|
| **Sensor Contract** | F-01, F-02, F-14, F-15, F-16, F-17, F-18, F-19, F-20, F-21 |
| **Sensor Base Class** | F-14, F-15, F-16 |
| **Salience Scorer** | F-01, F-02, F-16 |
| **Learning Strategy** | F-03, F-04, F-05, F-11, F-23, F-24, F-25 |
| **Decision Strategy** | F-04, F-09, F-10, F-13, F-24, F-25 |
| **Executive** | F-06, F-07, F-08, F-12, F-13, F-19 |
| **Router / Orchestrator** | F-08, F-18, F-20, F-21 |
| **Proto / Schema** | F-01, F-05, F-19, F-20, F-23 |
| **Driver Design** | F-15, F-18, F-21 |
| **Preprocessor** | F-18, F-20 |
| **Pack SDK / Manifest** | F-23, F-24 |
| **Dashboard UI** | F-23 |

## Findings Needing Dedicated Design Sessions

- **F-08**: Goal selection for events
- **F-09**: Combinatorial response selection
- **F-07 + F-08**: Goal management (where goals come from + how they're matched)
- **F-16**: Sensor-level vs salience-level suppression (architectural decision)
- **F-24**: Pack constraints on learning + personality depth (SDK design)

## Findings Actionable Now (can be addressed in existing specs)

- **F-01**: Source in event contract + salience scorer (sensor contract design + SALIENCE_SCORER.md)
- **F-05**: Confidence bounds (LEARNING_STRATEGY.md)
- **F-04**: Low-confidence heuristic options (DECISION_STRATEGY.md — impl prompt #2 is ready)
- **F-14**: Test mode capture (sensor base class design)
- **F-15**: Sensor metrics (sensor base class design)
- **F-23**: Feedback scale design (LEARNING_STRATEGY.md + dashboard + feedback proto)

## Findings That Shape the Event Contract

These findings directly inform the composable event interface model:

| Finding | Contract Implication |
|---------|---------------------|
| F-01 | Source must be structured and rich, not a flat string |
| F-17 | Delivery patterns must include `stream` (design, don't build) |
| F-18 | Event relationships / dedup hints needed |
| F-19 | Field-level data classification (`normal`, `evaluation_only`, `internal`) |
| F-20 | Event intent field (`actionable`, `informational`, `unknown`) |
| F-21 | Backfill/historical flag for pre-connection state dumps |
