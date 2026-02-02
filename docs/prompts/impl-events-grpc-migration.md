# Implementation: Migrate Dashboard Events Router to gRPC

**Read `CLAUDE.md` first, then `claude_memory.md`, then this prompt.**

## Task

Migrate the dashboard events router from direct PostgreSQL access (`gladys_client.db`) to Memory service gRPC. This closes #66 (dashboard direct-DB tech debt) and partially addresses #67-#69.

**Branch**: Create `dashboard/events-grpc-migration` from `main`
**Logging standard**: `docs/design/LOGGING_STANDARD.md`

## Why

The dashboard backend currently queries PostgreSQL directly via `gladys_client.db` for event listing and single-event lookup. This bypasses the Memory service, meaning query logic is duplicated and bugs must be fixed in two places. The upcoming #63/#65 work adds new dashboard queries — establishing the gRPC pattern first prevents extending the anti-pattern.

## Architecture Rule

**The dashboard MUST NOT query PostgreSQL directly.** All data access goes through the Memory service gRPC API.

## Current State

In `src/services/dashboard/backend/routers/events.py`:
- `_fetch_events()` (line 114) calls `_db.list_events(env.get_db_dsn(), ...)` — direct DB
- SSE `_subscribe()` (line 255) calls `_db.get_event(env.get_db_dsn(), event_id)` — direct DB
- Everything else (submit, feedback, queue) already uses gRPC (orchestrator, executive)

The Memory service already has `QueryByTime` and `QueryBySimilarity` RPCs, but neither matches what the dashboard needs (list by recency with pagination, single event by ID).

## Implementation

### 1. Proto changes — `memory.proto`

Add new RPCs to `MemoryStorage` service:

```protobuf
// List recent events for dashboard (newest first, paginated)
rpc ListEvents(ListEventsRequest) returns (ListEventsResponse);

// Get a single event by ID
rpc GetEvent(GetEventRequest) returns (GetEventResponse);
```

New messages:

```protobuf
message ListEventsRequest {
    int32 limit = 1;              // default 50
    int32 offset = 2;
    string source = 3;            // filter by source, empty = all
    bool include_archived = 4;    // default false
}

message ListEventsResponse {
    repeated EpisodicEvent events = 1;
    string error = 2;
}

message GetEventRequest {
    string event_id = 1;
}

message GetEventResponse {
    EpisodicEvent event = 1;
    string error = 2;
}
```

The `EpisodicEvent` message already has all the fields the dashboard needs (id, timestamp, source, raw_text, salience, response_text, response_id, predicted_success, prediction_confidence). No new fields needed for this PR.

Regenerate stubs: `make proto`

### 2. Memory service — implement new RPCs

In `src/services/memory/gladys_memory/storage.py`, add:

```python
async def list_events(self, *, limit=50, offset=0, source=None, include_archived=False):
    """List recent events, newest first."""
    # Replicate the query from gladys_client/db.py list_events()
    # SELECT id, timestamp, source, raw_text, salience, response_text, response_id,
    #        predicted_success, prediction_confidence
    # LEFT JOIN heuristic_fires ON episodic_event_id for matched_heuristic_id
    # WHERE archived = false (unless include_archived)
    # Optional source filter
    # ORDER BY timestamp DESC LIMIT/OFFSET

async def get_event(self, event_id: str):
    """Fetch single event by ID."""
    # SELECT same columns WHERE id = event_id
```

In `src/services/memory/gladys_memory/grpc_server.py`, add:

```python
async def ListEvents(self, request, context):
    """List recent events for dashboard."""
    # Call self.storage.list_events()
    # Convert each row to EpisodicEvent proto
    # Return ListEventsResponse

async def GetEvent(self, request, context):
    """Get single event by ID."""
    # Call self.storage.get_event()
    # Convert to EpisodicEvent proto
    # Return GetEventResponse
```

Use the async connection pool (`self.pool`) that `storage.py` already maintains — NOT the sync psycopg2 pattern from `gladys_client/db.py`.

### 3. Dashboard events router — switch to gRPC

In `src/services/dashboard/backend/routers/events.py`:

**Remove**: `from gladys_client import db as _db`

**Add**: Memory service gRPC stub usage. Check how `env.py` provides stubs — there should be a `memory_stub()` or similar. If not, add one following the existing pattern for `orchestrator_stub()` and `executive_stub()`.

**Update `_fetch_events()`**: Replace `_db.list_events()` call with gRPC `ListEvents()`. Convert the proto response to the dict format that `_make_event_dict()` expects.

**Update SSE `_subscribe()`**: Replace `_db.get_event()` call with gRPC `GetEvent()`. The SSE handler runs in a thread — the gRPC call is sync (blocking), which is fine since it's already in a thread worker.

**Note on `_make_event_dict()`**: The `path` derivation logic (lines 70-74) will be replaced by `decision_path` column in #63/#65. For this PR, leave it as-is — it's about to be replaced anyway. Don't refactor what's being deleted next.

### 4. Verify no remaining direct-DB imports

After changes, grep the dashboard routers for `gladys_client` imports. The only acceptable remaining usage is in routers that handle operations without Memory service RPCs (e.g., `delete_event` in metrics or admin routes — check if any exist). If so, note them as remaining tech debt items.

## What NOT to change

- `_make_event_dict()` path derivation logic — replaced by #63/#65
- `gladys_client/db.py` itself — other consumers may use it; just stop the dashboard from calling it
- Submit event, feedback, queue endpoints — already use gRPC
- No frontend changes
- No schema changes

## Testing

1. `make proto` succeeds
2. Services start without errors
3. Dashboard loads — Lab tab shows events
4. Submit event via Lab tab — event appears in list
5. SSE stream works — new events appear in real-time
6. Source filter works
7. No `gladys_client.db` imports in dashboard routers (for events)

## Branch setup

```bash
git checkout main
git pull
git checkout -b dashboard/events-grpc-migration
```
