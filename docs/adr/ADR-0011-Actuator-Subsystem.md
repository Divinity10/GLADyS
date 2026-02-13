# ADR-0011: Actuator Subsystem

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Date** | 2026-01-18 |
| **Owner** | Mike Mulcahy (Divinity10), Scott (scottcm) |
| **Contributors** | |
| **Module** | Actuators |
| **Tags** | actuators, iot, smart-home, effectors, commands |
| **Depends On** | ADR-0001, ADR-0003, ADR-0008, ADR-0012 |

---

## 1. Context and Problem Statement

GLADyS is a *generalized* system that should control physical devices, not just observe and speak. Use cases include:

- Smart home: thermostats, fans, humidifiers, lights
- Security: door locks, garage doors, cameras
- Gaming: in-game actions via Aperture
- Productivity: application control, notifications

The current architecture has sensors (input) and speech (output) but no actuator subsystem for physical device control.

---

## 2. Decision Drivers

1. **Generalization**: Support diverse device types and protocols
2. **Safety**: Prevent dangerous commands (unlock doors at 2am)
3. **Security**: Actuators need higher trust than passive sensors
4. **Feedback**: Know if commands succeeded or failed
5. **Rate limiting**: Prevent oscillation (thermostat toggling)
6. **Audit**: All actuator commands must be logged

---

## 3. Decision

### 3.1 Integration Plugin Model

Most physical devices connect through smart home ecosystems (Home Assistant, Google Home, Amazon Alexa) rather than directly. GLADyS uses **integration plugins** that bridge to these ecosystems.

**Strategy**: Design a generic `Integration` interface, implement Home Assistant first (local-first, open API, aligns with GLADyS philosophy), add Google/Amazon when demand justifies.

```yaml
plugin:
  id: home-assistant
  name: "Home Assistant Integration"
  version: "1.0.0"
  type: integration
  description: "Bridge to Home Assistant smart home platform"

resources:
  gpu:
    required: false
  memory_mb: 128

lifecycle:
  startup:
    timeout_ms: 10000
  health:
    heartbeat_interval_ms: 30000
    failure_threshold: 3

integration:
  platform: home_assistant

  connection:
    type: websocket
    url_setting: ha_url           # Reference to user setting
    auth_setting: ha_token        # Reference to secure credential store

  # Virtual sensors exposed to GLADyS
  sensors:
    - entity_id: sensor.living_room_temperature
      as: living_room_temp
      unit: celsius

    - entity_id: binary_sensor.front_door
      as: front_door_open

  # Actuators exposed to GLADyS
  actuators:
    - entity_id: climate.nest_thermostat
      as: thermostat
      trust_tier: comfort
      capabilities:
        - set_temperature
        - set_hvac_mode
      rate_limit:
        max_calls: 1
        period_seconds: 60

    - entity_id: lock.front_door
      as: front_door_lock
      trust_tier: security
      capabilities:
        - lock
        - unlock
      confirmation_required: true

    - entity_id: light.living_room
      as: living_room_lights
      trust_tier: comfort
      capabilities:
        - turn_on
        - turn_off
        - set_brightness
```

### 3.2 Actuator Trust Tiers

Different actuators have different risk profiles. Trust tiers determine audit routing, confirmation requirements, and permission levels.

| Trust Tier | Risk Profile | Audit Table | Confirmation | Examples |
|------------|--------------|-------------|--------------|----------|
| `comfort` | Low | `audit_actions` | Optional | Lights, thermostat, fans |
| `security` | High | `audit_security` (Merkle) | Required by default | Locks, garage doors, cameras |
| `safety` | Critical | `audit_security` (Merkle) | Always required | Fire suppression, gas shutoff |

Trust tier is declared per-actuator in the integration manifest, not per-device-type globally.

### 3.3 Command Model

#### 3.3.1 Command Structure

```protobuf
message ActuatorCommand {
  string actuator_id = 1;       // e.g., "thermostat", "front_door_lock"
  string action = 2;            // e.g., "set_temperature", "unlock"
  map<string, Value> params = 3; // Action-specific parameters
  string correlation_id = 4;    // Links to triggering event
  bool user_confirmed = 5;      // User explicitly confirmed this action
}

message ActuatorResponse {
  string correlation_id = 1;
  ActuatorOutcome outcome = 2;  // SUCCESS, FAILURE, PENDING, DENIED
  string message = 3;           // Human-readable status
  map<string, Value> state = 4; // New device state (if known)
}

enum ActuatorOutcome {
  SUCCESS = 0;
  FAILURE = 1;
  PENDING = 2;      // Command sent, outcome unknown (async)
  DENIED = 3;       // Validation failed or confirmation rejected
  RATE_LIMITED = 4; // Exceeded rate limit
}
```

#### 3.3.2 Command Validation

Commands pass through validation layers before execution:

1. **Capability check**: Is this action in the actuator's declared capabilities?
2. **Parameter validation**: Are parameters within declared bounds?
3. **Rate limit check**: Would this exceed the rate limit?
4. **Trust tier check**: Does user have permission for this trust tier?
5. **Confirmation check**: Does this action require confirmation? Was it provided?

#### 3.3.3 Rate Limiting

Prevents oscillation (thermostat toggling) and abuse:

```yaml
rate_limit:
  max_calls: 1
  period_seconds: 60
  burst_allowed: 3      # Optional: allow burst then throttle
  cooldown_seconds: 300 # Optional: extended cooldown after burst
```

Rate limits are per-actuator, enforced by the orchestrator. Executive can query remaining budget before deciding to actuate.

### 3.4 Safety Bounds

Actuators can declare safety bounds in their manifest:

```yaml
actuators:
  - entity_id: climate.nest_thermostat
    as: thermostat
    safety_bounds:
      temperature:
        min: 55   # Fahrenheit - prevent pipe freeze
        max: 85   # Prevent heat exhaustion
      hvac_mode:
        allowed: [heat, cool, auto, off]
        denied: []
```

Bounds are enforced at the orchestrator level - Executive cannot bypass them.

### 3.5 Confirmation UX

High-risk actions require user confirmation:

```
[GLADyS]: Someone's at the door. Should I unlock it?
[User]: Yes, let them in
[GLADyS]: Unlocking front door... done.
```

Confirmation requirements:

- `trust_tier: security` → confirmation required by default (user can override in settings)
- `trust_tier: safety` → confirmation always required (cannot be disabled)
- `confirmation_required: true` → explicit override regardless of tier

Confirmation timeout: 30 seconds default, configurable per-actuator.

### 3.6 Feedback Loop

Actuators report outcomes for closed-loop control:

1. **Synchronous**: Command → Response (within latency budget)
2. **Asynchronous**: Command → Pending → State change event (via sensor)

For async actuators, the integration plugin monitors state changes and emits events when the target state is reached (or timeout).

```yaml
actuators:
  - entity_id: lock.front_door
    feedback:
      mode: async
      state_entity: binary_sensor.front_door_locked
      timeout_seconds: 10
```

### 3.7 Executive Decision Model

The Executive decides when to actuate based on:

1. **Explicit request**: User says "turn on the lights"
2. **Learned pattern**: User always turns on lights at 6pm
3. **Reactive condition**: Temperature exceeds comfort threshold
4. **Proactive suggestion**: "It's getting warm, should I turn on the AC?"

Decision factors:

- User preferences (proactive vs. reactive)
- Confirmation requirements (ask first for security tier)
- Rate limit budget (don't attempt if rate-limited)
- Context (don't adjust thermostat during sleep mode)

### 3.8 Latency Requirements

| Action Type | Budget | Rationale |
|-------------|--------|-----------|
| User-requested | 2000ms | Includes confirmation dialog |
| Reactive (safety) | 500ms | Fast response to dangerous conditions |
| Proactive | 5000ms | No urgency, can batch |
| Confirmation timeout | 30000ms | User has time to respond |

These are separate from the 1000ms conversational budget in ADR-0005.

### 3.9 Dependency Modeling

Some actuators have dependencies (can't AC if window open):

```yaml
actuators:
  - entity_id: climate.nest_thermostat
    as: thermostat
    dependencies:
      - condition: window_sensor.closed
        required_for: [set_hvac_mode]
        message: "Close windows before turning on AC"
```

Dependencies are soft constraints - Executive is warned but can override with user confirmation.

### 3.10 Conflict Resolution

When multiple commands conflict (two routines trying to set different temperatures):

1. **Latest wins** (default): Most recent command takes precedence
2. **Safety wins**: Safety-tier commands override comfort-tier
3. **User wins**: Explicit user commands override automated commands
4. **Source priority**: Configurable priority by command source

Conflicts are logged to audit with both commands and resolution reason

---

## 4. Open Questions

*Resolved questions moved to Section 3.*

### Remaining

1. **Credential storage**: Where do integration tokens (HA long-lived tokens) go? Coordinate with ADR-0008.
2. **Entity discovery**: Auto-discover HA entities or require explicit mapping in manifest?
3. **State sync polling**: How often to poll HA for state changes if websocket fails?
4. **Offline handling**: HA unavailable - how does GLADyS degrade gracefully?
5. **Multi-integration conflicts**: Same device exposed through HA and Google - which wins?
6. **Gaming actuators**: How do game input actuators (Aperture) fit this model?
7. **Notification actuators**: Phone notifications, desktop alerts - same model or separate?

---

## 5. Consequences

### Positive

1. **Ecosystem leverage**: Home Assistant's 2000+ integrations become available to GLADyS
2. **Per-device trust**: Fine-grained security model where lock is `security` tier but light is `comfort`
3. **Oscillation prevention**: Rate limiting prevents thermostat toggling and similar issues
4. **Safety guarantees**: Bounds enforced at orchestrator level, Executive cannot bypass
5. **Auditability**: All commands logged with correlation to triggering events
6. **Graceful degradation**: Confirmation requirements give users control over autonomous behavior
7. **Future-proofing**: Generic Integration interface allows Google/Amazon to be added later

### Negative

1. **HA dependency**: Users without Home Assistant need to set it up (one-time cost)
2. **Manifest complexity**: Integration manifests are larger than simple sensors
3. **Latency overhead**: Validation layers add latency to command execution
4. **Configuration burden**: Per-actuator trust tiers, rate limits, etc. require thoughtful setup

### Risks

1. **HA API changes**: Home Assistant API evolves - need versioning strategy
2. **Security surface**: Integration plugins have broad access to external systems
3. **Confirmation fatigue**: Too many confirmations → users disable them → reduced safety
4. **State drift**: If GLADyS's view of device state drifts from reality, commands may fail or misbehave
5. **Feedback timeout**: Async actuators may never confirm success - need graceful handling

---

## 6. Related Decisions

- ADR-0003: Plugin Manifest Specification (sensor model to extend)
- ADR-0008: Security and Privacy (permission model)
- ADR-0010: Learning and Inference (learns from actuator outcomes)
- ADR-0012: Audit Logging (records all commands)
