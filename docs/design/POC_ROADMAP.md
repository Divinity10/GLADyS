# PoC Validation Roadmap

**Last Updated**: 2026-01-24

## Purpose

This document defines what the Proof of Concept must validate to confirm GLADyS is feasible. Rather than proving abstract mechanisms work, we prove the system can handle real-world tasks that humans find trivial.

The PoC is successful when we can demonstrate (with mocked sensors/actuators) that the architecture supports basic assistant functionality.

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
| 0 | Storage | PostgreSQL stores all data | ✅ Proven |
| 1a | Episodic Memory | Store/retrieve events | ✅ Proven |
| 1b | Semantic Memory | Store/retrieve entities & relationships | 🔴 Not built |
| 2 | Retrieval | Query relevant entities, traverse relationships | 🔴 Not proven |
| 3 | Skill Registry | Know what skills exist and their capabilities | 🔴 Not built |
| 4 | Routing/Planning | Connect query to correct skill | 🔴 Not built |
| 5 | Execution | Call skill, return result | 🔴 Not built |

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
| 1b | Semantic Memory | Know Mike's email address | 🔴 Not built |
| 3 | Skill Registry | Email skill registered | 🔴 Not built |
| 5 | Execution | Call email actuator | 🔴 Not built |

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
| 3 | Skill Registry | Calendar skill registered | 🔴 Not built |
| 5 | Execution | Call calendar sensor | 🔴 Not built |

---

### Scenario 4: Learning Loop (Original PoC Focus)

**Flow**: Event → LLM Reasoning → Feedback → Heuristic → Skip LLM next time

**Why this scenario matters**:
- The differentiator: system learns from experience
- Converts slow reasoning to fast heuristics
- Proves adaptive behavior works

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| 1a | Episodic Memory | Store events | ✅ Proven |
| 1c | Procedural Memory | Store heuristics | ✅ Proven |
| 2 | Heuristic Matching | Find matching heuristics | ✅ Proven (word overlap) |
| 4 | LLM Integration | Reason about events | ✅ Proven (Ollama) |
| 4 | Pattern Extraction | Extract heuristic from feedback | ⚠️ Partially proven |

---

### Scenario 5: "The Second Time is Faster" (Learning Experience)

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
| All from Scenario 1 | — | Full query flow | 🔴 Not built |
| 4b | Pattern Extraction | LLM generates useful heuristic | ⚠️ Quality untested |
| 1c | Heuristic Persistence | Survives restart | ✅ Proven (PostgreSQL) |
| 2c | Natural Language Matching | Handles query variations | ⚠️ Word overlap only |

---

### Scenario 6: Proactive Sensor Response

**Sensor event**: Temperature sensor reports 60°F (dropped from 72°F)

**Expected flow**:
1. Sensor sends event → Orchestrator receives
2. Salience evaluation → High (temperature drop is significant)
3. Heuristic check → "When temp drops below 65°F, adjust thermostat"
4. Action → Call thermostat actuator to increase heat
5. Notification → "Temperature dropped to 60°F. Adjusting thermostat."

**Why this scenario matters**:
- System-initiated, not user-initiated (proactive)
- Proves the "always observing brain" architecture
- IoT/smart home is a primary use case
- Event-driven, not query-driven

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| 0 | Sensor Integration | Receive sensor events | 🔴 Not built |
| 1a | Episodic Memory | Store temperature events | ✅ Proven |
| 2c | Heuristic Matching | Match condition to event | ✅ Proven |
| 5 | Actuator Execution | Call thermostat | 🔴 Not built |
| — | Salience Thresholds | Determine significance | ⚠️ Structure exists |

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
| 1a | Episodic Memory | Track repeated events | ✅ Proven |
| 2a | Pattern Detection | Identify recurring patterns | 🔴 Not built |
| — | Confidence Accumulation | Build confidence over time | 🔴 Not built |
| 4 | Suggestion Generation | Propose automation | 🔴 Not built |

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
| 1b | Semantic Memory | Store multiple entities with same name | 🔴 Not built |
| 2b | Entity Resolution | Detect ambiguity | 🔴 Not built |
| — | Clarification Flow | Ask user, process response | 🔴 Not built |
| 4 | Context Tracking | Remember clarification in conversation | 🔴 Not built |

---

### Scenario 9: Negative Feedback / Unlearning

**User experience**:

```
Event: Temperature drops to 68°F
System: [Heuristic fires] "Adjusting thermostat to 72°F"
User: "No, don't do that. I like it cool."
System: [Decreases heuristic confidence]
         "Got it. I won't adjust the thermostat when it's 68°F."

Next time: Temperature drops to 68°F
System: [Heuristic confidence too low, doesn't fire]
        [May ask: "Temperature is 68°F. Want me to adjust the thermostat?"]
```

**Why this scenario matters**:
- Completes the learning loop (positive AND negative feedback)
- System can unlearn bad heuristics
- User corrections improve the system
- Proves TD learning / confidence adjustment works

**Layer Requirements**:

| Layer | Component | What It Does | Status |
|-------|-----------|--------------|--------|
| 1c | Procedural Memory | Update heuristic confidence | 🔴 TD learning not built |
| — | Credit Assignment | Know which heuristic caused action | 🔴 Not built |
| — | Confidence Threshold | Don't fire low-confidence heuristics | ⚠️ Threshold exists (0.5) |
| 4 | Feedback Processing | Handle negative feedback | ⚠️ RPC exists, no confidence update |

---

## Layer Status Summary

| Layer | Component | Description | Status | Proven By |
|-------|-----------|-------------|--------|-----------|
| 0 | Storage | PostgreSQL + pgvector | ✅ Done | Local DB working |
| 1a | Episodic Memory | Event storage/retrieval | ✅ Done | Events store, query works |
| 1b | Semantic Memory | Entity + relationship storage | 🔴 Not built | — |
| 1c | Procedural Memory | Heuristic storage | ✅ Done | Heuristics store to DB |
| 2a | Event Retrieval | Query events by time/similarity | ⚠️ Partial | Time works, similarity untested |
| 2b | Entity Retrieval | Query entities, traverse relationships | 🔴 Not built | — |
| 2c | Heuristic Matching | Match events to heuristics | ✅ Done | test_killer_feature.py |
| 3 | Skill Registry | Capability discovery | 🔴 Not built | — |
| 4a | LLM Reasoning | Process events with LLM | ✅ Done | Executive stub + Ollama |
| 4b | Pattern Extraction | Extract heuristic from feedback | ⚠️ Partial | Works, quality untested |
| 4c | Query Routing | Route queries to skills | 🔴 Not built | — |
| 5 | Skill Execution | Call sensors/actuators | 🔴 Not built | — |

---

## Next Steps (Ordered)

### Phase 1: Semantic Memory Foundation
**Goal**: Prove we can store and retrieve entities with relationships

1. Design entity schema (entities table, relationships table)
2. Add entity proto messages
3. Implement store/retrieve RPCs
4. Test: Store Steve → Buggy → Minecraft, query it back

**Success Criteria**:
- Can store entity with type and attributes
- Can store relationship between entities
- Can query entity by name and get related entities
- Can traverse relationships (Steve → characters → games)

### Phase 2: Episodic Retrieval Quality
**Goal**: Prove similarity-based retrieval works

1. Store 10-15 varied events
2. Query by similarity
3. Verify related events return, unrelated don't

**Success Criteria**:
- Semantic similarity captures meaning (not just keywords)
- Threshold tuning gives reasonable precision/recall

### Phase 3: Skill Registry (Mock)
**Goal**: Prove skills can advertise capabilities

1. Define skill manifest format (YAML)
2. Create mock Minecraft skill manifest
3. Load manifests, query capabilities

**Success Criteria**:
- Can query "what skill checks player online status?"
- Returns correct skill with correct method

### Phase 4: End-to-End Query Flow
**Goal**: Prove "Is Steve online?" works with mocks

1. Wire together: query → entity lookup → skill routing → mock response
2. Test full flow

**Success Criteria**:
- Query returns correct answer
- All layers participate correctly

---

## Test Inventory

| Test | File | What It Proves |
|------|------|----------------|
| Heuristic storage | test_heuristic_flow.py | LLM extracts pattern, stores to DB |
| Heuristic matching | test_killer_feature.py | Matching skips LLM, 42x speedup |
| Entity storage | (not built) | Semantic memory works |
| Similarity retrieval | (not built) | Embeddings capture meaning |
| Skill discovery | (not built) | Capability registry works |
| E2E query | (not built) | Full "Is Steve online?" flow |

---

## Open Questions

1. **Entity schema**: Graph DB style (nodes + edges) or relational with foreign keys?
2. **Skill manifest format**: YAML? JSON? Proto?
3. **Query routing**: Rules-based or LLM-based?
4. **Ambiguity handling**: What if there are two Steves?

---

## Relationship to ADRs

This roadmap validates the architecture defined in the ADRs:

- **ADR-0001**: Brain-inspired architecture (sensor → salience → executive)
- **ADR-0004**: Memory hierarchy (episodic, semantic, procedural)
- **ADR-0010**: Learning pipeline (heuristic formation)
- **ADR-0003**: Plugin/skill packs (capability manifests)

The PoC proves these architectural decisions are implementable and effective.
