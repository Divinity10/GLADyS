# Sensor Pipeline Consistency Review

**Date:** 2026-02-14
**Reviewer:** Gemini interactive CLI agent
**Scope:** Sensor protocol, command handling, heartbeat, registration
**Status:** COMPLETE

---

## Executive Summary

**Total findings:** 4 BLOCKER, 3 IMPORTANT, 2 MINOR

**Overall assessment:**
The sensor pipeline documentation is well-structured and reflects a clear architectural vision, but the implementation has significant gaps and contradictions. The most critical issues are the lack of command argument handling in the Orchestrator, the missing implementation of the `SendCommand` RPC, and the fact that both Java and JS SDKs completely ignore pending commands in the heartbeat response. Additionally, the Python SDK reference implementation (`AdapterBase`) described in the design documents is entirely missing from the codebase. These issues directly block the implementation and control of new sensors (e.g., RuneScape).

**Top BLOCKER findings:**
1. **Finding 1: Orchestrator Heartbeat ignores command arguments.**
2. **Finding 2: `SendCommand` is a TODO stub in Orchestrator.**
3. **Finding 3: Java/JS SDK HeartbeatManagers ignore pending commands.**
4. **Finding 4: Python SDK / `AdapterBase` is missing from the codebase.**

**Recommended fix order:**
1. Implement `SendCommand` and command queueing in Orchestrator (Finding 2).
2. Fix Orchestrator `Heartbeat` to correctly include `args` in `PendingCommand` (Finding 1).
3. Update Java and JS SDKs to handle `pending_commands` in `HeartbeatManager` (Finding 3).
4. Implement the Python `AdapterBase` and SDK (Finding 4).
5. Add special handling for `system.metrics` events in Orchestrator (Finding 5).

---

## Findings

### BLOCKER Findings

#### Finding 1: Orchestrator Heartbeat ignores command arguments

**Severity:** BLOCKER
**Domain:** Sensor Pipeline

**Contradiction:**
- **Doc claims:** `docs/codebase/SENSOR_CONTROL.md` shows `HeartbeatResponse` containing `pending_commands` which include `args` (google.protobuf.Struct).
- **Code reality:** `src/services/orchestrator/gladys_orchestrator/server.py:488` creates `PendingCommand` but ignores the arguments from the registry.
- **Impact:** Sensors receive lifecycle commands (e.g., START, STOP) but without parameters (e.g., `dry_run`, `force`), causing them to fail or behave incorrectly.

**Source of Truth:**
- [x] Doc is correct (Proto and design intent require arguments)

**Recommended Fix:**
Update `server.py:Heartbeat` to populate the `args` field:
```python
        pending_commands = [
            orchestrator_pb2.PendingCommand(
                command_id=p.get("command_id", ""),
                command=p.get("command", orchestrator_pb2.COMMAND_UNSPECIFIED),
                args=p.get("args", {}),  # Add this line
            )
            for p in pending_dicts
        ]
```

#### Finding 2: `SendCommand` is a TODO stub in Orchestrator

**Severity:** BLOCKER
**Domain:** Sensor Pipeline

**Contradiction:**
- **Doc claims:** `docs/codebase/SENSOR_CONTROL.md` and `docs/design/SENSOR_DASHBOARD.md` describe `SendCommand` as the primary mechanism for the Dashboard to control sensors.
- **Code reality:** `src/services/orchestrator/gladys_orchestrator/server.py:470` is a `TODO` stub that just logs the command and returns success.
- **Impact:** The Dashboard cannot actually control any sensors. Commands are never queued or delivered.

**Source of Truth:**
- [x] Doc is correct â†’ Implement `SendCommand` in Orchestrator and Registry.

**Recommended Fix:**
Implement command queueing in `ComponentRegistry` and call it from `OrchestratorServicer.SendCommand`.

#### Finding 3: Java/JS SDK HeartbeatManagers ignore pending commands

**Severity:** BLOCKER
**Domain:** Sensor Pipeline

**Contradiction:**
- **Doc claims:** `docs/codebase/SENSOR_CONTROL.md` and `docs/design/SENSOR_ARCHITECTURE.md` state that sensors receive and must execute lifecycle commands delivered via `HeartbeatResponse.pending_commands`.
- **Code reality:** `sdk/java/.../HeartbeatManager.java:70` and `sdk/js/.../HeartbeatManager.ts:50` call the heartbeat RPC but ignore the response.
- **Impact:** Even if the Orchestrator correctly sends commands, sensors using the provided SDKs will never see or execute them.

**Source of Truth:**
- [x] Doc is correct â†’ Update SDKs to process `pending_commands`.

**Recommended Fix:**
Update `HeartbeatManager` in both SDKs to accept a command handler callback and invoke it for each command in the heartbeat response.

#### Finding 4: Python SDK / `AdapterBase` is missing from the codebase

**Severity:** BLOCKER
**Domain:** Sensor Pipeline

**Contradiction:**
- **Doc claims:** `docs/design/SENSOR_ARCHITECTURE.md` section 3.3 and 3.4 describes a "Python SDK" and provides a full specification for an `AdapterBase` class as the reference implementation.
- **Code reality:** No `AdapterBase` class or Python SDK exists in `src/` or `sdk/`.
- **Impact:** Contradicts the claim that a reference implementation is provided for PoC 2. Python sensor developers have no foundation to build upon.

**Source of Truth:**
- [x] Doc is correct â†’ Code is missing.

**Recommended Fix:**
Implement the Python SDK and `AdapterBase` as specified in `SENSOR_ARCHITECTURE.md`.

---

### IMPORTANT Findings

#### Finding 5: `system.metrics` events are not specially handled by Orchestrator

**Severity:** IMPORTANT
**Domain:** Sensor Pipeline

**Contradiction:**
- **Doc claims:** `docs/design/SENSOR_ARCHITECTURE.md` section 1.3 states "`system.metrics` events routed to system handlers, not salience pipeline".
- **Code reality:** `src/services/orchestrator/gladys_orchestrator/router.py:route_event` does not differentiate by source and sends all events (including metrics) through salience scoring and memory.
- **Impact:** Performance degradation as metrics events are unnecessarily processed by the expensive salience/memory pipeline. Heuristics might erroneously match on metrics data.

**Source of Truth:**
- [x] Doc is correct â†’ Update `router.py` to intercept metrics events.

**Recommended Fix:**
In `router.py:route_event`, add a check for `event.source == "system.metrics"` and route to a dedicated metrics handler (as planned in `SENSOR_DASHBOARD.md`).

#### Finding 6: JS SDK sends deprecated/invalid `metrics` field in `HeartbeatRequest`

**Severity:** IMPORTANT
**Domain:** Sensor Pipeline

**Contradiction:**
- **Doc claims:** `docs/codebase/SENSOR_CONTROL.md` line 144 shows `HeartbeatRequest` without a `metrics` field.
- **Code reality:** `sdk/js/gladys-sensor-sdk/src/GladysClient.ts:110` sets `metrics: {},` in the `HeartbeatRequest`.
- **Proto reality:** `proto/orchestrator.proto` `HeartbeatRequest` does NOT have a `metrics` field.
- **Impact:** Inconsistency with Proto definition. May cause issues with some gRPC client implementations or confusion for developers.

**Source of Truth:**
- [x] Proto is correct â†’ Remove field from JS SDK.

**Recommended Fix:**
Remove line 110 from `sdk/js/gladys-sensor-sdk/src/GladysClient.ts`.

#### Finding 7: SDKs do not enforce gRPC timeouts from ADR-0005

**Severity:** IMPORTANT
**Domain:** Sensor Pipeline

**Contradiction:**
- **Doc claims:** `docs/adr/ADR-0005-gRPC-Service-Contracts.md` section 6 specifies timeouts: 100ms for Event publish and 5000ms for Heartbeat.
- **Code reality:** Neither Java nor JS SDKs set gRPC deadlines on these calls.
- **Impact:** Sensor threads may hang indefinitely if the orchestrator is unresponsive, violating the system's latency budget.

**Source of Truth:**
- [x] ADR-0005 is correct â†’ Update SDKs to set deadlines.

**Recommended Fix:**
Update `GladysClient` in both SDKs to use gRPC deadlines based on the ADR-0005 specifications.

---

### MINOR Findings

#### Finding 8: `Event.intent` type mismatch (Enum vs String)

**Severity:** MINOR
**Domain:** Sensor Pipeline

**Contradiction:**
- **Doc claims:** `docs/design/SENSOR_ARCHITECTURE.md` section 2.2 says `intent` is an `enum: actionable, informational, unknown`.
- **Code reality:** `proto/common.proto:44` defines `string intent = 11;`.
- **Impact:** Cosmetic inconsistency, though string allows more flexibility for future intents without proto changes.

**Source of Truth:**
- [x] Proto is correct â†’ Update documentation to reflect string type.

#### Finding 9: Conflicting documentation for `HeartbeatRequest` metrics

**Severity:** MINOR
**Domain:** Sensor Pipeline

**Contradiction:**
- **Doc inconsistency:** `docs/codebase/SENSOR_CONTROL.md` correctly shows no metrics in the proto definition (line 144) but includes `metrics=request.metrics` in the pseudo-code example (line 272).
- **Impact:** Confusing for developers implementing the heartbeat handler.

**Source of Truth:**
- [x] Proto is correct â†’ Update pseudo-code in `SENSOR_CONTROL.md`.

---

## Appendix: Documents Reviewed

- `docs/adr/ADR-0005-gRPC-Service-Contracts.md`
- `docs/codebase/SENSOR_CONTROL.md`
- `docs/design/SENSOR_ARCHITECTURE.md`
- `docs/design/SENSOR_DASHBOARD.md`
- `proto/common.proto`
- `proto/orchestrator.proto`

## Appendix: Code Reviewed

- `src/services/orchestrator/gladys_orchestrator/server.py`
- `src/services/orchestrator/gladys_orchestrator/registry.py`
- `src/services/orchestrator/gladys_orchestrator/router.py`
- `src/services/orchestrator/gladys_orchestrator/config.py`
- `sdk/java/gladys-sensor-sdk/src/main/java/com/gladys/sensor/GladysClient.java`
- `sdk/java/gladys-sensor-sdk/src/main/java/com/gladys/sensor/HeartbeatManager.java`
- `sdk/js/gladys-sensor-sdk/src/GladysClient.ts`
- `sdk/js/gladys-sensor-sdk/src/HeartbeatManager.ts`
