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

**Status**: open
**Affects**: Sensor contract, Salience scorer, proto schema, heuristic storage

**Observation**: Heuristic matching without source context produces cross-domain false positives. A calendar event about "meeting in 5 minutes" should not match a gaming heuristic about "5 minutes until boss spawn." MiniLM-L6 embeddings alone can't distinguish these — they're semantically similar.

**Impact**: Source is not just metadata — it's a primary input to the matching algorithm. Currently `source` is a flat string in the proto Event message. It may be missing from the heuristic matching query path entirely (see #56, #99).

**Design questions**:
1. Should source be a hard filter (only match heuristics from same source) or a weighted signal (prefer same-source, allow cross-source at high similarity)?
2. How granular is "source"? Sensor ID? Domain? Pack? (e.g., `runescape-sensor` vs `gaming` vs `runescape-pack`)
3. Does the heuristic store its source context? If so, at what granularity?
4. How does this interact with cross-domain reasoning (PoC 3 goal)?

**Related**: working_memory.md discovery ("MiniLM-L6 similarity too coarse for cross-domain"), #56, #99

---

### F-02: Heuristic-to-event matching needs to improve

**Status**: open
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
2. Should `raw_text` generation follow a template/pattern per event type to improve embedding consistency?
3. Should we log all candidate matches (not just winner) to diagnose matching quality? (POC_LIFECYCLE already suggests this)

---

## Learning & Confidence

### F-03: Positive feedback should increase confidence on a gradient scale

**Status**: open
**Affects**: Learning strategy, confidence update algorithm

**Observation**: Liking a heuristic response should increase confidence, but by how much? First-time approval should count more than repeated approval of the same pattern.

**Impact**: Current Beta-Binomial update treats all positive feedback equally. A gradient scale (1st like = significant boost, 2nd = moderate, 3rd+ = diminishing) would better model trust-building.

**Design questions**:
1. Is this a modification to the Beta-Binomial parameters, or a separate scaling function applied before the update?
2. Should the gradient be per-heuristic (Nth approval of THIS heuristic) or per-event-type (Nth approval of this TYPE of response)?
3. Does this interact with the implicit feedback timing (F-11)?

---

### F-04: Low-confidence heuristics should be included in LLM prompt as options

**Status**: open
**Affects**: Decision strategy, executive prompt design

**Observation**: When a low-confidence heuristic reasonably matches an event, its response should be presented to the LLM as a neutral option — not as the answer, but as "here's what was tried before."

**Impact**: If the LLM independently generates a near-identical response to a low-confidence heuristic, that's strong evidence the heuristic is good. This creates a new implicit signal: "LLM convergence."

**Design questions**:
1. What similarity threshold qualifies as "reasonably matches" for inclusion?
2. How are heuristic options presented in the prompt? As examples? As options to choose from?
3. If LLM response is near-identical to a heuristic option, what's the confidence boost? (Small — the LLM agreed, but we didn't get user feedback yet)
4. If LLM response diverges from all heuristic options, is that negative signal for those heuristics? (Probably not — LLM may have more context)
5. How many heuristic options can we include before the prompt gets too long / quality degrades?

**Directly relevant to**: `impl-decision-strategy.md` (now unblocked)

---

### F-05: Confidence must never reach 0 or 1

**Status**: open (likely straightforward)
**Affects**: Learning strategy, confidence update algorithm

**Observation**: Nothing should ever be absolutely certain or absolutely impossible. A confidence of 1.0 means "this will always work" — which is never true. A confidence of 0.0 means "this will never work" — also never true (context might change).

**Impact**: Beta-Binomial with proper priors naturally prevents exact 0 or 1, but the bounds should be explicit: e.g., [0.01, 0.99] or [0.05, 0.95].

**Design questions**:
1. What are the hard bounds? `[0.05, 0.95]` seems reasonable.
2. Should this be configurable or fixed?
3. Does this need to be in the proto definition or just enforced in the update logic?

---

### F-06: LLM-generated response confidence seems unusually high

**Status**: open
**Affects**: Executive, decision strategy, confidence semantics

**Observation**: The LLM reports high confidence in its responses, but it's unclear what "confidence" means in this context.

**Impact**: If confidence means "how sure am I this text is grammatically correct" — of course it's high. If it means "how confident am I this response will produce the desired outcome for the user" — it should be much lower, especially for novel situations.

**Design questions**:
1. What should LLM response confidence measure? Proposed: "confidence that this response will produce the goal state (the desired outcome)."
2. Should we calibrate LLM confidence externally (scale it down) rather than trusting the raw LLM self-assessment?
3. Does the confidence definition need to be in the LLM prompt explicitly?
4. How does this interact with heuristic initial confidence (currently 0.3)?

---

## Goals & Response Selection

### F-07: Goal statement needed in LLM prompt

**Status**: open
**Affects**: Executive, sensor contract (goal context), orchestrator context

**Observation**: Without a goal statement, the LLM generates generic responses. Quality improves significantly when the system knows what the user is trying to achieve.

**Impact**: This requires goals to be part of the system context. Where do goals come from? How are they selected per-event?

**Design questions**:
1. Where are goals stored? User profile? Active context? Per-domain config?
2. How is a goal selected for a given event? Manual? Inferred from context? Domain-skill defined?
3. Can multiple goals be active simultaneously? (Yes — "survive combat" AND "have fun" AND "level up")
4. How are conflicting goals handled? (e.g., "maximize XP" vs "minimize risk")

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

**Status**: open — **needs dedicated design session**
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

**Status**: open
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

**Status**: open
**Affects**: Learning strategy, implicit feedback design

**Observation**: Manual feedback (user explicitly approves/rejects) needs a much longer window than implicit feedback (user undoes an action or ignores a suggestion). But what unit measures the window — time? Number of subsequent events? Some combination?

**Impact**: Currently unclear how feedback attribution works temporally. If a user gives thumbs-up 30 minutes later, does it count? If 3 events pass without complaint, is that implicit approval?

**Design questions**:
1. What's the manual feedback window? Time-based (e.g., 5 minutes)? Session-based? Unlimited until next event?
2. What's the implicit feedback window? Time-based? Event-count-based? Both?
3. Should the window vary by domain? (Gaming events are rapid — 3 events might be 2 seconds. Home automation events are sparse — 3 events might be 3 hours.)
4. How does this interact with the gradient confidence scale (F-03)?

**Related**: ADR-0010 §3.10 defines implicit signal types but not windows

---

## Executive Architecture

### F-12: Multi-threaded LLM calls for scenario exploration

**Status**: open
**Affects**: Executive architecture, latency budget

**Observation**: Sometimes the Executive should explore multiple scenarios simultaneously. If done serially, latency is too high (each LLM call is 500-2000ms).

**Impact**: This is an architectural change. Currently the Executive processes one event with one LLM call. Parallel exploration means multiple concurrent LLM calls per event, then selecting among results.

**Design questions**:
1. When should the Executive explore multiple scenarios vs commit to one? (Confidence threshold? Event complexity? User preference?)
2. How many concurrent explorations? (Cost/latency tradeoff)
3. Does this interact with F-04 (heuristic options in prompt)? If we're already providing heuristic options, maybe we don't need parallel LLM calls.
4. Is this PoC 2 or PoC 3 scope?

**Related**: resource-allocation.md concurrent processing question

---

### F-13: Should LLM provide multiple response options with confidence levels?

**Status**: open
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

**Status**: open
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
1. Should capture/replay be a base class feature (all sensors get it for free)? (Likely yes — both levels are JSON in/out, replay is generic, no transport-specific logic needed)
2. ~~Capture parameters: max events? max time? max file size?~~ **Resolved**: Time-based + record-count-based, whichever hits first. Must be explicitly enabled.
3. File format: JSONL (one event per line, appendable) or JSON array (structured but harder to stream)?
4. ~~For driver-level capture, who captures — the driver itself or the sensor's ingestion layer?~~ **Resolved**: Sensor's ingestion layer captures driver data. Drivers must stay lightweight — capture logic belongs in the sensor (Python), not duplicated across driver languages.
5. Should replay support speed control? (1x realtime, fast-forward, step-through)

---

### F-15: Sensor metrics for health and quality assessment

**Status**: open
**Affects**: Sensor base class, sensor dashboard (design question #62), manifest

**Observation**: Need basic metrics to assess how a sensor is performing. Two levels:
- **Driver metrics**: Is the driver missing app-specific events? (e.g., RuneLite fires an event but the driver didn't capture it)
- **Sensor metrics**: Events received, events published, events dropped/filtered, latency, error counts

**Impact**: Without metrics, a misconfigured or degraded sensor is invisible. The sensor dashboard design question (#62) needs these metrics to display.

**Design questions**:
1. What metrics should every sensor report? (Proposed minimum: events_received, events_published, events_dropped, last_event_timestamp, uptime, error_count)
2. Should driver-level metrics be reported through the sensor, or is that driver-specific?
3. How are metrics exposed? gRPC health endpoint? Periodic metric events? Dashboard polling?
4. Should the manifest declare expected event rates so the system can detect anomalies?

---

### F-16: System-directed event type suppression at sensor level

**Status**: open — **architectural decision needed**
**Affects**: Sensor contract, orchestrator→sensor communication, habituation model

**Observation**: The system should be able to tell a sensor to stop capturing specific event types. Example: RuneScape emits sound events, which are probably useless unless a future audio preprocessor exists.

**Impact**: This raises a fundamental question: should suppression happen at the sensor level or the salience level?

- **Sensor-level suppression**: Prevents the event from being recorded at all. Saves bandwidth, storage, and processing. But: we lose the ability to retroactively analyze suppressed events if we later decide they're useful.
- **Salience-level suppression (habituation)**: Event is captured and stored but not routed to Executive. Preserves the data for future analysis. But: still costs bandwidth and storage for events we're ignoring.

**Design questions**:
1. Should there be two suppression layers — sensor-level (hard filter, event never emitted) and salience-level (soft filter, event stored but not acted on)?
2. If sensor-level suppression exists, who controls it? Orchestrator config? User preference? Automatic based on salience feedback?
3. Should the sensor manifest declare which event types are suppressible vs always-on?
4. Does sensor-level suppression need to be reversible at runtime (orchestrator sends "start capturing sound events again")?
5. Is this related to the RuneScape driver's per-category toggles (enabled/disabled by default)?

**Tension**: Suppressing at the sensor saves resources but loses data. The principle "measure before optimizing" (ADR-0004) suggests keeping data and suppressing at salience. But at PoC 2 event volumes, bandwidth may force sensor-level filtering.

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

**Status**: open
**Affects**: Sensor contract, dedup strategy, preprocessor design

**Observation**: Game events often contain overlapping data. RuneScape example:
- Position event fires every game tick (contains entity position)
- Movement event fires when an entity moves (also contains entity position)
- Both events carry the same position data

Other overlapping patterns exist across event types.

**Impact**: Two problems:
1. **App-level dedup**: The driver/sensor must decide which event is the authoritative source for a given piece of data. This is domain-specific.
2. **GLADyS-level dedup**: Even after normalization, the orchestrator may see semantically redundant events. Needs a dedup strategy.
3. **Cross-event relationships**: Some overlapping data implies a relationship between events (e.g., "this movement event is related to that position update"). How is this captured?

**Design questions**:
1. Where does dedup happen? Driver? Sensor? Preprocessor? Orchestrator?
2. Should the event contract support explicit event relationships (e.g., `related_event_ids`, `supersedes_event_id`)?
3. Should there be a concept of "authoritative source" for a data field when multiple events carry it?
4. Is this a sensor-specific preprocessor concern (domain logic for which events to keep) or a generic platform concern?

---

### F-19: Solution/cheat data — flagging data not for normal use

**Status**: open
**Affects**: Sensor contract, event interface model, executive prompt design

**Observation**: Some apps contain both state and solution. Sudoku exposes the solution in the DOM. Math apps might show answers. Capturing this data helps GLADyS evaluate its own responses (was the hint correct?) but using it in a response would be cheating, not helping.

**Impact**: The event contract needs a way to flag data as "available for evaluation/learning but not for response generation." This is a data classification concern.

**Design questions**:
1. Should this be a field-level annotation (specific fields marked as restricted) or an event-level flag?
2. Proposed: `visibility` or `usage` field on data elements: `normal` (use freely), `evaluation_only` (learning/scoring but not response text), `internal` (sensor bookkeeping, don't forward)
3. Who enforces this — the sensor (marks the data), the orchestrator (strips it before Executive), or the Executive (respects the flag in prompts)?
4. Can this classification change over time? (User might say "I'm done trying, show me the answer")
5. Does this interact with the audit system? (Solution data shouldn't appear in user-visible logs but might be in audit logs)

---

### F-20: Initial connection event flood — informational vs actionable

**Status**: open — **important for PoC 2 volume management**
**Affects**: Sensor contract, event interface model, orchestrator buffering

**Observation**: When a driver connects, there's often an initial flood of events that then become sparse. Much of the flood is informational — no action needed. RuneScape example: user logs in → character appears → burst of inventory events. Only the login might need a response; the inventory events are context.

Two sub-problems:
1. **Informational vs actionable**: Need to indicate whether an event expects a response, is strictly informational (context), or unknown.
2. **Event bundling**: Multiple app events during a burst could be combined into a single GLADyS event (e.g., "user logged in with inventory: [...]"). This bundling logic belongs in the sensor or a sensor-specific preprocessor.

**Impact**: Without this distinction, the orchestrator will try to route every burst event through salience → executive, creating a processing storm on connect.

**Design questions**:
1. Should the event contract include a `response_expected` or `intent` field? Proposed values: `actionable` (may need response), `informational` (context only, no response expected), `unknown` (let salience decide)
2. Should sensors support event bundling (combining multiple app events into one GLADyS event)?
3. Should sensors signal "burst incoming" to the orchestrator? Or should the orchestrator detect bursts automatically?
4. Does the sensor or a preprocessor handle the bundle→single-event compression?
5. How does informational data get into context without triggering the Executive? (Store in memory, available for retrieval, but don't route through salience→executive)

---

### F-21: App-buffered events released on mod connect

**Status**: captured (specific case of F-20)
**Affects**: Sensor contract, driver design

**Observation**: Some apps (RuneScape) buffer events during startup before mods are allowed to receive them. Once the mod becomes live, all buffered events are sent in a flood. This is a specific case of F-20 but with an additional nuance: these events occurred BEFORE the driver was active, so timestamps may not be accurate, and the events represent pre-existing state, not changes.

**Impact**: The sensor needs to distinguish between:
- **Live events**: Happened while sensor was active (accurate timestamps, represents changes)
- **Backfill events**: Buffered from before sensor was active (may have inaccurate timestamps, represents initial state)

**Design questions**:
1. Should the event contract include a `backfill` or `historical` flag?
2. Should backfill events use a different delivery pattern (e.g., treated as `poll`/state-snapshot rather than `event`/change)?
3. How does the orchestrator handle backfill events differently? (Don't trigger responses, just store as context?)

---

### F-22: Sudoku and Melvor sensor-specific findings

**Status**: resolved — no additional findings

Sudoku and Melvor were exploratory sensors with near-identical HTTP Bridge architectures. Their sensor-relevant lessons are already captured in the general findings (F-14 through F-21). No sensor-specific findings beyond what's already documented.

---

## Feedback & Learning System Findings

### F-23: Granular feedback — user scale + dev dual rating

**Status**: open
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
1. Should dev and user feedback be shown in the same dashboard view or separate tabs?
2. Should dev feedback include a free-text notes field for pack development context?
3. How does the 5-point score map to update magnitude? Linear or non-linear? (1→-large, 3→~0, 5→+large)
4. Can dev feedback override user feedback? (e.g., dev re-rates a heuristic that users have been rating poorly)

---

### F-24: Pack constraints on heuristic learning

**Status**: open — **SDK design, some YAGNI-ignoring warranted**
**Affects**: Learning strategy, heuristic storage, pack manifest, decision strategy

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
1. Where do heuristic constraints live — in the heuristic definition (per-heuristic) or in the pack manifest (pack-wide defaults)?
2. Should locked heuristics be completely immutable, or should they allow dev feedback overrides?
3. Should feedback_weight be per-heuristic or per-pack?
4. How do pack response biases interact with user preferences? (Additive? Pack sets base, user adjusts within range?)
5. Should constraints be visible to the user? ("This response confidence is locked by the Minecraft skill pack")
6. What's the boundary between "personality bias" and "personality decision override"? Where exactly is the line?

---

## Cross-Reference: Findings by Subsystem

| Subsystem | Findings |
|-----------|----------|
| **Sensor Contract** | F-01, F-02, F-14, F-15, F-16, F-17, F-18, F-19, F-20, F-21 |
| **Sensor Base Class** | F-14, F-15, F-16 |
| **Salience Scorer** | F-01, F-02, F-16 |
| **Learning Strategy** | F-03, F-04, F-05, F-11, F-23, F-24 |
| **Decision Strategy** | F-04, F-09, F-10, F-13, F-24 |
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
