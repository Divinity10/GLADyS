# Phase Validation Roadmap

**Last Updated**: 2026-01-27

## Purpose

This document defines what the Proof of Concept must validate to confirm GLADyS is feasible. Rather than proving abstract mechanisms work, we prove the system can handle real-world tasks that humans find trivial.

The Phase is successful when we can demonstrate (with mocked sensors/actuators) that the architecture supports basic assistant functionality.

---

## Why GLADyS? (Killer Features)

### What makes GLADyS different?

| Capability | Alexa/Siri | ChatGPT | GLADyS |
|------------|------------|---------|--------|
| Responds to commands | âœ… | âœ… | âœ… |
| Learns preferences | âœ… shallow | âŒ | âœ… deep (behavioral patterns) |
| Proactive actions | âœ… notifications | âŒ | âœ… salience-driven, context-aware |
| Cross-domain awareness | âŒ siloed | âŒ no state | âœ… unified memory |
| Gets faster with use | âŒ | âŒ | âœ… heuristic learning |
| Local/private by default | âŒ cloud | âŒ cloud | âœ… local-first |
| Customizable personality | âŒ fixed | âŒ | âœ… configurable |

### Killer Features (Priority Order)

1. **"The Second Time is Faster"** (Heuristic Learning)
   - First request: LLM reasons through the problem (slow)
   - User feedback: "That was helpful"
   - Second request: Heuristic fires, skips LLM (instant)
   - *No existing assistant does this.*

2. **Proactive Intelligence**
   - Not just "reminder in 10 minutes"
   - "Steve just came online and you wanted to play — want me to message him?"
   - Requires salience evaluation + real sensors

3. **Cross-Domain Reasoning**
   - "Is Steve free for dinner?" checks Discord + Calendar + knows which Steve
   - Unified memory across all domains

4. **Pattern Detection** (Post-Phase)
   - "I notice you always turn on the porch light at sunset. Automate this?"
   - System learns without explicit feedback

### What the Phase Must Prove

| Feature | Phase Requirement | Status |
|---------|-----------------|--------|
| Heuristic creation | Explicit feedback → new heuristic stored | âš ï¸ Needs validation |
| Heuristic matching | Similar event → heuristic fires | âœ… Proven |
| Cross-domain query | Multi-hop reasoning works | âœ… Proven |
| Proactive action | Real sensor → system responds | ðŸ”´ No real sensor yet |

---

## Current Status Summary

| Phase | Component | Status | Test/Proof |
|-------|-----------|--------|------------|
| **Phase 1** | Semantic Memory | âœ… Complete | `test_semantic_memory.py` |
| **Phase 2** | Episodic Retrieval | âš ï¸ Partial | Time-based works, similarity untested |
| **Phase 3** | Skill Registry | âœ… Complete | `test_skill_registry.py` |
| **Phase 4** | E2E Query Flow | âœ… Complete | `test_e2e_query.py` |
| **Learning** | TD Learning | âœ… Complete | `test_td_learning.py` |
| **Learning** | Heuristic Matching | âœ… Complete | `test_killer_feature.py` |
| **Learning** | Full Loop | âš ï¸ Issues | `test_scenario_5_learning_loop.py` - reliability issues |

---

## North Star Scenarios

These scenarios guide what we build. Each exposes layers that must work.

### Scenario 1: "Is Steve online?"

**User asks**: "Is Steve online?"

**Expected flow**:
1. Parse query → identify intent (check person's online status)
2. Entity lookup → Steve is a friend
3. Relationship lookup → Steve has character "Buggy" in Minecraft
4. Context check → Minecraft is currently running
5. Skill routing → Minecraft skill can check player status
6. Execution → Query Minecraft for Buggy's status
7. Response → "Yes, Steve (Buggy) is online in Minecraft"

**Why this scenario matters**:
- Requires semantic memory (who is Steve? what characters?)
- Requires skill discovery (what can check online status?)
- Requires multi-step reasoning (Steve → character → game → check)
- Trivial for humans, exposes real complexity for the system

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| 0 | Storage | PostgreSQL stores all data | âœ… Proven |
| 1a | Episodic Memory | Store/retrieve events | âœ… Proven |
| 1b | Semantic Memory | Store/retrieve entities & relationships | âœ… Proven (test_semantic_memory.py) |
| 2 | Retrieval | Query relevant entities, traverse relationships | âœ… Proven (2-hop context expansion) |
| 3 | Skill Registry | Know what skills exist and their capabilities | âœ… Proven (test_skill_registry.py) |
| 4 | Routing/Planning | Connect query to correct skill | âœ… Proven (test_e2e_query.py) |
| 5 | Execution | Call skill, return result | âœ… Proven (mocked execution) |

---

### Scenario 2: "Send an email to Mike"

**User asks**: "Send an email to Mike saying I'll be late"

**Expected flow**:
1. Parse query → identify intent (send email)
2. Entity lookup → Mike is [specific person with email]
3. Skill routing → Email skill can send messages
4. Execution → Compose and send email
5. Confirmation → "Email sent to Mike"

**Why this scenario matters**:
- Requires entity resolution (which Mike?)
- Requires skill with side effects (actually sends something)
- Common assistant task

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| 1b | Semantic Memory | Know Mike's email address | âœ… Ready (entity storage works) |
| 3 | Skill Registry | Email skill registered | ðŸ”´ Need email skill manifest |
| 5 | Execution | Call email actuator | ðŸ”´ Need email actuator |

---

### Scenario 3: "What's on my calendar tomorrow?"

**User asks**: "What's on my calendar tomorrow?"

**Expected flow**:
1. Parse query → identify intent (calendar query)
2. Skill routing → Calendar skill can query events
3. Execution → Query calendar for tomorrow's events
4. Response → List of events

**Why this scenario matters**:
- Read-only query (simpler than email)
- Time-based reasoning ("tomorrow")
- Common assistant task

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| 3 | Skill Registry | Calendar skill registered | ðŸ”´ Need calendar skill manifest |
| 5 | Execution | Call calendar sensor | ðŸ”´ Need calendar skill |

---

### Scenario 4: Learning Loop (Original Phase Focus)

**Design details**: See [LEARNING_LOOP_DESIGN.md](LEARNING_LOOP_DESIGN.md) for architecture and milestones.

**Flow**: Event → LLM Reasoning → Feedback → Heuristic → Skip LLM next time

**Why this scenario matters**:
- The differentiator: system learns from experience
- Converts slow reasoning to fast heuristics
- Proves adaptive behavior works

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| 1a | Episodic Memory | Store events | âœ… Proven |
| 1c | Procedural Memory | Store heuristics | âœ… Proven |
| 2 | Heuristic Matching | Find matching heuristics | âœ… Proven (word overlap) |
| 4 | LLM Integration | Reason about events | âœ… Proven (Ollama) |
| 4 | Pattern Extraction | Extract heuristic from feedback | âš ï¸ Partially proven |

---

### Scenario 5: "The Second Time is Faster" (Learning Experience)

**Design details**: See [LEARNING_LOOP_DESIGN.md](LEARNING_LOOP_DESIGN.md) — this scenario validates Milestone 1.

**User experience**:

```
First time:
  User: "Is Steve online?"
  System: [LLM reasons: Steve → Buggy → Minecraft → check] (2-3 seconds)
  Response: "Steve (Buggy) is online in Minecraft"
  User: "Thanks!" (positive feedback)
  System: [Extracts pattern, stores heuristic]

Second time (next day):
  User: "Is Steve online?"
  System: [Heuristic fires, skips LLM] (<100ms)
  Response: "Steve (Buggy) is online in Minecraft"
```

**Why this scenario matters**:
- Shows learning from user perspective (not just mechanism)
- Proves patterns generalize (works again later)
- Performance improvement is visible (2s → 100ms)
- The differentiator in action

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| All from Scenario 1 | — | Full query flow | âœ… Proven (test_e2e_query.py) |
| 4b | Pattern Extraction | LLM generates useful heuristic | âš ï¸ Works but quality varies |
| 1c | Heuristic Persistence | Survives restart | âœ… Proven (PostgreSQL) |
| 2c | Natural Language Matching | Handles query variations | âœ… Semantic embeddings (0.7 threshold) |

---

### Scenario 6: Proactive Sensor Response

**Sensor event**: Temperature sensor reports 60Â°F (dropped from 72Â°F)

**Expected flow**:
1. Sensor sends event → Orchestrator receives
2. Salience evaluation → High (temperature drop is significant)
3. Heuristic check → "When temp drops below 65Â°F, adjust thermostat"
4. Action → Call thermostat actuator to increase heat
5. Notification → "Temperature dropped to 60Â°F. Adjusting thermostat."

**Why this scenario matters**:
- System-initiated, not user-initiated (proactive)
- Proves the "always observing brain" architecture
- IoT/smart home is a primary use case
- Event-driven, not query-driven

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| 0 | Sensor Integration | Receive sensor events | ðŸ”´ Not built |
| 1a | Episodic Memory | Store temperature events | âœ… Proven |
| 2c | Heuristic Matching | Match condition to event | âœ… Proven |
| 5 | Actuator Execution | Call thermostat | ðŸ”´ Not built |
| — | Salience Thresholds | Determine significance | âš ï¸ Structure exists |

---

### Scenario 7: Pattern Detection / Habituation

**Observation**: User has manually turned on porch light at sunset 5 times this week

**Expected flow**:
1. System observes repeated pattern
2. Confidence builds over repetitions
3. System suggests: "I notice you turn on the porch light at sunset. Should I do this automatically?"
4. User confirms → Creates automation heuristic
5. Next sunset → System acts proactively

**Why this scenario matters**:
- System learns without explicit feedback
- Proves habituation/pattern detection works
- Proactive suggestion (not just reaction)
- User remains in control (confirms before automating)

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| 1a | Episodic Memory | Track repeated events | âœ… Proven |
| 2a | Pattern Detection | Identify recurring patterns | ðŸ”´ Not built |
| — | Confidence Accumulation | Build confidence over time | ðŸ”´ Not built |
| 4 | Suggestion Generation | Propose automation | ðŸ”´ Not built |

---

### Scenario 8: Disambiguation

**User asks**: "Call Mike"

**Expected flow**:
1. Parse query → intent is "call someone named Mike"
2. Entity lookup → Multiple Mikes exist (Mike Mulcahy, Mike Smith)
3. System asks: "Which Mike? Mike Mulcahy or Mike Smith?"
4. User: "Mulcahy"
5. Execution → Initiate call to Mike Mulcahy

**Why this scenario matters**:
- Handles ambiguous requests gracefully
- Proves system can ask clarifying questions
- Common real-world situation
- Tests entity resolution with multiple matches

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| 1b | Semantic Memory | Store multiple entities with same name | âœ… Done |
| 2b | Entity Resolution | Detect ambiguity | ðŸ”´ Not built |
| — | Clarification Flow | Ask user, process response | ðŸ”´ Not built |
| 4 | Context Tracking | Remember clarification in conversation | ðŸ”´ Not built |

---

### Scenario 9: Negative Feedback / Unlearning

**User experience**:

```
Event: Temperature drops to 68Â°F
System: [Heuristic fires] "Adjusting thermostat to 72Â°F"
User: "No, don't do that. I like it cool."
System: [Decreases heuristic confidence]
         "Got it. I won't adjust the thermostat when it's 68Â°F."

Next time: Temperature drops to 68Â°F
System: [Heuristic confidence too low, doesn't fire]
        [May ask: "Temperature is 68Â°F. Want me to adjust the thermostat?"]
```

**Why this scenario matters**:
- Completes the learning loop (positive AND negative feedback)
- System can unlearn bad heuristics
- User corrections improve the system
- Proves TD learning / confidence adjustment works

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| 1c | Procedural Memory | Update heuristic confidence | âœ… Proven (test_td_learning.py) |
| — | Credit Assignment | Know which heuristic caused action | âœ… matched_heuristic_id propagated |
| — | Confidence Threshold | Don't fire low-confidence heuristics | âœ… Threshold = 0.5 |
| 4 | Feedback Processing | Handle negative feedback | âœ… UpdateHeuristicConfidence RPC |

---

## Layer Status Summary

| Layer | Component | Description | Status | Proven By |
|-------|-----------|-------------|--------|-----------|
| 0 | Storage | PostgreSQL + pgvector | âœ… Done | Local DB working |
| 1a | Episodic Memory | Event storage/retrieval | âœ… Done | Events store, query works |
| 1b | Semantic Memory | Entity + relationship storage | âœ… Done | test_semantic_memory.py |
| 1c | Procedural Memory | Heuristic storage + confidence | âœ… Done | test_td_learning.py |
| 2a | Event Retrieval | Query events by time/similarity | âš ï¸ Partial | Time works, similarity untested |
| 2b | Entity Retrieval | Query entities, traverse relationships | âœ… Done | test_semantic_memory.py |
| 2c | Heuristic Matching | Match events to heuristics (semantic) | âœ… Done | test_killer_feature.py |
| 3 | Skill Registry | Capability discovery | âœ… Done | test_skill_registry.py |
| 4a | LLM Reasoning | Process events with LLM | âœ… Done | Executive stub + Ollama |
| 4b | Pattern Extraction | Extract heuristic from feedback | âš ï¸ Partial | Works, quality varies |
| 4c | Query Routing | Route queries to skills | âœ… Done | test_e2e_query.py |
| 5 | Skill Execution | Call sensors/actuators | âš ï¸ Mocked | test_e2e_query.py (mock executor)

---

## Next Steps (Ordered)

### Phase 1: Semantic Memory Foundation âœ… COMPLETE
**Goal**: Prove we can store and retrieve entities with relationships

**Completed**: test_semantic_memory.py proves all criteria met.

### Phase 2: Episodic Retrieval Quality âš ï¸ PARTIAL
**Goal**: Prove similarity-based retrieval works

1. âœ… Storage works with embeddings
2. âš ï¸ Similarity-based retrieval not explicitly tested
3. âš ï¸ Threshold tuning needs validation

**Remaining**:
- Add test_episodic_similarity.py to prove semantic retrieval

### Phase 3: Skill Registry (Mock) âœ… COMPLETE
**Goal**: Prove skills can advertise capabilities

**Completed**: test_skill_registry.py proves all criteria met.

### Phase 4: End-to-End Query Flow âœ… COMPLETE
**Goal**: Prove "Is Steve online?" works with mocks

**Completed**: test_e2e_query.py proves full flow with mocked skill execution.

---

## Current Gaps and Next Work

### 1. Learning Loop Reliability
**Problem**: test_scenario_5_learning_loop.py has intermittent failures
- Pattern extraction quality varies
- Rust cache invalidation may be stale
- Feedback → heuristic path not always reliable

**Work needed**:
- Debug why learning loop fails intermittently
- Improve cache invalidation on confidence change
- Better pattern extraction prompts

### 2. Orchestrator Integration
**Problem**: Orchestrator doesn't fully integrate the learning path
- Events route to Executive correctly
- Executive can process events with LLM
- But: feedback doesn't consistently update existing heuristics

**Work needed**:
- Wire ProvideFeedback through to Memory UpdateHeuristicConfidence
- Track which heuristic fired for an event (for credit assignment)

### 3. Real Skill Execution
**Problem**: Skills execute via mock, not real code
- Skill manifests define capabilities
- Query routing works
- But: no actual skill code runs

**Work needed** (deferred for real sensor integration):
- Implement skill execution layer
- Connect to first real sensor (Discord? Home Assistant?)

---

## Test Inventory

| Test | File | What It Proves | Status |
|------|------|----------------|--------|
| Heuristic storage | test_heuristic_flow.py | LLM extracts pattern, stores to DB | âœ… Pass |
| Heuristic matching | test_killer_feature.py | Semantic matching skips LLM | âœ… Pass |
| TD Learning | test_td_learning.py | Confidence updates work, clamping works | âœ… Pass |
| Semantic Memory | test_semantic_memory.py | Entity + relationship storage, 2-hop expansion | âœ… Pass |
| Skill Registry | test_skill_registry.py | YAML manifests, capability query | âœ… Pass |
| E2E Query | test_e2e_query.py | Full "Is Steve online?" flow | âœ… Pass |
| Learning Loop | test_scenario_5_learning_loop.py | Full S2→S1 handoff scenarios | âš ï¸ Intermittent |
| Lab Bench | test_lab_bench.py | Evaluation UI integration | âœ… Pass |
| Evaluation RPCs | test_evaluation_rpcs.py | Response streaming for UI | âœ… Pass |

---

## Resolved Questions

1. **Entity schema**: âœ… Relational (entities + relationships tables in PostgreSQL)
2. **Skill manifest format**: âœ… YAML (see plugins/skills/minecraft-skill.yaml)
3. **Query routing**: âœ… Capability-based lookup via SkillRegistry
4. **Heuristic matching**: âœ… Semantic embeddings with 0.7 cosine similarity threshold

## Open Questions

1. **Ambiguity handling**: What if there are two Steves? (Entity resolution not implemented)
2. **Pattern extraction quality**: How to improve LLM-generated heuristics?
3. **Cache invalidation**: When should Rust LRU cache be invalidated?
4. **Real sensors**: Which sensor to integrate first? (Discord, Home Assistant, Minecraft mod)

---

## Relationship to ADRs

This roadmap validates the architecture defined in the ADRs:

- **ADR-0001**: Brain-inspired architecture (sensor → salience → executive)
- **ADR-0004**: Memory hierarchy (episodic, semantic, procedural)
- **ADR-0010**: Learning pipeline (heuristic formation)
- **ADR-0003**: Plugin/skill packs (capability manifests)

The Phase proves these architectural decisions are implementable and effective.

