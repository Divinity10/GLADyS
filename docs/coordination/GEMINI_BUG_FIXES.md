# Gemini Bug Fix Tasks

**Assigned to**: Gemini
**Date**: 2026-01-26
**Coordinator**: Scott

---

## Before You Start

1. **Read** `docs/coordination/COORDINATION.md` for the coordination protocol
2. **Check** `docs/coordination/MESSAGES.md` for any updates from Claude
3. **Use** `gemini_memory.md` as your scratch pad for progress tracking
4. **Reference** [CONCURRENCY.md](../codebase/CONCURRENCY.md) for concurrency model and [CONCEPT_MAP.md](../../CONCEPT_MAP.md) for concept-to-code mapping

---

## Your Tasks

### Task 1: Fire-and-Forget Error Handling in router.py

**Priority**: HIGH
**File**: `src/orchestrator/gladys_orchestrator/router.py`
**Line**: ~115 (search for `asyncio.create_task`)

#### Problem

`asyncio.create_task()` is used without error handling. If the task raises an exception, it's silently dropped. This makes debugging impossible.

#### Current Code (approximate)

```python
asyncio.create_task(self._memory_client.record_heuristic_fire(...))
```

#### Required Fix

Add an error callback to log exceptions:

```python
def _handle_task_exception(task: asyncio.Task) -> None:
    """Log exceptions from fire-and-forget tasks."""
    try:
        exc = task.exception()
        if exc is not None:
            logger.error(
                "background_task_failed",
                task_name=task.get_name(),
                error=str(exc),
                error_type=type(exc).__name__,
            )
    except asyncio.CancelledError:
        pass  # Task was cancelled, not an error

# Usage:
task = asyncio.create_task(
    self._memory_client.record_heuristic_fire(...),
    name="record_heuristic_fire"
)
task.add_done_callback(_handle_task_exception)
```

#### Acceptance Criteria

- [ ] All `asyncio.create_task()` calls in router.py have error callbacks
- [ ] Errors are logged via structlog (use existing logger pattern in file)
- [ ] Task names are descriptive for debugging
- [ ] Existing tests still pass

---

### Task 2: gRPC Channel Leaks in dashboard.py

**Priority**: HIGH
**File**: `src/ui/dashboard.py`
**Lines**: ~77-95 (search for `get_*_stub` functions)

#### Problem

The dashboard creates new gRPC channels for every stub call but never closes them. This causes resource leaks.

#### Current Code Pattern

```python
def get_orchestrator_stub():
    channel = grpc.insecure_channel(get_orchestrator_address())
    return orchestrator_pb2_grpc.OrchestratorStub(channel)
    # channel is never closed!
```

#### Required Fix

Create a managed channel class that:

1. Caches channels per address
2. Provides cleanup capability
3. Can be reset when environment changes

**Option A: Context manager pattern**

```python
@contextmanager
def get_channel(address: str):
    """Get a gRPC channel that will be properly closed."""
    channel = grpc.insecure_channel(address)
    try:
        yield channel
    finally:
        channel.close()

# Usage:
with get_channel(get_orchestrator_address()) as channel:
    stub = orchestrator_pb2_grpc.OrchestratorStub(channel)
    response = stub.SomeMethod(request)
```

**Option B: Session-scoped channels (recommended for Streamlit)**

```python
def get_or_create_channel(address: str) -> grpc.Channel:
    """Get cached channel or create new one."""
    if "grpc_channels" not in st.session_state:
        st.session_state.grpc_channels = {}

    if address not in st.session_state.grpc_channels:
        st.session_state.grpc_channels[address] = grpc.insecure_channel(address)

    return st.session_state.grpc_channels[address]

def close_all_channels():
    """Close all cached channels (call on env switch)."""
    if "grpc_channels" in st.session_state:
        for channel in st.session_state.grpc_channels.values():
            channel.close()
        st.session_state.grpc_channels = {}
```

#### Acceptance Criteria

- [ ] Channels are reused within a session (not created per call)
- [ ] Channels are closed when environment switches
- [ ] `close_all_channels()` is called when user changes environment
- [ ] No `grpc.insecure_channel()` calls outside the managed pattern
- [ ] Dashboard still works (test manually: all tabs load, event simulation works)

---

## Coordination Notes

### Files You Own (edit freely)

- `src/orchestrator/gladys_orchestrator/router.py`
- `src/ui/dashboard.py`

### Files Claude Owns (do not edit)

- `src/orchestrator/gladys_orchestrator/outcome_watcher.py`
- `proto/memory.proto`
- `src/memory/python/gladys_memory/grpc_server.py`
- `src/memory/python/gladys_memory/storage.py`

### Proto Regeneration

After Claude updates `memory.proto`, you'll need to regenerate stubs:

```bash
python cli/proto_gen.py
```

Claude will post in `MESSAGES.md` when this is needed.

---

## How to Ask Questions

If you have questions for Claude or need to coordinate:

1. Post in `docs/coordination/MESSAGES.md` using the format in `COORDINATION.md`
2. Continue with other work if possible
3. Check back for responses

---

## When You're Done

1. Update `gemini_memory.md` with what you completed
2. Post completion notice in `docs/coordination/MESSAGES.md`
3. List any issues or concerns discovered

---

## Reference: Success Criteria from REFACTORING_PLAN.md

Your tasks contribute to these success criteria:

- [ ] Background task failures logged (Task 1)
- [ ] No gRPC channel leaks (Task 2)
- [ ] Environment switch works without app restart (Task 2)
