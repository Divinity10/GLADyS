# ADR-0014: Executive Decision Loop

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Date** | 2026-01-19 |
| **Owner** | Mike Mulcahy (Divinity10), Scott (scottcm) |
| **Contributors** | |
| **Module** | Executive |
| **Tags** | executive, decision, personality, response |
| **Depends On** | ADR-0001, ADR-0004, ADR-0007, ADR-0013 |

---

## 1. Context and Problem Statement

ADR-0001 establishes the Executive as the "prefrontal cortex" of GLADyS—responsible for decision-making, planning, personality, and action. ADR-0013 specifies how events reach the Executive via the Salience Gateway. However, we lack specification for:

- **What happens when an event arrives?** How does the Executive decide whether to respond, how to respond, and when?
- **How does personality affect decisions?** The personality matrix exists but its integration is undefined.
- **What's the proactive/reactive balance?** When does GLADyS speak without being prompted?
- **How are skills orchestrated?** When to load/unload, how to compose responses.

**Core problem**: How does the Executive turn a stream of salient events + memory into appropriate, personality-consistent responses at the right time?

---

## 2. Decision Drivers

1. **Response quality over quantity**: Better to say nothing than to say something irrelevant or annoying.

2. **Personality consistency**: Responses must feel like they come from a coherent character, not a random generator.

3. **Latency constraints**: ADR-0001 allocates ~400ms for Executive decision, ~200ms for response generation.

4. **User control**: Users must be able to adjust proactivity, verbosity, personality without feeling like they're fighting the system.

5. **Context awareness**: Same event should generate different responses in different contexts (gaming vs work).

6. **Learning integration**: Executive behavior should improve based on user feedback (ADR-0007 adaptive algorithms).

---

## 3. Decision

We implement the Executive as a **stateful decision engine** with:

- **Event-driven core loop**: Process events from Salience Gateway
- **Decision framework**: Multi-factor evaluation before responding
- **Personality integration**: Traits influence every decision point
- **Proactive scheduling**: Clock-driven opportunities to speak without events
- **Skill composition**: Layered response generation through skill pipeline
- **Feedback emission**: Modulation signals back to Salience Gateway

---

## 4. Architecture Overview

### 4.1 Position in System

```
              Salience Gateway
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                         EXECUTIVE                                │
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │   Inbox      │ → │  Decision    │ → │   Response           │ │
│  │   Queue      │   │  Engine      │   │   Generator          │ │
│  └──────────────┘   └──────────────┘   └──────────────────────┘ │
│         ↑                 │                       │              │
│         │           ┌─────┴─────┐                 ▼              │
│   Salience     ┌────┴────┐ ┌────┴────┐    ┌──────────────┐     │
│   Stream       │Personality│ │  Memory │    │    Output    │     │
│                │  Engine   │ │  Query  │    │    Router    │     │
│                └──────────┘ └─────────┘    └──────────────┘     │
│                      │                           │               │
│                      ▼                           ▼               │
│               ┌──────────────┐            ┌──────────────┐      │
│               │    Skill     │            │   TTS/Text   │      │
│               │  Orchestrator│            │   Output     │      │
│               └──────────────┘            └──────────────┘      │
│                                                                  │
│                      ┌──────────────┐                            │
│                      │  Modulation  │ → To Salience Gateway      │
│                      │  Emitter     │                            │
│                      └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Core Components

| Component | Responsibility |
|-----------|---------------|
| **Inbox Queue** | Receives SalientEvents, buffers for processing |
| **Decision Engine** | Evaluates whether/how/when to respond |
| **Personality Engine** | Applies trait modulation to all decisions |
| **Memory Query** | Retrieves relevant context for decisions and responses |
| **Response Generator** | Produces response content (text, action) |
| **Skill Orchestrator** | Loads/unloads skills, composes through skill pipeline |
| **Output Router** | Directs response to appropriate output (TTS, text, action) |
| **Modulation Emitter** | Sends feedback to Salience Gateway |

---

## 5. Decision Engine

### 5.1 Core Loop

The Executive runs on a clock tick (default 1 Hz), not purely event-driven:

```
Every tick:
  1. Process inbox events (event-driven)
  2. Check proactive opportunities (clock-driven)
  3. Emit pending modulation signals
  4. Update internal state
```

This hybrid model allows:
- **Reactive**: Respond to events as they arrive
- **Proactive**: Initiate conversation without events (check-ins, observations)

### 5.2 Decision Framework

For each event (or proactive opportunity), the Decision Engine evaluates:

```
┌─────────────────────────────────────────────────────────────────┐
│                    DECISION FRAMEWORK                            │
│                                                                  │
│  Event → [RELEVANCE] → [TIMING] → [RESPONSE TYPE] → [CONTENT]   │
│              │             │             │              │        │
│              ▼             ▼             ▼              ▼        │
│          Should I      When should   How should I    What do    │
│          respond?      I respond?    respond?        I say?     │
└─────────────────────────────────────────────────────────────────┘
```

#### 5.2.1 Relevance Evaluation

**Inputs**:
- Salience vector from gateway (threat, opportunity, goal_relevance, humor, etc.)
- Current focus (what is the user doing?)
- Recent response history (did I just say something about this?)
- Personality trait: `proactive` (how often to speak unprompted)

**Decision**:
```
relevance_score = f(salience, focus_alignment, novelty, proactive_trait)

if relevance_score < threshold:
    decision = PASS  # Don't respond
else:
    decision = CONTINUE
```

**Threshold modulation**:
- High `proactive` personality → lower threshold (respond more)
- User recently said "be quiet" → raise threshold temporarily
- High threat → ignore threshold (always respond)

#### 5.2.2 Timing Evaluation

Not every response should be immediate. Timing considers:

**Factors**:
- **Urgency** (from salience): High threat → immediate
- **User state**: User typing/in menu → wait for natural break
- **Response clustering**: Multiple events → batch into one response
- **Personality trait**: `enthusiasm` affects response speed

**Timing outcomes**:
| Outcome | Condition | Behavior |
|---------|-----------|----------|
| **Immediate** | High urgency OR high enthusiasm + high relevance | Respond now |
| **Queued** | Moderate relevance, user busy | Wait for break signal |
| **Batched** | Multiple related events in window | Combine into single response |
| **Deferred** | Low urgency, conversational | Wait for natural opportunity |

**Break signals** (from Orchestrator):
- User paused typing for N seconds
- Menu closed
- Combat ended
- Explicit "what's up?" prompt

#### 5.2.3 Response Type Selection

**Types**:
| Type | When | Example |
|------|------|---------|
| **Alert** | High threat, needs attention | "Behind you!" |
| **Observation** | Worth noting, no action needed | "Nice shot." |
| **Suggestion** | Actionable opportunity | "You could craft a diamond pickaxe." |
| **Question** | Need user input | "Want me to keep tracking this?" |
| **Quip** | Humor opportunity, no information | "Well, that escalated quickly." |
| **Check-in** | Proactive, no specific event | "How's the build going?" |

**Selection based on**:
- Salience dimensions (high threat → Alert, high humor → Quip)
- Personality traits (high `helpfulness` → more Suggestions)
- Context (gaming → more Alerts/Quips, work → more Observations)

#### 5.2.4 Content Generation

Content is generated through the **skill pipeline** (see Section 7).

---

## 6. Personality Integration

### 6.1 Trait Matrix

From ADR-0001 Section 9.2, personality traits:

| Trait | Range | Effect on Executive |
|-------|-------|-------------------|
| humor | 0-1 | Likelihood of quips, joke injection |
| sarcasm | 0-1 | Tone modifier, affects word choice |
| formality | 0-1 | Register (casual ↔ professional) |
| proactive | 0-1 | Response threshold, check-in frequency |
| enthusiasm | 0-1 | Response speed, exclamation usage |
| helpfulness | 0-1 | Suggestion frequency, detail level |
| verbosity | 0-1 | Response length, detail inclusion |

### 6.2 Trait Application Points

Traits affect multiple decision stages:

```
                          ┌─────────────────────────────┐
                          │        TRAIT MATRIX          │
                          │                              │
                          │  humor: 0.8                  │
                          │  sarcasm: 0.6                │
                          │  proactive: 0.5              │
                          │  ...                         │
                          └──────────────┬──────────────┘
                                         │
          ┌──────────────────────────────┼──────────────────────────────┐
          │                              │                              │
          ▼                              ▼                              ▼
   ┌─────────────┐               ┌─────────────┐               ┌─────────────┐
   │  Relevance  │               │  Response   │               │   Content   │
   │  Threshold  │               │   Type      │               │   Style     │
   │             │               │             │               │             │
   │ proactive   │               │ humor →     │               │ sarcasm →   │
   │ helpfulness │               │   Quip      │               │   tone      │
   │             │               │ helpfulness │               │ formality → │
   │             │               │   → Suggest │               │   register  │
   └─────────────┘               └─────────────┘               └─────────────┘
```

### 6.3 Context-Adaptive Traits

Per ADR-0001 Section 9.3, traits shift based on context:

```yaml
context_modifiers:
  high_threat:
    proactive: +0.3      # More likely to speak
    sarcasm: -0.4        # Less sarcastic
    verbosity: -0.3      # Shorter responses
    helpfulness: +0.2    # More helpful

  opportunity:
    enthusiasm: +0.2     # More excited
    humor: +0.1          # Slightly more jokes

  user_struggling:
    helpfulness: +0.3    # More helpful
    sarcasm: -0.5        # Much less sarcastic
    formality: -0.2      # More casual/friendly
```

### 6.4 Personality State

Personality is not just static traits but has state:

```
PersonalityState {
  base_traits: TraitMatrix          // From personality template
  context_modifiers: TraitMatrix    // Current context adjustments
  user_overrides: TraitMatrix       // User's temporary adjustments
  effective_traits: TraitMatrix     // Computed: base + context + user

  mood: MoodVector                  // Affect based on recent events
  rapport: float                    // Relationship with user (0-1)
}
```

**Mood** affects responses subtly:
- Recent successes → slightly higher enthusiasm
- Recent failures → slightly lower sarcasm (don't kick when down)
- Long session → lower proactive (user might want quiet)

**Rapport** builds over time:
- Positive feedback → rapport increases
- Negative feedback → rapport decreases
- High rapport → more personal, lower formality

---

## 7. Skill Orchestration

### 7.1 Skill Types (from ADR-0001)

| Type | Purpose | Loading |
|------|---------|---------|
| **Style Modifiers** | Alter tone/register (sarcasm, poetic) | Always loaded based on personality |
| **Personality Templates** | Define base traits | One active at a time |
| **Domain Expertise** | Context-specific knowledge | Loaded with context |
| **Capability Extensions** | New abilities (calendar, smart home) | User-enabled |

### 7.2 Skill Pipeline

Response generation flows through loaded skills:

```
Raw Intent → [Domain Skill] → [Style Skills] → [Personality Filter] → Output
                  │                 │                  │
                  ▼                 ▼                  ▼
            Add context      Modify tone        Final consistency
            "diamond ore"    add sarcasm        check against traits
```

**Example flow**:
1. **Intent**: Alert user about low health (from Decision Engine)
2. **Domain Skill** (Minecraft): Adds context "12 hearts remaining, fighting zombie"
3. **Style Skill** (Sarcasm): "Oh look, you're about to die. Again."
4. **Personality Filter**: Check sarcasm level appropriate, adjust if needed
5. **Output**: "Oh look, you're about to die. Again."

### 7.3 Skill Loading

```
On context change:
  1. Unload context-irrelevant domain skills
  2. Load new context's domain skills
  3. Style skills remain (personality-bound)

On personality change:
  1. Swap personality template
  2. Reload style skills based on new traits
  3. Domain skills unaffected
```

**Manifest declaration** (from ADR-0003):
```yaml
# Example: Minecraft expertise skill
name: minecraft_expertise
type: domain_skill
context_binding: gaming.minecraft
capabilities:
  - entity_identification
  - crafting_suggestions
  - threat_assessment
```

---

## 8. Proactive Behavior

### 8.1 Proactive Opportunities

The Executive doesn't only respond to events. It can initiate:

| Opportunity | Trigger | Example |
|-------------|---------|---------|
| **Check-in** | Time since last interaction | "Still going strong?" |
| **Observation** | Pattern noticed over time | "You've been mining for a while." |
| **Reminder** | Scheduled or inferred | "Didn't you want to check on the farm?" |
| **Mood comment** | Detected emotional state | "Rough session?" |
| **Achievement** | Milestone detected | "That's your 100th diamond!" |

### 8.2 Proactive Scheduling

```
proactive_config:
  check_in:
    min_interval_seconds: 300    # At most once per 5 min
    probability_per_tick: 0.01   # 1% chance per tick (after interval)
    trait_multiplier: proactive  # Scaled by proactive trait

  observation:
    min_events_for_pattern: 5    # Need enough data to observe
    novelty_threshold: 0.6       # Only if pattern is interesting
    cooldown_seconds: 600        # 10 min between observations

  achievement:
    always_fire: true            # Achievements are always noted
    delay_if_busy: true          # Wait for break if user in action
```

### 8.3 Proactive Filtering

Not every opportunity should fire:

```python
def should_proactive_fire(opportunity, personality):
    # Check interval
    if time_since_last(opportunity.type) < opportunity.min_interval:
        return False

    # Check personality
    base_prob = opportunity.probability_per_tick
    adjusted_prob = base_prob * personality.proactive

    if random() > adjusted_prob:
        return False

    # Check user state
    if user_state.is_busy and not opportunity.urgent:
        defer(opportunity)
        return False

    return True
```

---

## 9. Memory Interaction

### 9.1 Query Patterns

The Executive queries memory for decision-making and response generation:

| Query Type | When | Example |
|------------|------|---------|
| **Context retrieval** | Every response | "What happened recently with this entity?" |
| **Goal lookup** | Relevance evaluation | "What is user trying to accomplish?" |
| **Pattern check** | Proactive detection | "Has this happened before?" |
| **Profile access** | Personality adjustment | "How does user prefer to be addressed?" |
| **Fact recall** | Response content | "What do we know about xX_Slayer_Xx?" |

### 9.2 Memory-Informed Decisions

```
decision_context = {
    recent_events: memory.query_recent(source=event.source, limit=10),
    relevant_facts: memory.query_semantic(event.embedding, limit=5),
    user_goals: memory.get_active_goals(),
    entity_context: memory.get_entity(event.entities),
}

# Use context in decision
if similar_event in decision_context.recent_events:
    reduce_relevance()  # Already talked about this

if event matches decision_context.user_goals:
    boost_relevance()  # Relates to what user wants
```

### 9.3 Response Memory

Executive actions are logged back to memory:

```protobuf
message ExecutiveAction {
  string event_id = 1;              // Event that triggered (if any)
  ResponseType response_type = 2;   // Alert, Observation, etc.
  string content = 3;               // What was said
  repeated string skills_used = 4;  // Which skills composed this
  TraitMatrix effective_traits = 5; // Personality at time of response
  UserReaction reaction = 6;        // If user reacted (feedback)
}
```

This enables:
- Learning what responses work (ADR-0007)
- "What did I say about X?" queries
- Personality consistency checking

---

## 10. Salience Modulation

### 10.1 Feedback Triggers

The Executive sends modulation to Salience Gateway when:

| Trigger | Modulation | Example |
|---------|------------|---------|
| User says "stop telling me about X" | Suppress(X) | "OK, I'll stop mentioning inventory changes." |
| Event ignored multiple times | Habituate(pattern) | (Automatic) |
| User asks "watch for Y" | Heighten(Y) | "I'll keep an eye out for creepers." |
| Context switch | AdjustThreshold(context) | (Automatic) |

### 10.2 Implicit Feedback

Beyond explicit commands, Executive infers modulation needs:

```python
def check_implicit_feedback():
    # If I forwarded an event but Executive didn't act
    for event in recent_forwarded:
        if not was_acted_on(event):
            emit_modulation(Habituate(event.pattern, decay_rate=0.1))

    # If user seems annoyed (negative sentiment after my response)
    if recent_user_sentiment < 0 and recent_response is not None:
        raise_threshold_temporarily()
```

---

## 11. Output Routing

### 11.1 Output Types

| Type | Medium | When |
|------|--------|------|
| **Speech** | TTS | Default for alerts, observations |
| **Text** | Overlay/notification | User preference, TTS disabled |
| **Action** | System integration | Smart home, game actions (future) |
| **Silent** | Internal only | Logging, learning, no user output |

### 11.2 Output Selection

```yaml
output_preferences:
  alert:
    primary: speech
    fallback: text
    urgent: true      # Interrupt if needed

  observation:
    primary: speech
    fallback: text
    urgent: false     # Wait for break

  quip:
    primary: speech
    condition: user_not_busy
    suppress_if: recently_quipped  # Don't rapid-fire jokes
```

### 11.3 Speech Configuration

```yaml
tts:
  engine: piper       # From ADR-0001
  voice: personality_bound

  speed_modifiers:
    high_threat: 1.2  # Faster when urgent
    casual: 0.9       # Slower for relaxed

  interruption:
    allow_self_interrupt: true   # New urgent can cut off current
    min_speech_before_cut: 1.0   # At least 1s before interrupting
```

---

## 12. Performance Requirements

| Metric | Target | Rationale |
|--------|--------|-----------|
| Decision latency | <100ms P95 | Per ADR-0001: 400ms total, leave room |
| Response generation | <200ms P95 | Per ADR-0001 |
| Tick rate | 1 Hz | Balance responsiveness vs overhead |
| Memory query latency | <50ms P95 | Per ADR-0001 |
| Proactive check | <10ms | Must not delay reactive path |

---

## 13. State Management

### 13.1 Executive State

```
ExecutiveState {
  // Current context
  active_context: Context
  loaded_skills: [Skill]
  personality: PersonalityState

  // Working state
  inbox: PriorityQueue<SalientEvent>
  pending_responses: Queue<DeferredResponse>
  modulation_buffer: [SalienceModulation]

  // History (for decisions)
  recent_responses: RingBuffer<ExecutiveAction>
  recent_events: RingBuffer<SalientEvent>

  // User state (from Orchestrator)
  user_state: UserActivityState
}
```

### 13.2 Persistence

Executive state is mostly ephemeral (rebuilt on restart). Persisted elements:

| Element | Persistence | Location |
|---------|-------------|----------|
| Personality template selection | Persisted | User profile |
| User trait overrides | Persisted | User profile |
| Loaded skills | Rebuilt | From context |
| Inbox/pending | Dropped | Fresh on restart |
| Rapport | Persisted | User profile |

---

## 14. gRPC Interface

### 14.1 Service Definition

```protobuf
service Executive {
  // Receive events from Salience Gateway
  rpc StreamSalientEvents(stream SalientEvent) returns (stream ExecutiveAck);

  // User interaction
  rpc UserMessage(UserInput) returns (ExecutiveResponse);

  // State queries
  rpc GetState(Empty) returns (ExecutiveState);
  rpc GetPersonality(Empty) returns (PersonalityState);

  // Configuration
  rpc SetPersonality(PersonalityConfig) returns (PersonalityAck);
  rpc AdjustTrait(TraitAdjustment) returns (TraitAck);
  rpc LoadSkill(SkillRequest) returns (SkillAck);
  rpc UnloadSkill(SkillRequest) returns (SkillAck);
}
```

### 14.2 Executive → Salience

```protobuf
service SalienceGateway {
  // Modulation from Executive
  rpc Modulate(SalienceModulation) returns (ModulationAck);
}
```

### 14.3 Executive → Output

```protobuf
service OutputRouter {
  // Send response to output
  rpc Emit(OutputRequest) returns (OutputAck);

  // Check output state
  rpc GetState(Empty) returns (OutputState);

  // Interrupt current output
  rpc Interrupt(InterruptRequest) returns (InterruptAck);
}
```

---

## 15. Open Questions

1. **LLM selection**: Which model for response generation? Options: local (Ollama), cloud (Claude API), hybrid. Trade-offs: latency, cost, privacy, quality.

2. **Semantic Kernel integration**: ADR-0001 mentions Semantic Kernel for C# Executive. How does it fit with skill orchestration?

3. **Multi-turn conversation**: How does Executive handle extended conversations vs single responses?

4. **Goal management**: Where do goals come from? User-declared? Inferred? How updated?

5. **Fallback responses**: What does Executive do when LLM times out or errors?

---

## 16. Consequences

### 16.1 Positive

1. **Coherent personality**: Trait matrix ensures consistent character
2. **Appropriate responses**: Multi-factor decision prevents spam
3. **Proactive engagement**: Clock-driven opportunities enable personality
4. **Skill extensibility**: Pipeline allows new capabilities

### 16.2 Negative/Risks

1. **Tuning complexity**: Many parameters to configure
2. **Latency pressure**: 400ms budget is tight for LLM inference
3. **Personality drift**: Context modifiers could make character feel inconsistent
4. **Proactive annoyance**: Too much unprompted speech annoys users

### 16.3 Mitigations

- Start with conservative proactive settings
- User controls for "talk more" / "talk less"
- Log all decisions for tuning
- Personality A/B testing with user groups

---

## 17. Related Decisions

- ADR-0001: GLADyS Architecture (Executive role, personality matrix)
- ADR-0003: Plugin Manifest Specification (skill declaration)
- ADR-0004: Memory Schema Details (memory query patterns)
- ADR-0007: Adaptive Algorithms (learning from feedback)
- ADR-0013: Salience Subsystem (event source, modulation target)

---

## 18. Notes

The Executive is the "voice" of GLADyS—what users experience directly. Getting personality right is more important than feature completeness. A charming, limited AI beats a capable, annoying one.

The decision framework draws from cognitive psychology (dual-process theory) and game AI (utility-based decision making). The goal is not to simulate human cognition but to produce human-satisfying responses.

MVP should focus on reactive responses with simple proactive check-ins. Advanced proactive behavior (observations, achievements) can follow once the basic loop feels right.
