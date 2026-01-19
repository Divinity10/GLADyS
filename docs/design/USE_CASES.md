# GLADyS Use Cases

This document catalogs use cases discussed during design. Each use case helps validate architectural decisions and identifies requirements for sensors, skills, actuators, and learning.

---

## Use Case Index

| ID | Name | Domain | Status | Latency Profile |
|----|------|--------|--------|-----------------|
| UC-01 | Ring Doorbell Notification | Home | MVP | `conversational` |
| UC-02 | Minecraft Gaming Companion | Gaming | First Release | `realtime` |
| UC-03 | RuneScape (OSRS) Companion | Gaming | Planned | `realtime` |
| UC-04 | Evony Strategic Advisor | Gaming | Speculative | `conversational` |
| UC-05 | Home Climate Control | Home | Planned | `comfort` |
| UC-06 | Security Monitoring | Home | Planned | `realtime` |
| UC-07 | Voice Interaction | Cross-cutting | Core | `conversational` |

---

## UC-01: Ring Doorbell Notification

**Domain**: Home Automation
**Status**: MVP (stepping stone)
**Priority**: High - validates core pipeline

### Description

When someone rings the doorbell or motion is detected, GLADyS notifies the user via desktop notification and audio on their computer.

### Why This First

- Proves: sensor → brain → output pipeline
- Validates: Home Assistant integration
- Simple: no complex salience, no actuators
- Scott's preference: computer/phone output, not Google Home speakers

### Architecture

```
Ring Doorbell → Home Assistant → HA Integration Plugin → Salience → Executive → Desktop Output
```

### Components

| Component | Type | Notes |
|-----------|------|-------|
| Home Assistant Integration | Sensor (via Integration) | Receives doorbell events |
| Basic Salience | Skill | "Someone at door" = high salience |
| Simple Executive | Executive | Decide to notify |
| Desktop Notifier | Output | Toast notification + TTS |

### Latency Profile

`conversational` (<1000ms) - user should hear notification quickly but not safety-critical

### Learning Opportunities

- Learn which motion events are false positives (wind, animals)
- Learn user's response patterns (do they care at 3am?)
- Learn preferred notification modality by context

### Success Criteria

- [ ] Doorbell ring → notification in <2 seconds
- [ ] Motion detection → notification (with learned filtering)
- [ ] User can see event in audit log

---

## UC-02: Minecraft Gaming Companion

**Domain**: Gaming
**Status**: First Release
**Priority**: High - primary launch target

### Description

GLADyS acts as an AI companion while playing Minecraft, providing contextual awareness, suggestions, and information via voice.

### Why This Target

- Aperture mod already planned (exposes game state via local API)
- Complex salience opportunities (combat, exploration, building)
- Voice output natural (user is at computer, hands on keyboard)
- Mike's expertise in Minecraft modding

### Architecture

```
Aperture Mod → Game Sensor Plugin → Preprocessors → Salience → Executive → Voice Output
```

### Components

| Component | Type | Notes |
|-----------|------|-------|
| Aperture Bridge | Sensor | Exposes: player state, inventory, nearby entities, world state, chat |
| Combat Detector | Preprocessor | Identify combat situations |
| Threat Assessor | Skill (Analyzer) | Evaluate danger level |
| Game Knowledge | Skill (Query) | Minecraft wiki, crafting recipes |
| Voice Output | Output | TTS to computer speakers |

### Latency Profile

`realtime` (<500ms) - combat situations need fast response

### Trust Tier

N/A - no physical actuators. Game actuators (if added later) would be `comfort` tier.

### Learning Opportunities

- Learn player's skill level (adjust advice complexity)
- Learn preferred playstyle (builder vs explorer vs fighter)
- Learn what information is helpful vs annoying
- Track resource gathering rates (Gamma-Poisson)
- Preferences on warning verbosity (Beta-Binomial)

### Bayesian Models Used

| Pattern | Model | Example |
|---------|-------|---------|
| Warning acceptance | Beta-Binomial | "Did player act on low health warning?" |
| Preferred difficulty | Normal-Gamma | "What mob density triggers stress?" |
| Play session length | Gamma-Poisson | "How long until player takes a break?" |

### Success Criteria

- [ ] Warn about low health/hunger before critical
- [ ] Suggest crafting recipes contextually
- [ ] Identify nearby threats before player sees them
- [ ] Learn to reduce noise for experienced players

---

## UC-03: RuneScape (OSRS) Companion

**Domain**: Gaming
**Status**: Planned (secondary target)
**Priority**: Medium

### Description

GLADyS assists Old School RuneScape players during long grinding sessions, PvP encounters, and complex game activities.

### Why This Target

- RuneLite client has existing plugin ecosystem exposing game state
- Long grinding sessions benefit from AI companion
- PvP (Wilderness) has high-stakes, time-critical decisions
- Third-party client infrastructure = less custom work

### Architecture

```
RuneLite Plugin → Game Sensor → Preprocessors → Salience → Executive → Voice Output
```

### Components

| Component | Type | Notes |
|-----------|------|-------|
| RuneLite Bridge | Sensor | Player stats, inventory, nearby players, location |
| PvP Detector | Preprocessor | Identify Wilderness threats |
| Skill Tracker | Skill (Analyzer) | XP rates, time to level |
| Price Lookup | Skill (Query) | GE prices, flip opportunities |

### Latency Profile

`realtime` (<500ms) - PvP encounters are life-or-death (in-game)

### Learning Opportunities

- Learn grinding patterns and optimal routes
- Track XP rates (Gamma-Poisson)
- Learn risk tolerance in Wilderness
- Predict when player is about to bank

### Success Criteria

- [ ] Warn about PKers in Wilderness before engagement
- [ ] Track and report XP/hour rates
- [ ] Suggest bank trips based on inventory value
- [ ] Learn player's risk tolerance

---

## UC-04: Evony Strategic Advisor

**Domain**: Gaming
**Status**: Speculative (Scott's use case)
**Priority**: Low (exploration)

### Description

GLADyS analyzes Evony game state to recommend troop compositions, track resource rates, and provide strategic advice.

### Technical Challenges

- No official API - need alternative sensor approaches
- Windows client makes this feasible (vs mobile-only games)
- ToS considerations (personal use, not distribution)

### Sensor Approaches (Exploratory)

| Approach | Complexity | Risk |
|----------|------------|------|
| Memory reading | High | Game updates break it |
| WinDivert network hook | Medium | Intercept game protocol |
| DLL injection | High | Anticheat concerns |
| Screen capture + OCR | Medium | Slower, less precise |

### Architecture (Conceptual)

```
Evony Client → [Sensor TBD] → Game Sensor → Pattern Detector → Executive → Desktop Output
```

### Components

| Component | Type | Notes |
|-----------|------|-------|
| Evony Sensor | Sensor | TBD - depends on approach |
| Troop Analyzer | Skill (Analyzer) | Evaluate troop compositions |
| Rate Tracker | Learning | Gathering/training rates |
| Boss Timer | Skill | Track boss spawn times |

### Learning Opportunities

- Gathering cycle rates (Gamma-Poisson) - very periodic
- Training completion times (Gamma-Poisson)
- Boss spawn patterns (Gamma-Poisson)
- Troop composition preferences (could use heuristics)

### Two Distinct Features

1. **Pattern Learning**: Track rates, predict completion times (learning subsystem)
2. **Tactical Advisor**: Recommend troop layers for attacks (skill plugin, rule-based or LLM)

### Success Criteria

- [ ] Accurately predict gathering completion
- [ ] Recommend effective troop compositions
- [ ] Alert on boss spawns
- [ ] Learn user's playstyle preferences

---

## UC-05: Home Climate Control

**Domain**: Home Automation
**Status**: Planned
**Priority**: Medium

### Description

GLADyS manages thermostat, fans, and humidity based on learned preferences, occupancy, and external conditions.

### Architecture

```
Temperature Sensors → HA Integration → Salience → Executive → Thermostat Actuator
                                                           → Fan Actuator
```

### Components

| Component | Type | Trust Tier | Notes |
|-----------|------|------------|-------|
| Temperature Sensor | Sensor (via HA) | N/A | Room temperatures |
| Weather API | Sensor | N/A | External conditions |
| Thermostat | Actuator | `comfort` | Set temperature, mode |
| Smart Fan | Actuator | `comfort` | On/off, speed |
| Occupancy Detector | Sensor | N/A | Motion, phone presence |

### Latency Profile

`comfort` (<5000ms) - no urgency, should be slow to prevent oscillation

### Rate Limiting

Critical - thermostat changes must be rate-limited (1/minute max per ADR-0011)

### Learning Opportunities

- Preferred temperature by time of day (Normal-Gamma)
- Preferred temperature by activity (working vs sleeping)
- Acceptable humidity range (Normal-Gamma)
- Occupancy patterns (Gamma-Poisson for arrival times)

### Success Criteria

- [ ] Maintain comfortable temperature without user intervention
- [ ] Pre-cool/heat before user arrives home
- [ ] Respect rate limits (no oscillation)
- [ ] Learn and adapt to preference changes

---

## UC-06: Security Monitoring

**Domain**: Home Automation
**Status**: Planned
**Priority**: High (safety-critical)

### Description

GLADyS monitors security cameras, door/window sensors, and locks, alerting users to potential threats and optionally controlling locks.

### Architecture

```
Motion Sensors → HA Integration → Threat Assessment → Executive → Alert Output
Door Sensors  →                                                → Lock Actuator (with confirmation)
Cameras       →
```

### Components

| Component | Type | Trust Tier | Notes |
|-----------|------|------------|-------|
| Motion Sensors | Sensor (via HA) | N/A | PIR, camera motion |
| Door/Window Sensors | Sensor (via HA) | N/A | Open/closed state |
| Camera Feed | Sensor | N/A | May need person detection preprocessor |
| Door Lock | Actuator | `security` | Confirmation required |
| Garage Door | Actuator | `security` | Confirmation required |

### Latency Profile

`realtime` (<500ms) for alerts - safety carve-out applies

### Safety Considerations

- Lock/unlock commands require confirmation (per ADR-0011)
- All security actions logged to `audit_security` table with Merkle integrity
- Never auto-unlock without explicit user confirmation
- Alert escalation if user doesn't respond

### Learning Opportunities

- Learn normal motion patterns (reduce false alarms)
- Learn expected arrival/departure times
- Identify anomalous patterns

### Success Criteria

- [ ] Alert on unexpected motion when away
- [ ] Reduce false positives from pets, wind
- [ ] Lock confirmation flow works reliably
- [ ] Full audit trail for all lock events

---

## UC-07: Voice Interaction

**Domain**: Cross-cutting
**Status**: Core capability
**Priority**: High

### Description

User speaks to GLADyS, GLADyS responds via voice. Underpins most other use cases.

### Architecture

```
Microphone → Audio Sensor → STT Preprocessor → Salience → Executive → TTS Output → Speaker
                         → Tone Analyzer (optional)
```

### Components

| Component | Type | Notes |
|-----------|------|-------|
| Audio Sensor | Sensor | Continuous audio capture |
| Wake Word Detector | Preprocessor | "Hey GLADyS" or similar |
| STT (Speech-to-Text) | Preprocessor | Whisper or similar |
| Tone Analyzer | Preprocessor (optional) | Disabled per design decision |
| TTS (Text-to-Speech) | Output | Voice synthesis |

### Latency Profile

`conversational` (<1000ms) - natural conversation pace

### Preprocessor DAG

```
Audio → Wake Word ─┬─→ STT ──────→ Salience
                   └─→ Tone (disabled)
```

Note: Tone analysis disabled by design (unreliable, invasive per Scott's philosophy)

### Learning Opportunities

- Learn speech patterns for better recognition
- Learn preferred response verbosity
- Learn when user wants proactive speech vs silence

### Success Criteria

- [ ] Reliable wake word detection
- [ ] STT accuracy >95% for clear speech
- [ ] Response latency <1000ms
- [ ] Natural conversation flow

---

## Cross-Cutting Observations

### Latency Profile Distribution

| Profile | Use Cases |
|---------|-----------|
| `realtime` | UC-02, UC-03, UC-06 |
| `conversational` | UC-01, UC-04, UC-07 |
| `comfort` | UC-05 |
| `background` | Learning in all cases |

### Bayesian Model Usage

| Model | Use Cases |
|-------|-----------|
| Beta-Binomial | UC-02 (warning acceptance), UC-05 (comfort ok?) |
| Normal-Gamma | UC-02 (difficulty), UC-05 (temperature preference) |
| Gamma-Poisson | UC-02/03/04 (rates), UC-05 (arrival times) |

### Trust Tier Distribution

| Tier | Use Cases |
|------|-----------|
| N/A (no actuators) | UC-01, UC-02, UC-03, UC-04, UC-07 |
| `comfort` | UC-05 |
| `security` | UC-06 |

---

## How to Use This Document

1. **When designing a feature**: Check if a relevant use case exists, use it to validate design
2. **When adding ADR decisions**: Reference which use cases drove the decision
3. **When prioritizing work**: Use case status indicates implementation order
4. **When testing**: Use cases define acceptance criteria

## Adding New Use Cases

Use this template:

```markdown
## UC-XX: [Name]

**Domain**: [Gaming/Home/Productivity/Health]
**Status**: [MVP/First Release/Planned/Speculative]
**Priority**: [High/Medium/Low]

### Description
[What does this use case do?]

### Architecture
[Data flow diagram]

### Components
[Table of sensors, skills, actuators]

### Latency Profile
[realtime/conversational/comfort/background]

### Learning Opportunities
[What patterns can be learned?]

### Success Criteria
[Checkboxes for acceptance]
```
