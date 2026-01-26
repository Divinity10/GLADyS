# Cross-Cutting Questions

Topics that span multiple subsystems: audit, output routing, integration, and architectural gaps.

**Last updated**: 2026-01-25

---

## Open Questions

### Q: Cross-Cutting Integration Questions (§12)

**Status**: Open
**Priority**: Medium

#### Questions

1. **Executive decision**: How choose between speak vs actuate vs both vs neither?
2. **Continuous data**: Temperature every 5s - how enter system without flooding salience? (See [data-types.md](data-types.md))
3. **MVP scope**: Minimum to prove architecture works?
4. **Testing strategy**: Learning systems are non-deterministic - how test?

---

### Q: Output Routing and User Presence (§13)

**Status**: Gap - needs design
**Priority**: High

#### Problem

The Executive decides WHAT to communicate. But we haven't specified WHERE:

```
Executive → "Someone's at the door" → Output Router → ???
                                            │
                                            ├─→ Computer speakers (if at desk)
                                            ├─→ Google Home (if in that room)
                                            ├─→ Phone notification (if away)
                                            └─→ Smart display (show video + audio)
```

Output is distinct from actuators:
- **Actuator**: changes physical state (thermostat, lock)
- **Output**: delivers information TO the user (speech, notification, display)

#### Design Inspiration Sources

| Domain | Relevant Concepts | What It Offers |
|--------|-------------------|----------------|
| **Biology** | Motor neurons, proprioception | Brain learns which "muscle" to activate |
| **Cellular/WiFi** | Handoff, roaming, signal strength | User "roams" between devices |
| **Networking (QoS)** | Priority queues, traffic classes | Urgent messages get different treatment |
| **Pub/Sub** | Topic subscriptions, routing | Devices subscribe to message types |
| **Human Assistant** | Escalation, context awareness | Adapts channel to situation |
| **Service Mesh** | Retry policies, failover | If first output fails, try another |

#### Proposed: Hybrid Model

Combine the best from each domain:

1. **Presence detection** (cellular/wifi) - Track which devices the user is near
2. **Device capabilities** (IoT) - This device has display, that one is audio-only
3. **Message priority** (QoS) - Security alert vs routine notification
4. **Subscription model** (pub/sub) - User preferences: "always send X to phone"
5. **Escalation** (human assistant) - No response on speaker → try phone
6. **Learning** (biology) - Over time, learn "Scott responds faster from X at time Y"

#### Human Assistant Analogy

A good human assistant would:
- Tap your shoulder if you're right there
- Call your name if you're in another room
- Text if you're away
- Escalate if urgent and no response

GLADyS should behave similarly.

#### Routing Factors

| Factor | Source | Example |
|--------|--------|---------|
| **User location** | Presence sensors, device activity | Keyboard active → at computer |
| **Device availability** | Health checks | Google Home reachable? |
| **Message priority** | Event type | Security = high, routine = low |
| **Time of day** | Clock | 2am → silent notification, not speaker |
| **User preferences** | Configuration + learned | "Security events always to phone" |
| **Content type** | Message metadata | Video doorbell → device with display |
| **Response history** | Learning | "Scott responds from phone evenings" |

#### Open Questions

1. **Presence detection**: What signals indicate user location?
2. **Escalation policy**: How long to wait before trying next device?
3. **Multi-user**: Multiple users in household - route to correct person?
4. **Privacy**: Don't announce sensitive info on shared speaker?
5. **Output as plugin?**: Is the output router a plugin, or core system?
6. **Acknowledgment**: How know if user received the message?
7. **Do Not Disturb**: User/device-level DND modes?

#### Relationship to Actuators

Output devices could be modeled as actuators with special semantics:
- `type: output` vs `type: actuator`
- Or: Output router as separate subsystem that USES actuators

Decision needed: unified model or separate concepts?

---

### Q: Architectural Gaps Inventory (§14)

**Status**: Partial - some resolved, some open
**Priority**: Varies
**Created**: 2026-01-18

Gap analysis performed after ADR-0010/0011/0012 completion.

#### Resolved Gaps

| Gap | Resolution |
|-----|------------|
| Salience Subsystem | ADR-0013 |
| Executive Decision Loop | ADR-0014 |
| Personality / Persona | ADR-0015 |

#### Medium Priority (User Experience)

##### 14.3 Output Routing / User Presence
See [§13 above](#q-output-routing-and-user-presence-13)

##### 14.5 Multi-User / Household
**Gap**: Mentioned as open question in ADR-0010 but it's architectural.

**Questions**:
- Whose preferences win when users conflict?
- Per-user profiles vs household consensus?
- Privacy between household members?
- Voice identification for personalization?

**Recommendation**: Design doc first, ADR when decisions solidify

#### Lower Priority (Operational)

##### 14.6 Error Handling / Graceful Degradation
**Gap**: Scattered mentions but no coherent strategy.

**Questions**:
- What happens when subsystems fail?
- User communication about failures?
- Self-healing behaviors?
- Fallback chains?

##### 14.7 Upgrade / Migration
**Gap**: Not addressed.

**Questions**:
- Schema migration for memory/audit?
- Plugin version compatibility?
- Rolling upgrades?

**Recommendation**: Defer until closer to v1.0

##### 14.8 Testing Strategy
**Gap**: Not addressed.

**Questions**:
- How do you regression test a learning system?
- Simulation environments?
- Preventing learned behavior drift?

#### Documentation Gaps (Resolved)

| Doc | Status |
|-----|--------|
| GLOSSARY.md | Created 2026-01-18 |
| PERSONALITY_IDENTITY_MODEL.md | Created 2026-01-19 (deferred Big 5 design) |
| PERSONALITY_TEMPLATES.md | Created 2026-01-19 (11 test archetypes) |

---

### Q: PoC vs ADR-0005 Spec Gaps (§19)

**Status**: Tracked for post-MVP (intentional simplification)
**Priority**: Low
**Created**: 2026-01-22

#### Context

The PoC implementation uses simplified gRPC contracts compared to ADR-0005 specifications. This is intentional - the ADR defines the target architecture, while the PoC proves the core concept with minimal viable contracts.

#### SalienceGateway Service

| Aspect | ADR-0005 §4.5 Spec | PoC Implementation |
|--------|--------------------|--------------------|
| Package | `gladys.v1` | `gladys.memory` |
| Service name | `SalienceGatewayService` | `SalienceGateway` |
| RPCs | `EvaluateEvent`, `EvaluateEventBatch`, `ModulateSalience` | `EvaluateSalience` only |
| Request | Full `Event` + `EvaluationContext` | Flat fields (event_id, source, raw_text, etc.) |
| Response | Enriched event + relevant memories + user profile | Salience vector + from_cache + matched_heuristic_id |

#### Rationale for Simplification

1. **Minimal viable path**: PoC needs to prove event → salience → routing works
2. **Avoid premature complexity**: Rich context can be added when needed
3. **Faster iteration**: Simpler contracts = faster debugging
4. **Memory retrieval deferred**: `relevant_memories` requires additional integration

#### Post-MVP Expansion Path

1. Add `EvaluateEventBatch` for throughput optimization
2. Add `ModulateSalience` for Executive feedback loop
3. Expand request to include `EvaluationContext` (active goals, focus entities)
4. Expand response to include relevant memories and user profile snapshot
5. Migrate to `gladys.v1` package for consistency

**No Action Required**: This is documentation of intentional scope limitation.

---

## Resolved

### R: Audit System Design (§7)

**Decision**: See ADR-0012
**Date**: 2026-01-18
**ADR**: [ADR-0012](../../adr/ADR-0012-Audit-Subsystem.md)

#### Architecture

- Audit lives OUTSIDE brain, but readable by it
- Append-only, no compaction, immutable
- Brain can READ audit for context but cannot MODIFY

#### Storage

- Three tiered tables: `audit_security` (Merkle), `audit_actions` (hash), `audit_observations` (light)
- Event type taxonomy: `category.subject.action` with `source` as separate field
- Tiered storage: hot (SSD) → warm (HDD) → cold (archive)

#### Retention

- Per-event-type, configurable: -1=forever, >0=N days, 0=don't audit
- Policy hierarchy: System Defaults → Org Policy (locked) → User Preferences
- Security events default to forever; sensor observations default to 30 days

#### Access

- Separate query interface from memory (structured, not semantic)
- No delete before retention expiry (no exceptions)

#### Remaining Open

1. Plugin manifest schema for declaring emitted event types
2. Export format (JSON lines vs Parquet)
3. Merkle tree implementation choice
4. Cross-device audit sync

---

### R: Orchestrator Language (§18)

**Decision**: Python
**Date**: 2026-01-22

See:
- [SUBSYSTEM_OVERVIEW.md §3](../SUBSYSTEM_OVERVIEW.md)
- [ORCHESTRATOR_IMPL_PROMPT.md](../ORCHESTRATOR_IMPL_PROMPT.md)

Rationale: ML ecosystem, rapid prototyping, team familiarity. Performance-critical paths handled by Rust memory fast-path.

---

## Reference: Validation Use Cases

### UC3: Voice Interaction (DAG Processing)

```
[Microphone] → [STT Preprocessor] ──┬→ [Semantic Meaning] → Salience → Executive → [TTS]
                                    │
              [Tone Preprocessor] ──┘
```

Tests: DAG preprocessor model, parallel execution

### UC6: Multi-Modal Analysis

```
[Screen Capture] → [OCR] ────────────┐
                                     ├→ [Context Analyzer] → Salience → Executive
[Audio] → [STT] → [Speaker ID] ──────┘
```

Tests: Complex DAG, multiple sensor sources merging
