# Sensor Control Protocol

**Status**: Approved (2026-02-13)
**Related**: [SENSOR_ARCHITECTURE.md](../design/SENSOR_ARCHITECTURE.md), [SENSOR_DASHBOARD.md](../design/SENSOR_DASHBOARD.md)

## Overview

This document specifies:
1. How sensors communicate liveness and receive commands (Heartbeat RPC)
2. How sensors report detailed metrics (system.metrics events)
3. How the orchestrator sends lifecycle commands to sensors

**Architecture Decision**: Separate channels for liveness and metrics to solve the observability bootstrapping problem.

## Three Communication Channels

GLADyS sensors use three distinct channels:

### 1. Domain Events (High Volume, Continuous)

```
Sensor → Orchestrator: PublishEvent / PublishEvents

- Game state, emails, sensor-specific data
- Continuous stream, potentially 100+ events/second
- Subject to queueing, backpressure, flow control
```

### 2. Heartbeat (Low Volume, Critical)

```
Sensor → Orchestrator: Heartbeat RPC (every 30-60s)

- Minimal liveness signal (sensor_id, state)
- Command delivery via HeartbeatResponse.pending_commands
- Always responsive (not affected by event pipeline saturation)
```

### 3. System Metrics (Low Volume, Detailed)

```
Sensor → Orchestrator: PublishEvent(source="system.metrics")

- Detailed performance data (events/sec, queue depths, errors)
- Periodic (every 30-60s), flows through event pipeline
- Enables event subscription (metrics service can subscribe)
```

## Why Separate Heartbeat from Metrics?

**The observability bootstrapping problem:**

If metrics flow through the event pipeline, and the event pipeline becomes saturated, you lose observability of the system that provides observability.

**Failure scenario comparison:**

| Scenario | Metrics in Events | Separate Heartbeat |
|----------|-------------------|-------------------|
| **Pipeline saturated** | No metrics → can't diagnose | Heartbeat continues → see queue depth |
| **Sensor crashed** | No events → ambiguous | No heartbeat → clear signal |
| **Emergency shutdown** | Commands stuck in queue | Commands via heartbeat (immediate) |

**With separate heartbeat:**

- Dashboard shows "Sensors alive, queue=1000, 30s wait" (clear diagnosis)
- Can send emergency commands even when pipeline backed up
- Dead sensor detection is unambiguous (heartbeat missing = sensor dead)

**Pattern**: Kubernetes microservices - health probes separate from metrics collection.

---

## Architecture

```
┌──────────┐                    ┌──────────────┐                    ┌────────┐
│Dashboard │                    │ Orchestrator │                    │ Sensor │
└────┬─────┘                    └──────┬───────┘                    └───┬────┘
     │                                 │                                │
     │ SendCommand(sensor_id,          │                                │
     │   COMMAND_START, args)          │                                │
     ├────────────────────────────────►│                                │
     │                                 │  Queue command                 │
     │ CommandResponse(success=true)   │  (in-memory or DB)             │
     │◄────────────────────────────────┤                                │
     │                                 │                                │
     │                                 │         Heartbeat(state)
     │                                 │◄───────────────────────────────┤
     │                                 │                                │
     │                                 │  HeartbeatResponse(            │
     │                                 │    pending_commands=[          │
     │                                 │      {COMMAND_START, args}])   │
     │                                 ├───────────────────────────────►│
     │                                 │                                │
     │                                 │                   Execute start()
     │                                 │                   (async)      │
     │                                 │                                │
     │                                 │  Heartbeat(state=ACTIVE)       │
     │                                 │◄───────────────────────────────┤
     │                                 │                                │
     │                                 │  Mark command completed        │
     │                                 │                                │
```

---

## Proto Definitions

### Existing Infrastructure (orchestrator.proto)

```protobuf
service OrchestratorService {
    // Send command to component
    rpc SendCommand(CommandRequest) returns (CommandResponse);

    // Components send periodic heartbeats
    rpc Heartbeat(HeartbeatRequest) returns (HeartbeatResponse);
}

message CommandRequest {
    string target_component_id = 1;
    Command command = 2;
    google.protobuf.Struct args = 3;      // NEW: Command arguments
    RequestMetadata metadata = 15;
}

enum Command {
    COMMAND_UNSPECIFIED = 0;
    COMMAND_START = 1;
    COMMAND_STOP = 2;
    COMMAND_PAUSE = 3;
    COMMAND_RESUME = 4;
    COMMAND_RELOAD = 5;
    COMMAND_HEALTH_CHECK = 6;
    COMMAND_RECOVER = 7;                  // NEW: Trigger sensor recovery
}

message CommandResponse {
    bool success = 1;                     // True if command was queued
    string error_message = 2;             // Error if queueing failed
    ComponentStatus status = 3;           // Current component status
}

message HeartbeatRequest {
    string component_id = 1;
    ComponentState state = 2;
    RequestMetadata metadata = 15;
}

message HeartbeatResponse {
    bool acknowledged = 1;
    repeated PendingCommand pending_commands = 2;  // Commands to execute
}

message PendingCommand {
    string command_id = 1;                // UUID for tracking
    Command command = 2;
    google.protobuf.Struct args = 3;      // Command arguments
}
```

---

## Command Lifecycle

### 1. Dashboard Sends Command

```python
# Dashboard calls orchestrator
response = orchestrator_client.SendCommand(
    target_component_id="sensor-123",
    command=Command.COMMAND_START,
    args={"dry_run": True, "capture": True}
)

if response.success:
    # Command queued - sensor will get it on next heartbeat
    display_pending_state("Starting sensor...")
else:
    display_error(response.error_message)
```

### 2. Orchestrator Queues Command

```python
# Orchestrator implementation (pseudo-code)
def SendCommand(request):
    sensor = get_sensor(request.target_component_id)
    if not sensor:
        return CommandResponse(success=False, error_message="Sensor not found")

    # Queue command with TTL
    command_id = uuid4()
    queued_command = QueuedCommand(
        id=command_id,
        sensor_id=sensor.id,
        command=request.command,
        args=request.args,
        created_at=now(),
        expires_at=now() + timedelta(minutes=5)  # 5 minute TTL
    )

    command_queue.add(queued_command)

    return CommandResponse(
        success=True,
        status=sensor.current_status()
    )
```

### 3. Sensor Heartbeat Retrieves Command

```python
# Sensor sends heartbeat (every 30-60s)
response = orchestrator_client.Heartbeat(
    component_id=self.sensor_id,
    state=ComponentState.COMPONENT_STATE_ACTIVE
)

# Check for pending commands
for pending_cmd in response.pending_commands:
    await self.execute_command(pending_cmd)
```

### 4. Sensor Executes Command

```python
async def execute_command(self, pending_cmd: PendingCommand):
    """Execute command received in heartbeat response."""

    command_id = pending_cmd.command_id
    command = pending_cmd.command
    args = dict(pending_cmd.args)  # Struct → dict

    try:
        if command == Command.COMMAND_START:
            await self.start(**args)
            new_state = ComponentState.COMPONENT_STATE_ACTIVE

        elif command == Command.COMMAND_STOP:
            force = args.get("force", False)
            timeout_ms = args.get("timeout_ms", 5000)
            await self.stop(force=force, timeout_ms=timeout_ms)
            new_state = ComponentState.COMPONENT_STATE_STOPPED

        elif command == Command.COMMAND_RECOVER:
            strategy = args.get("strategy", "restart_drivers")
            success = await self.recover(strategy=strategy)
            new_state = ComponentState.COMPONENT_STATE_ACTIVE if success else ComponentState.COMPONENT_STATE_ERROR

        # Update local state
        self.current_state = new_state

        # Ack command (orchestrator sees new state in next heartbeat)
        logger.info(f"Command {command_id} executed successfully: {command} → {new_state}")

    except Exception as e:
        logger.error(f"Command {command_id} failed: {e}")
        self.current_state = ComponentState.COMPONENT_STATE_ERROR
```

### 5. Orchestrator Marks Command Complete

```python
# Orchestrator implementation (pseudo-code)
def Heartbeat(request):
    sensor = get_sensor(request.component_id)

    # Update sensor state
    sensor.update_status(
        state=request.state,
        metrics=request.metrics,
        last_heartbeat=now()
    )

    # Check for completed commands (state changed as expected)
    completed = []
    for cmd in command_queue.get_for_sensor(sensor.id):
        if state_matches_command(request.state, cmd.command):
            completed.append(cmd.id)

    command_queue.mark_completed(completed)

    # Get pending commands
    pending = command_queue.get_pending(sensor.id)

    return HeartbeatResponse(
        acknowledged=True,
        pending_commands=pending
    )
```

---

## Command Arguments Convention

### COMMAND_START

```json
{
  "dry_run": false,           // Don't publish events, just test pipeline
  "capture": false,           // Enable JSONL capture on startup
  "config_override": {}       // Override sensor config (JSONB)
}
```

### COMMAND_STOP

```json
{
  "force": false,             // Skip graceful shutdown, stop immediately
  "timeout_ms": 5000,         // Max time for graceful shutdown
  "flush_buffers": true       // Flush queued events before stopping
}
```

### COMMAND_RECOVER

```json
{
  "strategy": "restart_drivers"  // "restart_drivers" | "clear_buffers" | "full_reset"
}
```

### COMMAND_HEALTH_CHECK

```json
{
  "check_drivers": true,      // Ping all drivers
  "check_queues": true,       // Verify queue depths reasonable
  "detailed": false           // Return detailed health report
}
```

---

## Error Handling

### Command TTL

Commands expire after **5 minutes** (configurable). If sensor doesn't heartbeat within this window, command is dropped.

**Rationale**: Sensors may be offline, restarting, or dead. Don't queue commands indefinitely.

### Ack Timeout

If sensor state doesn't change within **3 heartbeats** after command delivery, mark command as failed.

**Example**: Sent COMMAND_START, sensor still shows STOPPED after 3 heartbeats → command failed.

### Idempotency

Commands must be idempotent:

- `COMMAND_START` on already-started sensor → no-op, not error
- `COMMAND_STOP` on already-stopped sensor → no-op, not error
- `COMMAND_RECOVER` can be called multiple times

**Why**: Network delays, retries, or manual re-sends shouldn't break the system.

### Command Ordering

Commands for a single sensor are delivered in **FIFO order**.

**Example**: Dashboard sends STOP then START → sensor receives STOP first, then START.

**Exception**: `COMMAND_HEALTH_CHECK` can be delivered out-of-order (doesn't change state).

---

## Dashboard Integration

### UI Patterns

**Pending state (command queued, waiting for heartbeat):**

```html
<button disabled>
  <span class="spinner"></span> Starting sensor...
</button>
<p class="text-muted">Waiting for sensor heartbeat (up to 60s)</p>
```

**Timeout after 2 minutes:**

```html
<div class="alert alert-warning">
  Command timed out - sensor didn't respond within 2 minutes.
  <button onclick="retry()">Retry</button>
</div>
```

**Success (state changed):**

```html
<button onclick="deactivate()">Deactivate</button>
<span class="badge badge-success">● Active</span>
```

### Dashboard API Calls

```python
# Activate sensor
response = orchestrator.SendCommand(
    target_component_id=sensor_id,
    command=Command.COMMAND_START
)

# Deactivate sensor
response = orchestrator.SendCommand(
    target_component_id=sensor_id,
    command=Command.COMMAND_STOP,
    args={"flush_buffers": True}
)

# Trigger recovery
response = orchestrator.SendCommand(
    target_component_id=sensor_id,
    command=Command.COMMAND_RECOVER,
    args={"strategy": "restart_drivers"}
)

# Force shutdown (emergency)
response = orchestrator.SendCommand(
    target_component_id=sensor_id,
    command=Command.COMMAND_STOP,
    args={"force": True, "timeout_ms": 1000}
)
```

---

## Sensor SDK Integration

### Python SDK Example

```python
from gladys.sensors import AdapterBase

class MySensorAdapter(AdapterBase):
    """Example sensor using pull-based command delivery."""

    async def run(self):
        """Main sensor loop."""
        while self.running:
            # Send heartbeat, check for commands
            response = await self.orchestrator_client.Heartbeat(
                component_id=self.sensor_id,
                state=self.current_state
            )

            # Execute any pending commands
            for cmd in response.pending_commands:
                await self.execute_command(cmd)

            # Wait for next heartbeat interval
            await asyncio.sleep(self.heartbeat_interval_s)

    async def execute_command(self, cmd: PendingCommand):
        """Execute command from orchestrator."""
        if cmd.command == Command.COMMAND_START:
            await self.start(**dict(cmd.args))
        elif cmd.command == Command.COMMAND_STOP:
            await self.stop(**dict(cmd.args))
        elif cmd.command == Command.COMMAND_RECOVER:
            await self.recover(**dict(cmd.args))
        # ... handle other commands
```

---

## Future Optimizations

### Urgent Command Fast Path (PoC 3+)

If sub-second latency becomes needed:

1. Add `urgent` flag to `SendCommand`
2. Orchestrator sends push notification to sensor (requires bidirectional channel)
3. Sensor sends immediate heartbeat to retrieve urgent command
4. Falls back to pull-based if push fails

**Not needed for PoC 2** - manual dashboard operations tolerate 30-60s latency.

### Push-Based Alternative (Remote Sensors)

For sensors that expose gRPC endpoints:

1. Sensor registers `control_endpoint` during `RegisterComponent`
2. Orchestrator calls sensor's `SensorControl.ExecuteCommand()` RPC directly
3. Falls back to pull-based if push fails

**Deferred until remote sensors are a requirement.**

---

## Testing

### Unit Tests

- Command queueing (add, retrieve, expire)
- TTL expiration (commands dropped after 5 min)
- Idempotency (multiple START commands = one effect)
- Argument parsing (Struct → dict conversion)

### Integration Tests

- Dashboard sends command → sensor executes within 2 heartbeats
- Command timeout → sensor doesn't heartbeat → command expires
- Sensor offline → command queued → sensor comes back → command delivered
- Multiple commands → delivered in FIFO order

### Manual Tests

- Click "Activate" in dashboard → sensor starts within 60s
- Click "Deactivate" → sensor stops and flushes events
- Click "Recover" → sensor restarts drivers and recovers
- Sensor crash → orchestrator detects (no heartbeat) → shows disconnected

---

## References

- [orchestrator.proto](../../proto/orchestrator.proto) - SendCommand, Heartbeat RPCs
- [SENSOR_ARCHITECTURE.md](../design/SENSOR_ARCHITECTURE.md) - Sensor protocol interface
- [SENSOR_DASHBOARD.md](../design/SENSOR_DASHBOARD.md) - Dashboard sensor management UI
- Kubernetes: Pod lifecycle via kubelet polling
- AWS Systems Manager: EC2 Run Command with agent polling
- HashiCorp Nomad: Client allocation via server polling
