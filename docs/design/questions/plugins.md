# Plugins & Skills Questions

Plugin architecture, sensors, skills, actuators, integration models, and skill design patterns.

**Last updated**: 2026-01-31

---

## Open Questions

### Q: Preprocessor Plugin Constraints (§37)

**Status**: Open — design decision
**Priority**: Medium
**Created**: 2026-01-31
**Origin**: Relocated from `docs/research/OPEN_QUESTIONS.md`

Raw sensor data is often noisy. Preprocessors are optional plugins between a sensor and the salience gateway. Current thinking: they must be extremely fast (sub-millisecond, no model inference) and salience-affecting only (annotate/adjust salience hints, don't make routing decisions).

**Design questions**:

- **Where's the boundary between preprocessor and sensor?** If a doorbell camera does its own human detection, is that a preprocessor or a smarter sensor? Does the distinction matter architecturally?

- **What can preprocessors know?** Stateless = simple classification only. But useful preprocessing sometimes requires state (e.g., "third motion event in 60 seconds from same zone"). How much state is acceptable before a "preprocessor" becomes a subsystem?

- **Should preprocessors drop events entirely?** Current thinking: no — they annotate, gateway decides. But 200 wind-triggered events/hour are noise even when annotated. Is there a case for preprocessor-level suppression?

- **How do preprocessors interact with learning?** If a preprocessor incorrectly suppresses a real threat, the error is invisible — gateway never sees it, learning pipeline never gets the feedback signal. How do we detect preprocessing errors?

**Relevant**: ADR-0013 Section 4.1 (pipeline position), ADR-0003 (plugin architecture)

---

### Q: Actuator/Effector Gap (§1)

**Status**: Stale - predates ADR-0011
**Priority**: High (if actuators proceed)
**Note**: Most of this is addressed in ADR-0011. Review for any remaining gaps.

#### Original Problem

The architecture shows sensors (input) flowing to Executive which produces speech (TTS output). But GLADyS should also control physical devices:
- Thermostats, fans, HVAC
- Humidifiers / dehumidifiers
- Smart lights
- Door locks (high security concern)

**Gap**: No actuator plugin type exists. Skills provide knowledge to Executive, not device control.

#### Original Questions (Now Mostly Resolved by ADR-0011)

- Should actuators be a new plugin type or an extension of skills? → **New type (ADR-0011)**
- What's the command validation / safety bounds model? → **See ADR-0011 §4**
- Rate limiting to prevent oscillation? → **See ADR-0011 §5**
- Confirmation requirements for high-impact actions? → **See ADR-0011 §6**

---

### Q: Tiered Actuator Security (§3)

**Status**: Open - partially addressed in ADR-0011
**Priority**: High (if actuators proceed)

#### Problem

ADR-0008 security model is good for data privacy, but physical actuators have different risk profiles:

| Plugin Type | Risk if Compromised |
|-------------|---------------------|
| Game sensor | Annoyance |
| Screen capture | Privacy violation |
| Thermostat | Comfort / pipe freeze |
| Door lock | Physical security breach |

#### Open Questions

- Should physical security actuators (locks, garage doors) require higher trust than entertainment plugins?
- Should there be an "actuator trust tier" separate from sensor trust?
- What confirmation UX for dangerous actions?

**Note**: ADR-0011 has some coverage here but the trust tier model may need expansion.

---

### Q: Plugin Taxonomy and Processing Pipeline (§9)

**Status**: Open - design captured but DAG questions remain
**Priority**: High

#### Proposed Taxonomy

| Type | Direction | Trigger | Purpose |
|------|-----------|---------|---------|
| **Sensor** | World → Brain | Push | Produces **events** |
| **Skill** | Brain ↔ Brain | Varies | Transforms, analyzes, provides knowledge |
| **Actuator** | Brain → World | Push | Executes **commands** |

#### Skill Subtypes

| Subtype | When it runs | Purpose | Examples |
|---------|--------------|---------|----------|
| **Preprocessor** | Pre-salience | Transform/enrich raw sensor data | STT, tone analysis, OCR |
| **Query** | On-demand | Answer questions during reasoning | Knowledge lookup, API query |
| **Analyzer** | Either | Complex assessment | Threat detection, comfort evaluation |

#### DAG Processing Model

Preprocessors form a DAG, not a linear chain:

```
Audio Stream
     │
     ├──→ [Word Recognition] ──┬──→ [Semantic Meaning] → Salience
     │                         │
     └──→ [Tone Detection] ────┘
```

Manifest declares dependencies:
```yaml
plugin_id: semantic_meaning_detector
type: skill
subtype: preprocessor
requires:
  - word_recognition.transcript
  - tone_detection.emotion
```

#### Performance Requirements

| Stage | Budget | Rationale |
|-------|--------|-----------|
| Raw sensor → Preprocessor | <50ms | Perceptible lag starts ~100ms |
| Preprocessor chain total | <200ms | Leave room for salience + Executive |
| Full end-to-end | <1000ms | ADR-0005 budget |

#### Open Questions

1. **Unified vs separate types**: Should preprocessors be a skill subtype or a fourth plugin type?
2. **Caching strategy**: How cache expensive preprocessor results?
3. **Error handling**: Preprocessor fails - skip it or block the pipeline?
4. **Hot-swap**: Can preprocessors be updated without restarting the system?
5. **DAG validation**: How detect cycles or missing dependencies at manifest load time?
6. **Timeout propagation**: If one node times out, how does it affect downstream nodes?

---

### Q: Skill Architecture Design Direction (§25)

**Status**: Design captured (pre-PoC)
**Priority**: Medium (PoC uses simple model; full design for post-PoC)
**Created**: 2026-01-24

#### Context

During Phase 3 planning, questions emerged about how skills interact with core services. These decisions are captured here but **not implemented in PoC**.

#### Skill Categories (from ADR-0003)

| Category | Purpose | Example |
|----------|---------|---------|
| `style_modifier` | Adjust tone/personality | formal_mode |
| `domain_expertise` | Passive knowledge | minecraft-expertise |
| `capability` | Active abilities | minecraft-skill (check_player_status) |
| `language` | Translation/localization | spanish, pirate_speak |
| `outcome_evaluator` | Assess results | was_helpful |

#### Design Decisions (Post-PoC)

| Topic | Direction | Rationale |
|-------|-----------|-----------|
| **Skill dependencies** | Skills declare `requires: [memory, llm]` in manifest | Explicit > implicit |
| **LLM access** | Executive provides managed client with queuing | Prevents runaway LLM calls |
| **Actuator routing** | Skills propose actions, Orchestrator dispatches | Safety stays centralized |
| **Skill heuristics** | Skills can contribute heuristics on load | Pack ships with fast-path rules |
| **Memory access** | Two-tier: Executive mediates simple cases; autonomous skills get Memory client | Based on complexity |

#### Manifest Extension (Post-PoC)

```yaml
plugin_id: evony-expertise
type: skill
category: domain_expertise

requires:
  - memory
  - llm
  - sensors:
      - evony-game-state

capabilities:
  - attack_planning
  - defense_analysis

contributes_heuristics:
  - condition: "user asks about attacking in Evony"
    action: {delegate: "evony-expertise", method: "plan_attack"}
```

#### Why PoC Uses Simple Model

| Reason | Detail |
|--------|--------|
| **Prove core loop** | Event → salience → routing → response |
| **Avoid infrastructure** | No managed LLM client, no skill sandboxing |
| **Focus** | Heuristic learning is the differentiator |

#### Open for Post-PoC

1. Skill sandboxing (prevent misbehaving skills from overwhelming Memory/LLM)
2. Managed LLM client API (rate limiting, cost tracking)
3. Skill lifecycle (hot reload, version conflicts)
4. Multi-skill coordination (when multiple skills could handle a query)
5. Heuristic conflict (pack heuristic vs learned heuristic)

---

## Resolved

### R: Actuator System Design (§6)

**Decision**: See ADR-0011
**Date**: 2026-01-XX
**ADR**: [ADR-0011](../../adr/ADR-0011-Actuator-Subsystem.md)

All original questions resolved:
1. **Plugin model**: New plugin type
2. **Command validation**: Schema validation + safety bounds
3. **Rate limiting**: Per-actuator configurable limits
4. **Feedback**: Async with timeout
5. **Dependencies**: Manifest declares preconditions
6. **Conflict resolution**: Priority model + user override
7. **Latency budget**: Profile-based (see [infrastructure.md](infrastructure.md))
8. **Confirmation UX**: Configurable per-actuator

---

### R: Integration Plugin Model (§10)

**Decision**: Start with Home Assistant; design generic Integration interface
**Date**: 2026-01-XX

#### Why Home Assistant First

| Factor | Home Assistant | Google/Amazon |
|--------|---------------|---------------|
| **Philosophy** | Local-first, privacy-focused | Cloud-dependent |
| **Device breadth** | 2000+ integrations | Large but walled garden |
| **API stability** | Open, well-documented | Proprietary |
| **GLADyS alignment** | Privacy, user control, local processing | Cloud dependency |

**Strategy**: Design generic `Integration` interface, implement Home Assistant first, add Google/Amazon when user demand justifies.

#### Proposed Integration Manifest

```yaml
plugin_id: home_assistant
type: integration
version: 1.0.0

connection:
  type: websocket
  url: ws://homeassistant.local:8123/api/websocket
  auth: long_lived_token  # reference to secure credential store

expose:
  sensors:
    - entity_id: sensor.living_room_temperature
      as: living_room_temp
      unit: celsius

  actuators:
    - entity_id: climate.nest_thermostat
      as: thermostat
      trust_tier: comfort
      capabilities:
        - set_temperature
        - set_hvac_mode
      rate_limit: 1/minute

    - entity_id: lock.front_door
      as: front_door_lock
      trust_tier: security  # → routes to audit_security table
      confirmation_required: true
```

#### Key Design Points

1. **Per-device trust tiers**: Lock is `security`, thermostat is `comfort`
2. **Rate limiting per actuator**: Prevents oscillation at device level
3. **Confirmation requirements**: High-risk actuators can require user confirmation
4. **Virtual sensors/actuators**: GLADyS sees `front_door_lock`, not `lock.front_door`

#### Remaining Open Questions

1. **Credential storage**: Where do long-lived tokens go? (Coordinate with ADR-0008)
2. **Entity discovery**: Auto-discover HA entities or require explicit mapping?
3. **State sync**: How often to poll HA for state changes vs. websocket push?
4. **Offline handling**: HA unavailable - how does GLADyS degrade gracefully?

---

## Reference: Validation Use Cases

### UC1: Gaming Companion (Aperture)
```
[Game State Sensor] → [Threat Analyzer Skill] → Salience → Executive → Speech
                                                                    ↘ [Game Input Actuator]
```

### UC2: Environmental Comfort
```
[Temp Sensor] ─────┐
[Humidity Sensor] ─┼→ [Comfort Analyzer] → Salience → Executive → [HVAC Actuator]
[CO2 Sensor] ──────┘
```

### UC4: Physical Security (High-Risk)
```
[Motion Sensor] → [Person Detector] → Salience → Executive → [Door Lock Actuator]
                                                          ↘ User Confirmation
```
