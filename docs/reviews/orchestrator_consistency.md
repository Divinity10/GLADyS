# Orchestrator Core Consistency Review

**Date:** 2026-02-14
**Reviewer:** Gemini Deep Reasoning
**Scope:** Service topology, RPC contracts, event routing, concurrency model
**Status:** COMPLETE

---

## Executive Summary

**Total findings:** 0 BLOCKER, 5 IMPORTANT, 3 MINOR

**Overall assessment:**
The Orchestrator Core implementation is functional and mostly aligns with the recent "§30 boundary change" (shifting decision logic to the Executive). However, there is significant documentation drift regarding the physical file structure of protos, the observability stack, and the internal concurrency state. Several "HIGH" severity issues listed in `CONCURRENCY.md` have been fixed in the code but remain in the documentation, which could mislead new developers. The "Moment Accumulator" concept has been largely replaced by a "Priority Event Queue," but several design documents still refer to moment windows and accumulation intervals.

**Top IMPORTANT findings:**
1. **Missing `salience.proto`**: `ADR-0005` specifies separate proto files, but `SalienceGateway` is merged into `memory.proto`.
2. **Stale Concurrency Issues**: `CONCURRENCY.md` lists fixed race conditions as high-priority bugs.
3. **Fallback Salience Discrepancy**: `router.py` does not use the configured `fallback_novelty` and has hardcoded defaults that contradict `ROUTER_CONFIG.md`.
4. **Proposed vs Actual Observability**: `ADR-0006` describes a Prometheus/Loki stack that does not exist in the current implementation.
5. **Moment Accumulator Staleness**: Design docs describe "Moment windows" while code implements a standard Priority Queue.

**Recommended fix order:**
1. Update `CONCURRENCY.md` to reflect that fire-and-forget and `OutcomeWatcher` race conditions are fixed.
2. Align `router.py` with `ROUTER_CONFIG.md` by using the `fallback_novelty` configuration.
3. Update `ADR-0005` and `INTERFACES.md` to reflect the actual proto file structure.
4. Update `SUBSYSTEM_OVERVIEW.md` to clarify the transition from Moments to Priority Queuing.

---

## Findings

### IMPORTANT Findings

#### Finding 1: Physical Proto File Discrepancy (Salience)

**Severity:** IMPORTANT
**Domain:** RPC Contracts

**Contradiction:**
- **Doc claims:** `ADR-0005` Section 4.1 specifies `salience.proto` as a separate file. `INTERFACES.md` also refers to `proto/orchestrator.proto` for event routing but implies separate service files.
- **Code reality:** `proto/salience.proto` does not exist. The `SalienceGateway` service is defined within `proto/memory.proto`.
- **Impact:** Developers looking for salience contracts will be confused or think the service is missing. Code generation scripts (like `buf.gen.yaml`) might be misconfigured if they expect separate files.

**Source of Truth:**
- [x] Code is correct → Update `ADR-0005` and `INTERFACES.md` to reflect merged `memory.proto`.

**Recommended Fix:**
Update `ADR-0005` Section 4.1 and `INTERFACES.md` to note that `SalienceGateway` and `MemoryStorage` share `proto/memory.proto` due to their co-location in the same process.

#### Finding 2: Stale Concurrency Issues in Documentation

**Severity:** IMPORTANT
**Domain:** Concurrency Model

**Contradiction:**
- **Doc claims:** `docs/codebase/CONCURRENCY.md` lists two "HIGH" severity issues: (1) Fire-and-forget tasks in `router.py:115` without error handling, and (2) Race condition in `outcome_watcher.py` `_pending` list.
- **Code reality:** `router.py` (line 147, 276) now uses `_handle_task_exception` callback. `outcome_watcher.py` (line 117, 133, etc.) uses an `asyncio.Lock` for all access to `self._pending`.
- **Impact:** Misleads developers into thinking the system is unstable or has known high-priority bugs that are already resolved.

**Source of Truth:**
- [x] Code is correct → Update `docs/codebase/CONCURRENCY.md` to remove these from "Known Issues" and document the fixes as patterns.

**Recommended Fix:**
Remove the stale entries from the "Known Concurrency Issues" table in `docs/codebase/CONCURRENCY.md`. Add a note about using `_handle_task_exception` as a best practice for background tasks.

#### Finding 3: Fallback Salience Inconsistency

**Severity:** IMPORTANT
**Domain:** Event Routing

**Contradiction:**
- **Doc claims:** `docs/design/ROUTER_CONFIG.md` specifies that `_default_salience()` should use `self._config.fallback_novelty` (default 0.8) and set other fields to 0.0.
- **Code reality:** `src/services/orchestrator/gladys_orchestrator/router.py:319` (in `_default_salience`) has hardcoded 0.5 for all dimensions and does not reference `self.config.fallback_novelty`.
- **Impact:** Graceful degradation behavior is inconsistent with the design. High-salience events might not be routed correctly when the salience service is down because 0.5 is below the `high_salience_threshold` of 0.7.

**Source of Truth:**
- [x] Doc is correct → Update `router.py` to use config values.

**Recommended Fix:**
In `router.py`, update `_default_salience` to use `self.config.fallback_novelty` for the novelty dimension and 0.0 (or as specified) for others to ensure it triggers the high-salience threshold if intended.

#### Finding 4: Proposed vs Actual Observability Stack

**Severity:** IMPORTANT
**Domain:** Observability

**Contradiction:**
- **Doc claims:** `ADR-0006` (Proposed) specifies Prometheus, Loki, Jaeger, and Grafana. `ADR-0005` Section 9 also mentions OpenTelemetry integration and Jaeger.
- **Code reality:** The implementation uses `structlog` (Python) and `tracing` (Rust). There is no Prometheus, Loki, or Jaeger in `docker-compose.yml`. Monitoring is handled via the custom Dashboard service.
- **Impact:** New contributors might try to set up or find these external services which are not currently part of the stack.

**Source of Truth:**
- [ ] Doc is correct → Implement stack
- [x] Code is correct → Update `ADR-0006` to clarify it is a future roadmap and document current `structlog` + Dashboard status.

**Recommended Fix:**
Update the status of `ADR-0006` to clearly state it is a future roadmap for Phase 3+. Add a section to `docs/codebase/LOGGING.md` explaining that the Dashboard is the primary observability tool for the current phase.

#### Finding 5: Moment Accumulator vs Priority Queue

**Severity:** IMPORTANT
**Domain:** Event Routing

**Contradiction:**
- **Doc claims:** `ADR-0001` and `SUBSYSTEM_OVERVIEW.md` describe "Moments" and "Moment windows" (50-100ms) for accumulating events before processing.
- **Code reality:** `src/services/orchestrator/gladys_orchestrator/event_queue.py` implements a standard Priority Queue where events are processed individually as fast as possible by a background worker, ordered by salience. The docstring explicitly says "Replaces MomentAccumulator for Phase."
- **Impact:** Confusion over the temporal model of the system. "Moments" imply batching/synchronization that isn't happening in the current `EventQueue` implementation.

**Source of Truth:**
- [x] Code is correct → Update `SUBSYSTEM_OVERVIEW.md` and `ADR-0001` to reflect the priority queue model.

**Recommended Fix:**
Update `SUBSYSTEM_OVERVIEW.md` Section 3 to clarify that "Moments" are currently implemented as prioritized individual events in a queue, and that temporal correlation is deferred to Memory queries.

### MINOR Findings

#### Finding 6: Heuristic Proto Gap (`frozen` status)

**Severity:** MINOR
**Domain:** Domain Conventions

**Contradiction:**
- **Doc claims:** `docs/codebase/DOMAIN_CONVENTIONS.md` correctly identifies that `frozen` status exists in the DB but is **NOT IN PROTO**.
- **Code reality:** `proto/memory.proto` `message Heuristic` indeed lacks a `frozen` or `active` boolean field.
- **Impact:** Dashboard and other clients cannot filter heuristics by active/inactive status via gRPC.

**Source of Truth:**
- [x] Doc is correct (identifies gap) → Update Proto to include the field.

**Recommended Fix:**
Add `bool active = 19;` (or similar) to the `Heuristic` message in `proto/memory.proto`.

#### Finding 7: Executive Language Inconsistency

**Severity:** MINOR
**Domain:** Service Topology

**Contradiction:**
- **Doc claims:** `ADR-0001` specifies C# for the Executive. `docker-compose.yml` calls the current service "executive-stub (Python)" and says the "real" one will be C#.
- **Code reality:** `src/services/executive/gladys_executive/server.py` is a fairly complete Python implementation of the decision logic, including LLM integration and bootstrapping. `SERVICE_TOPOLOGY.md` notes that reality (Python) differs from the ADR.
- **Impact:** Ambiguity about the long-term technology choice for the Executive.

**Source of Truth:**
- [ ] ADR is correct → Rewrite in C#
- [x] Reality is correct → Update ADR-0001 or accept the Python implementation as more than a "stub".

**Recommended Fix:**
Update `ADR-0001` or add an addendum noting that the Executive implementation has shifted to Python (or clarify if the C# move is still planned).

#### Finding 8: Type Naming Inconsistency (`SalienceVector` vs `SalienceResult`)

**Severity:** MINOR
**Domain:** RPC Contracts

**Contradiction:**
- **Doc claims:** `INTERFACES.md` and `ADR-0005` use the name `SalienceVector`.
- **Code reality:** `proto/types.proto` and `common.proto` use the name `SalienceResult`. The `SalienceResult` contains a `map<string, float> vector`.
- **Impact:** Minor confusion when searching for types in the codebase.

**Source of Truth:**
- [x] Proto is correct → Update `INTERFACES.md` and `ADR-0005`.

**Recommended Fix:**
Replace occurrences of `SalienceVector` with `SalienceResult` in `INTERFACES.md` and `ADR-0005`.

---

## Appendix: Documents Reviewed

- `docs/adr/ADR-0001-GLADyS-Architecture.md`
- `docs/adr/ADR-0005-gRPC-Service-Contracts.md`
- `docs/adr/ADR-0006-Observability-and-Monitoring.md`
- `docs/design/ARCHITECTURE.md`
- `docs/design/SUBSYSTEM_OVERVIEW.md`
- `docs/design/INTERFACES.md`
- `docs/design/ROUTER_CONFIG.md`
- `docs/design/LOGGING_STANDARD.md`
- `docs/codebase/SERVICE_TOPOLOGY.md`
- `docs/codebase/CONCURRENCY.md`
- `docs/codebase/DOMAIN_CONVENTIONS.md`
- `docs/codebase/LOGGING.md`
- `docs/codebase/DOCKER.md`

## Appendix: Code Reviewed

- `src/services/orchestrator/gladys_orchestrator/server.py`
- `src/services/orchestrator/gladys_orchestrator/router.py`
- `src/services/orchestrator/gladys_orchestrator/registry.py`
- `src/services/orchestrator/gladys_orchestrator/event_queue.py`
- `src/services/orchestrator/gladys_orchestrator/outcome_watcher.py`
- `src/services/orchestrator/gladys_orchestrator/config.py`
- `src/services/executive/gladys_executive/server.py`
- `proto/orchestrator.proto`
- `proto/memory.proto`
- `proto/common.proto`
- `proto/types.proto`
- `docker/docker-compose.yml`
