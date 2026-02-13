# Memory Subsystem Implementation Plan

**Status**: In Progress
**Last Updated**: 2026-01-21

## Overview

Two-layer memory architecture:

- **Rust Fast Path** (<5ms): L0 cache, novelty detection, heuristic lookup
- **Python Storage Path** (<50ms): PostgreSQL + pgvector, embeddings

## Completed Setup

- [x] Project structure created
- [x] Proto definitions (`memory.proto`)
- [x] Python package skeleton (uv, tests passing)
- [x] Rust crate skeleton (cargo, tests passing)
- [x] SQL migration (`001_initial_schema.sql`)
- [x] docker-compose for PostgreSQL

## Implementation Phases

### Phase 1: Python Storage Path ✅ COMPLETE

#### 1.1 Database Connection & Basic Operations ✅

- [x] **Task**: Implement working PostgreSQL connection with pgvector
- **Files**: `gladys_memory/storage.py`
- **Tests**: `tests/test_storage.py` (14 tests passing)
- **Done when**: Can connect to PostgreSQL, store an event, retrieve by ID

#### 1.2 Event Storage (CRUD) ✅

- [x] **Task**: Complete episodic event storage implementation
- **Files**: `gladys_memory/storage.py`
- **Tests**: `tests/test_storage.py`
- **Done when**:
  - `store_event()` works with all fields ✓
  - `query_by_time()` returns events in range ✓
  - `query_by_similarity()` returns semantically similar events ✓

#### 1.3 Embedding Integration ✅

- [x] **Task**: Integrate embedding generation into storage flow
- **Files**: `gladys_memory/storage.py`, `gladys_memory/embeddings.py`
- **Tests**: `tests/test_embeddings.py` (6 tests passing)
- **Done when**: Events stored with auto-generated embeddings if not provided ✓

#### 1.4 Heuristic Storage ✅

- [x] **Task**: Implement heuristic CRUD operations
- **Files**: `gladys_memory/storage.py`
- **Tests**: `tests/test_storage.py`
- **Done when**: Can store, query, and update heuristics ✓

#### 1.5 gRPC Server Implementation ✅

- [x] **Task**: Generate protobuf code and implement gRPC servicer
- **Files**:
  - Generated: `gladys_memory/memory_pb2.py`, `gladys_memory/memory_pb2_grpc.py` ✓
  - Implemented: `gladys_memory/grpc_server.py` ✓
- **Tests**: `tests/test_grpc.py` (12 tests passing)
- **Done when**: gRPC server starts, responds to StoreEvent and QueryBySimilarity ✓

### Phase 2: Rust Fast Path (In Progress)

#### 2.1 gRPC Client ✅

- [x] **Task**: Implement gRPC client to call Python storage
- **Files**: `rust/src/client.rs`, `rust/src/lib.rs`
- **Tests**: `rust/src/client.rs` (unit tests), `rust/tests/integration_test.rs`
- **Done when**: Can call Python storage service from Rust ✓

#### 2.2 L0 Cache Implementation ✅

- [x] **Task**: Complete in-memory cache with eviction
- **Files**: `rust/src/lib.rs` (cache implemented inline)
- **Tests**: Unit tests in module (10 tests passing)
- **Done when**:
  - Add/retrieve events from cache ✓
  - Eviction when capacity exceeded ✓ (oldest-first, timestamp-based)
  - Cache statistics tracking ✓

#### 2.3 Novelty Detection ✅

- [x] **Task**: Implement novelty detection using embeddings
- **Files**: `rust/src/lib.rs`
- **Tests**: Unit tests in module
- **Done when**:
  - `is_novel(embedding)` returns true/false ✓
  - Configurable similarity threshold ✓
  - Uses cache for comparison ✓

#### 2.4 Heuristic Matching (Partial)

- [ ] **Task**: Implement heuristic condition matching
- **Files**: `rust/src/lib.rs`
- **Tests**: Unit tests in module
- **Status**: Basic structure in place, condition matching logic deferred (JSONB schema allows flexibility)
- **Done when**:
  - Load heuristics from Python storage ✓
  - Match event context against conditions (deferred)
  - Return matching heuristics sorted by confidence ✓ (by confidence filter)

### Phase 3: Integration

#### 3.1 End-to-End Flow

- [ ] **Task**: Wire up Rust → Python flow
- **Files**: `rust/src/main.rs`, integration tests
- **Tests**: `rust/tests/integration_test.rs`
- **Status**: Client can connect and call Python service. Need to test with server running.
- **Done when**:
  - Event comes in to Rust
  - Rust checks cache/novelty/heuristics
  - Falls through to Python storage if needed
  - Response returns through Rust

#### 3.2 Docker Compose Integration

- [ ] **Task**: Add Rust service to docker-compose
- **Files**: `docker-compose.yml`, add Dockerfile for Rust
- **Done when**: `docker-compose up` starts both services

## Key Files Reference

```
src/memory/
├── proto/memory.proto           # gRPC contract ✓
├── rust/
│   ├── src/
│   │   ├── lib.rs              # Main library (cache, novelty) ✓
│   │   ├── main.rs             # Service entry point ✓
│   │   └── client.rs           # gRPC client ✓
│   └── tests/
│       └── integration_test.rs  # Rust ↔ Python tests ✓
├── python/
│   ├── gladys_memory/
│   │   ├── storage.py          # PostgreSQL operations ✓
│   │   ├── embeddings.py       # Sentence transformers ✓
│   │   ├── grpc_server.py      # gRPC service ✓
│   │   ├── memory_pb2.py       # Generated ✓
│   │   └── memory_pb2_grpc.py  # Generated ✓
│   └── tests/
│       ├── test_embeddings.py  # ✓ 6 passing
│       ├── test_storage.py     # ✓ 14 passing
│       └── test_grpc.py        # ✓ 12 passing
└── migrations/
    └── 001_initial_schema.sql  # ✓ Ready
```

## Test Summary

| Component | Test Type | Command | Status |
|-----------|-----------|---------|--------|
| Python embeddings | Unit | `uv run pytest tests/test_embeddings.py` | 6 passing ✓ |
| Python storage | Integration | `uv run pytest tests/test_storage.py` | 14 passing ✓ |
| Python gRPC | Integration | `uv run pytest tests/test_grpc.py` | 12 passing ✓ |
| Rust cache/novelty | Unit | `cargo test` | 10 passing ✓ |
| Rust client | Integration | `cargo test --test integration_test` | Needs Python server |
| End-to-end | Integration | Manual | Pending |

## ADR References

- [ADR-0004](../../docs/adr/ADR-0004-Memory-Schema-Details.md) - Schema details
- [ADR-0009](../../docs/adr/ADR-0009-Memory-Contracts-and-Compaction-Policy.md) - Contracts
- [ADR-0010](../../docs/adr/ADR-0010-Learning-and-Inference.md) - Learning architecture

## Current Focus

**Next task**: Phase 3.1 - Run end-to-end integration test with both services

**To test integration**:

1. Start PostgreSQL: `docker-compose up -d`
2. Start Python server: `cd python && uv run python -m gladys_memory.grpc_server`
3. Run Rust tests: `cd rust && cargo test --test integration_test`

**Blockers**: None
