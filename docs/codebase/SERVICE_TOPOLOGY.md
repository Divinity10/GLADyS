# Service Topology

> **Note on Languages**: The Orchestrator and Executive are currently implemented in **Python**. This differs from `GEMINI.md` / ADR-0001 (which specify Rust/C#). This map reflects the *actual* codebase state.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL CALLERS                            │
│              (Sensors, Dashboard UI, Tests, Executive)              │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Orchestrator │    │  SalienceGateway │    │    Executive     │
│    (Python)   │    │     (Rust)       │    │    (Python)      │
│   Port 50050  │    │   Port 50052     │    │   Port 50053     │
│               │    │                  │    │                  │
│ OrchestratorSvc│   │ SalienceGateway  │    │ ExecutiveService │
│               │    │ (evaluates       │    │ (decides action)   │
│ Routes events │    │  salience)       │    │                  │
└───────┬───────┘    └────────┬─────────┘    └──────────────────┘
        │                     │
        │                     │ QueryMatchingHeuristics RPC
        │                     ▼
        │            ┌──────────────────┐
        │            │  MemoryStorage   │
        └───────────►│    (Python)      │
                     │   Port 50051     │
                     │                  │
                     │ MemoryStorage    │
                     │ (stores data,    │
                     │  generates       │
                     │  embeddings)     │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │   PostgreSQL     │
                     │  + pgvector      │
                     │   Port 5432      │
                     └──────────────────┘
```

---

## Data Flow: Event Processing

```
1. Sensor emits event
        │
        ▼
2. Orchestrator.PublishEvent (50050)
        │
        ▼
3. Orchestrator calls SalienceGateway.EvaluateSalience (50052)
        │
        ├─► Rust checks local LRU cache
        │   └─► Cache HIT: return cached salience + record hit
        │
        └─► Cache MISS: Rust calls MemoryStorage.QueryMatchingHeuristics (50051)
                │
                ▼
            Python does semantic search (embedding cosine similarity)
                │
                ▼
            Results returned to Rust → cached → salience computed
        │
        ▼
4. Orchestrator ALWAYS forwards to Executive.ProcessEvent (50053)
   with heuristic suggestion context (if any match found)
   Exception: emergency fast-path (confidence >= 0.95 AND threat >= 0.9)
        │
        ▼
5. Executive decides: high-confidence heuristic → fast-path (no LLM)
                      otherwise → LLM reasoning, may create new heuristic
```

---

## Data Flow: Heuristic Creation and Learning

```
1. Executive decides to create heuristic from LLM response
        │
        ▼
2. Executive calls MemoryStorage.StoreHeuristic (50051)
        │  - condition_text: natural language trigger
        │  - effects_json: what to do when matched
        │  - origin: 'learned', 'user', 'pack', 'built_in'
        │
        ▼
3. Python generates embedding from condition_text
        │
        ▼
4. Heuristic stored in PostgreSQL (heuristics table)

--- Later, when heuristic fires ---

5. Event matches heuristic during EvaluateSalience
        │
        ▼
6. Executive records fire: MemoryStorage.RecordHeuristicFire (50051)
        │
        ▼
7. User gives feedback (thumbs up/down) OR outcome detected
        │
        ▼
8. MemoryStorage.UpdateHeuristicConfidence (50051)
        │  - Uses TD learning: new_conf = old_conf + lr * (actual - predicted)
        │
        ▼
9. Confidence updated, heuristic becomes more/less trusted

--- Heuristic deletion (KNOWN GAP) ---

10. Dashboard calls DELETE /api/heuristics/{id}
        │
        ▼
11. fun_api/heuristics.py → Direct DB delete (bypasses gRPC, tech debt #83)
        │
        ▼
12. Heuristic removed from PostgreSQL
        │
        ✗ Rust SalienceGateway NOT notified
        ✗ Stale heuristic may remain in Rust LRU cache
```

**BUG**: Deleting a heuristic via dashboard does not call `NotifyHeuristicChange` to invalidate Rust cache. The deleted heuristic may continue to match events until cache TTL expires or cache is flushed.

---

## Data Ownership: Who Writes What

Each table has a single owning component. No table is written by multiple services.

| Table | Owner | Write Paths | Key Files |
|-------|-------|-------------|-----------|
| `episodic_events` | Orchestrator | (1) Immediate heuristic match, (2) After queued event processed | `server.py:182`, `event_queue.py:248` |
| `heuristic_fires` | Orchestrator | On any heuristic match (via LearningModule) | `learning.py:on_fire()` |
| `heuristics` | Executive | On positive feedback (learned patterns) | `gladys_executive/server.py:537-563` |
| `heuristics.confidence` | Executive | On any feedback (TD learning update) | `gladys_executive/server.py:477-485` |
| `heuristic_fires.outcome` | LearningModule | Implicit feedback (timeout, undo, ignored-3x, pattern match) | `learning.py:on_outcome()` |

### Response Delivery

All event responses flow through the Orchestrator -- no component can push responses directly to clients.

| Path | Flow | Delivery |
|------|------|----------|
| Emergency fast-path | Sensor → Orchestrator → EventAck (inline) | Synchronous in PublishEvents stream (confidence >= 0.95 AND threat >= 0.9 only) |
| Normal (all other events) | Sensor → Orchestrator → Queue → Executive → Orchestrator → broadcast | Async via SubscribeResponses stream. Executive decides heuristic fast-path vs LLM. |
