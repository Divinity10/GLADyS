# Learning Loop Work Log

**Purpose**: Coordination file for Claude and Gemini working in parallel on the Learning Loop closure.

**Reference**: See [LEARNING_CLOSURE_PLAN.md](LEARNING_CLOSURE_PLAN.md) for the full plan.

---

## Active Work

| Phase | Owner | Environment | Status | Last Update |
|-------|-------|-------------|--------|-------------|
| 0 - Fix Explicit Feedback | Claude | Local | ✅ Complete | 2026-01-26 |
| 1 - Generalization Test | Gemini | Docker | ✅ Complete | 2026-01-26 |
| 2 - Implicit Feedback | Claude | Local | 🟢 Unblocked | 2026-01-26 |
| 3 - Feedback Persistence | Claude | Docker | ✅ Complete | 2026-01-26 |

---

## Environment Sync Status

**Last Verified**: 2026-01-26 by Gemini

- [x] Proto files are in sync
- [x] Migrations exist in `src/memory/migrations/` (001-009)
- [x] Docker services running and healthy
- [x] Semantic matching verified via integration test

**Check status**: `python scripts/docker.py status` (Docker) or `python scripts/local.py status` (Local)

---

## Log Entries

### 2026-01-26 - Integration Gaps Fixed: GetHeuristic RPC and feedback_source

**Author**: Claude

**What was done**:

1. **Added `GetHeuristic` RPC** - Needed by OutcomeWatcher to fetch heuristic details
   - Added `GetHeuristicRequest` and `GetHeuristicResponse` to `memory.proto`
   - Implemented handler in `grpc_server.py`
   - Added `get_heuristic` method in `storage.py`

2. **Added `feedback_source` to `UpdateHeuristicConfidenceRequest`**
   - Proto field 5: `string feedback_source` - 'explicit' (user) or 'implicit' (outcome watcher)
   - Updated `storage.py` to accept and pass through the parameter
   - Updated `grpc_server.py` handler to read from request

3. **Synced protos and regenerated stubs**

**Files changed**:
- `src/memory/proto/memory.proto` - Added GetHeuristic RPC, feedback_source field
- `src/orchestrator/proto/memory.proto` - Synced
- `src/memory/python/gladys_memory/grpc_server.py` - GetHeuristic handler, feedback_source passthrough
- `src/memory/python/gladys_memory/storage.py` - get_heuristic method, feedback_source parameter
- All generated `*_pb2.py` and `*_pb2_grpc.py` files regenerated

**Test result**: Flight Recorder test still passes with all integration gaps fixed.

---

### 2026-01-26 - Phase 3 Complete: Flight Recorder Test Passing

**Author**: Claude

**What was done** (multiple bugs fixed):

1. **Fixed test event IDs** - Test was creating `evt-{uuid.hex[:8]}` which isn't a valid UUID. Memory service expects UUIDs.
   - Changed to `event_id = str(uuid.uuid4())`

2. **Fixed storage.py `get_pending_fires`** - SQL query was missing `outcome` and `feedback_source` columns but gRPC handler tried to access them.
   - Added columns to SELECT statement

3. **Fixed test subprocess path** - Test runs from `src/integration/` but called `scripts/docker.py` which doesn't exist relative to that directory.
   - Changed to absolute path: `str(PROJECT_ROOT / "scripts" / "docker.py")`

**Files changed**:
- `src/integration/test_flight_recorder.py` - UUID fix, subprocess path fix
- `src/memory/python/gladys_memory/storage.py` - SQL column fix

**Test result**:
```
SUCCESS: Flight Recorder works!
- Heuristic stored ✓
- Fire recorded on match ✓
- Outcome updated on feedback ✓
- Verified: outcome='success', feedback_source='explicit' ✓
```

**Phase 3 is now complete.** Remaining work: Phase 2 (implicit feedback) integration.

---

### 2026-01-26 - Proto Duplication Fixed, Handing Back to Gemini

**Author**: Claude

**What was done** (root cause fix for SalienceVector class mismatch):

1. **Created `types.proto`** - Single source of truth for cross-service types
   - `src/memory/proto/types.proto` contains `SalienceVector` definition
   - Documented the principle: "If type is CREATED by service A and CONSUMED by service B, it belongs here"

2. **Updated all proto files to import from types.proto**:
   - `memory.proto`: `import "types.proto"; ... gladys.types.SalienceVector salience = 6;`
   - `common.proto`: Same pattern

3. **Updated Python code**:
   - `grpc_server.py`, `router.py`, `memory_client.py`, `test_grpc.py` - import `types_pb2`
   - `memory_client.py` now uses `CopyFrom` correctly (no more class mismatch)

4. **Updated Rust build**:
   - `build.rs` compiles both `types.proto` and `memory.proto`
   - `lib.rs` restructured proto module with nested `gladys::types` and `gladys::memory` modules

5. **Updated proto_sync.py**:
   - Added `types.proto` to both memory and orchestrator configs
   - Added to consistency check

6. **Added model_config to orchestrator config.py** (pydantic-settings v2 fix)

**Files changed**:
- `src/memory/proto/types.proto` - NEW
- `src/memory/proto/memory.proto` - imports types.proto
- `src/orchestrator/proto/common.proto` - imports types.proto
- `src/orchestrator/proto/types.proto` - synced copy
- `src/memory/python/gladys_memory/grpc_server.py` - uses types_pb2.SalienceVector
- `src/orchestrator/gladys_orchestrator/router.py` - uses types_pb2.SalienceVector
- `src/orchestrator/gladys_orchestrator/clients/memory_client.py` - CopyFrom now works
- `src/memory/rust/build.rs` - compiles both protos
- `src/memory/rust/src/lib.rs` - restructured proto module
- `scripts/proto_sync.py` - syncs types.proto
- `src/orchestrator/gladys_orchestrator/config.py` - added model_config

**Status**: Proto fixes complete, ready for Docker rebuild and testing.

**[For Gemini]**: The SalienceVector class mismatch error should be fixed. Docker needs rebuild. The test may still fail at "No fire record found" - I traced the code and the flow looks correct:
1. Rust `evaluate_salience` returns `matched_heuristic_id` ✓
2. Salience client extracts as `_matched_heuristic` ✓
3. Router calls `record_heuristic_fire` when heuristic matches ✓

If fire recording still fails, check:
- Is `_salience_client` connected in orchestrator?
- Is `_memory_client` connected when fire recording is attempted?
- Debug logs added to router.py lines 113, 123

---

### 2026-01-26 - Phase 3: Claude Taking Over (Handoff from Gemini)

**Author**: Claude

**Context**: Gemini hit capacity limits (Gemini 3.0 Pro under high demand). Claude taking over to complete Phase 3.

**Gemini's completed work** (good quality):
- Migration `009_heuristic_fires.sql` ✅
- Proto messages for fire tracking ✅
- Storage methods (`record_heuristic_fire`, `update_fire_outcome`, `get_pending_fires`) ✅
- Feedback linkage in `update_heuristic_confidence` ✅

**Remaining work**:
- Add gRPC handlers in `grpc_server.py`
- Wire Orchestrator router to call `RecordHeuristicFire` on cache hits
- Fix hardcoded `feedback_source='explicit'` to support 'implicit'

**Next steps**:
- Completing gRPC handlers now

---

### 2026-01-26 - Phase 3: Migration 009 Created

**Author**: Gemini

**What was done**:
- Created `src/memory/migrations/009_heuristic_fires.sql`.
- Applied migration to Docker environment.
- This creates the `heuristic_fires` table ("Flight Recorder") for tracking heuristic performance.

**Next steps**:
- Implement storage methods in `storage.py`.
- Add gRPC messages to `memory.proto`.

---

### 2026-01-26 - Phase 1 Complete: Generalization Test Verified

**Author**: Gemini

**What was done**:
- Created `src/integration/test_generalization.py`.
- Verified that GLADyS can generalize from "killing" to "murdering" (semantic match) while lexically sharing no major words.
- Verified that unrelated events do not trigger the heuristic (control test).

**Findings**:
- **Prefix Over-influence**: Discovered that domain prefixes (e.g., `social: ...`) can artificially inflate similarity scores for short phrases in the `all-MiniLM-L6-v2` model. This causes unrelated events in the same domain to incorrectly match heuristics at the default 0.7 threshold.
- **Recommendation**: For robust domain separation, we may need to increase the similarity threshold or use a more discriminative embedding strategy when prefixes are involved.

**Questions/Blockers**:
- None.

**Next steps**:
- Starting Phase 3 (Feedback Persistence).

---

### 2026-01-26 - Starting Phase 1: Generalization Test

**Author**: Claude

**What was built**:
The OutcomeWatcher - a system that observes the event stream for "consequences" of heuristic-triggered actions and automatically sends implicit feedback.

**How it works**:
1. When a heuristic fires (fast path cache hit), the OutcomeWatcher registers an "expectation"
2. Expectations are configured via patterns: trigger_pattern (matches heuristic condition_text) → outcome_pattern (matches subsequent event raw_text)
3. When an incoming event matches a pending expectation, implicit positive feedback is triggered
4. Feedback uses the existing TD learning API (UpdateHeuristicConfidence)

**Files created/modified**:
- `src/orchestrator/gladys_orchestrator/outcome_watcher.py` - NEW: OutcomeWatcher class
- `src/orchestrator/gladys_orchestrator/config.py` - Added outcome watcher config (enabled, cleanup_interval, patterns_json)
- `src/orchestrator/gladys_orchestrator/router.py` - Integrated outcome checking and fire registration
- `src/orchestrator/gladys_orchestrator/server.py` - Wires up OutcomeWatcher with cleanup loop
- `src/orchestrator/gladys_orchestrator/clients/memory_client.py` - Added update_heuristic_confidence() and get_heuristic()
- `src/integration/test_implicit_feedback.py` - NEW: Integration test

**Test results**:
```
[Step 1] Storing test heuristic...
Initial confidence: 0.600
[Step 2] Creating OutcomeWatcher with outcome pattern...
[Step 3] Registering heuristic fire...
[Step 4] Sending outcome event...
OutcomeWatcher: Outcome detected, sending positive implicit feedback
Confidence updated [implicit]: 0.60 → 0.63 (delta=0.030, td_error=0.300)
[Step 5] Verifying confidence update...
Final confidence: 0.630
PASS: Implicit feedback increased confidence!
```

**Configuration example**:
```json
{
  "outcome_patterns_json": "[{\"trigger_pattern\": \"oven\", \"outcome_pattern\": \"oven turned off\", \"timeout_sec\": 120}]"
}
```

**Design decisions made**:
1. Outcome patterns live in orchestrator config (JSON array) - simple, explicit, no schema changes
2. Timeout defaults to 120 seconds; expired expectations are cleaned up periodically
3. Success outcomes increase confidence; failure outcomes could decrease (configurable via is_success flag)

**Questions/Blockers**: None.

---

### 2026-01-26 - Starting Phase 2: Implicit Feedback (Outcome Evaluator)

**Author**: Claude

**What I'm doing**:
- Implementing the "Outcome Evaluator" - watches event stream for consequences of actions
- When a heuristic fires and the expected outcome event arrives, automatically trigger positive feedback

**Design decisions to make**:
1. Where does outcome mapping live? (Config file vs DB vs heuristic metadata)
2. How long to wait before marking outcome "unknown"?
3. Should failed outcomes decrease confidence or just not increase it?

**Approach**:
- Start simple: hardcoded outcome mappings in config for PoC
- Implement as background task in Orchestrator that watches for outcome events
- Call existing `UpdateHeuristicConfidence` API when outcome detected

**Files I'll likely modify**:
- `src/orchestrator/gladys_orchestrator/router.py` or new `outcome_watcher.py`
- `src/orchestrator/gladys_orchestrator/config.py` (outcome mappings)
- New test file for implicit feedback

**Questions/Blockers**:
- None currently. Starting with design exploration.

---

### 2026-01-26 - Starting Phase 1: Generalization Test

**Author**: Gemini

**What was done**:
- Initialized Phase 1 task.
- Reviewed requirements and reference `test_killer_feature.py`.

**Questions/Blockers**:
- None.

**Next steps**:
- Create `src/integration/test_generalization.py`.
- Verify semantic matching across lexical gaps (e.g., "house burning" ↔ "smoke alarms").

---

### 2026-01-26 - Phase 0 Complete: Explicit Feedback Fixed

**Author**: Claude

**Root Cause**: Test failures were NOT cache invalidation as initially suspected. The actual problems:

1. **Missing database migrations** - Migrations 004 and 008 were not applied to local PostgreSQL:
   - `last_accessed` column missing (migration 004)
   - `condition_embedding` column missing (migration 008)

2. **Hardcoded magic number** - `min_similarity=0.7` was hardcoded in storage.py instead of being configurable

**Fixes Applied**:

1. Applied all migrations to local database
2. Added `heuristic_min_similarity` config setting to `SalienceSettings` in [config.py](../../src/memory/python/gladys_memory/config.py)
3. Updated `storage.py` and `grpc_server.py` to use config value
4. Fixed test cleanup to use correct script paths (`scripts/local.py` or `scripts/docker.py`)
5. **Root cause prevention**: Added auto-migration to `scripts/local.py start` (matching docker.py behavior)
   - Use `--no-migrate` flag only if you intentionally need schema divergence

**Files Changed** (affects Docker environment):
- `src/memory/python/gladys_memory/config.py` - new `heuristic_min_similarity` setting
- `src/memory/python/gladys_memory/storage.py` - uses config instead of hardcoded 0.7
- `src/memory/python/gladys_memory/grpc_server.py` - uses config instead of hardcoded 0.7
- `scripts/local.py` - added `migrate` command, auto-migration on `start`
- `CLAUDE.md` - added Database Schema Management section

**Verification**: Test passes 5/5 runs reliably.

**Next**: Phases 2 and 3 are now unblocked. Phase 1 (Gemini) can continue independently.

---

### 2026-01-25 - Environment Verification Complete

**Author**: Claude

Verified environment sync:
- Proto files are identical between memory and orchestrator
- 8 migrations exist (001-008)
- Docker services all running and healthy (`python scripts/docker.py status`)

Gemini prompt created: [../prompts/GEMINI_PHASE1_GENERALIZATION.md](../prompts/GEMINI_PHASE1_GENERALIZATION.md)

**Next**: Claude starting Phase 0 diagnosis, Gemini can start Phase 1 in parallel.

---

### 2026-01-25 - Plan Created

**Author**: Claude

Created parallel execution plan:
- Phase 0 (Claude/Local) and Phase 1 (Gemini/Docker) can run in parallel
- Phases 2 and 3 blocked until Phase 0 completes
- Coordination via this file

**Next Actions**:
- Claude: Start Phase 0 diagnosis
- Gemini: Start Phase 1 test creation

---

## Communication Protocol

When updating this file:

1. **Add new entries at the top** (most recent first)
2. **Include**:
   - Date and author (Claude or Gemini)
   - What you did
   - Any blockers or questions for the other party
   - Files changed that might affect the other environment
3. **Update the Active Work table** when status changes
4. **Flag cross-environment changes**: If you change shared code (proto files, migrations, etc.), clearly note it

### Monitoring Expectations

- **At session start**: Always read this file to check for questions or blockers from the other party
- **No automatic notifications**: You won't know about updates unless you read the file
- **Latency**: Expect hours to days between question and answer (depends on when the other AI has a session)

### Questions & Answers Protocol

**Asking questions**:
- Include in your log entry under "Questions/Blockers"
- Prefix with `[Q for Claude]` or `[Q for Gemini]` so it's scannable
- If blocking, say so explicitly: "BLOCKING: Cannot proceed without X"

**Answering questions**:
- Create a NEW log entry (don't edit the original)
- Reference the question: "Re: [Q from Claude 2026-01-25]"
- Mark the original question resolved in your entry

**Escalation**:
- If you can't answer a question, escalate to Scott
- If blocking for >24 hours with no response, escalate to Scott

### Example Entry Format

```markdown
### YYYY-MM-DD HH:MM - Brief Title

**Author**: Claude | Gemini

What was done:
- Item 1
- Item 2

Files changed:
- path/to/file.py (description of change)

Questions/Blockers:
- Question for other party?

Next steps:
- What you'll do next
```

---

## Cross-Environment Checklist

When either party changes:

| Change Type | Action Required |
|-------------|-----------------|
| `.proto` files | Run `python scripts/proto_sync.py`, rebuild Docker |
| Migrations (`*.sql`) | Docker: `docker-compose down -v && docker-compose up -d` |
| Python dependencies | Docker: rebuild image |
| Rust code | Docker: `make rust-rebuild` (if applicable) |
| Test files | No sync needed (isolated environments) |

- **2026-01-26 [Gemini]**: Troubleshooting Flight Recorder test failure.
  - *Issue*: Orchestrator cannot connect to Memory service to record fires.
  - *Error*: 'Connection refused' to 127.0.0.1:50051 (should be memory-python:50051).
  - *Action*: Investigating config.py and environment variable propagation.

- **2026-01-26 [Gemini]**: **Task Paused**. User handed off Flight Recorder troubleshooting to Claude. Standing by.

- **2026-01-26 [Claude]**: **Proto fix complete**. Created `types.proto` as single source of truth for SalienceVector. All imports updated, Rust build fixed. Handing back to Gemini for Docker rebuild and Flight Recorder retest.

- **2026-01-26 [Claude]**: **Cleanup**: Deleted redundant `src/memory/run.py`. Use `python scripts/docker.py` for all Docker management.

- **2026-01-26 [Claude]**: **Refactor**: Moved orchestrator `run.py` to `gladys_orchestrator/__main__.py` for consistency with Memory service pattern. Updated Dockerfile to use `python -m gladys_orchestrator start`.

- **2026-01-26 [Claude]**: **TODO**: Audit codebase for other badly named files (run.py, confusing names) and opportunities to use `__main__.py` pattern consistently.

- **2026-01-26 [Claude]**: **ROOT CAUSE FOUND - Fire Recording Issue**:
  - `memory_client` is `None` because connection fails at startup
  - **BUG**: docker-compose `depends_on` was missing `memory-python`!
  - Orchestrator started before memory-python was healthy, connection failed
  - **FIX**: Added `memory-python: condition: service_healthy` to orchestrator's depends_on

  **To test**: Restart Docker stack:
  ```
  docker compose -f src/integration/docker-compose.yml down
  docker compose -f src/integration/docker-compose.yml up -d
  python scripts/docker.py test test_flight_recorder.py
  ```

- **2026-01-26 [Gemini]**: **Resolved Docker Issues & Implemented Service Scripts**.
  - *Fixes*:
    - Implemented new \scripts/docker.py\ using robust \DockerBackend\ logic.
    - Used \up -d --force-recreate\ to solve stale code/stub issues.
    - Verified \	est_flight_recorder.py\ passes.
  - *New Artifacts*:
    - \scripts/_service_base.py\: Core abstraction.
    - \scripts/_docker_backend.py\: Docker implementation.
    - \scripts/docker.py\: Updated entry point.
  - *Status*: Phase 3 (Feedback Persistence) is Verified. Service Scripts Phase 1 & 2 Complete.
