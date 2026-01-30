# GLADyS Memory Subsystem

The Memory subsystem stores and retrieves GLADyS's memories - everything from recent conversations to learned behaviors. Other subsystems (Orchestrator, Executive, etc.) call Memory via gRPC to remember things and recall relevant context.

## Who Needs This?

| You are... | What to do |
|------------|------------|
| **Working on Orchestrator, Executive, or other subsystems** | Start Memory via Docker. Your code calls it over gRPC. See "Connecting from Other Code" below. |
| **Working on Memory subsystem code** | See "Development" section below. |
| **Just running GLADyS** | Start Memory via Docker. Other subsystems will connect automatically. |

## Starting Memory (Docker)

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/)

From `src/memory`:

```
python run.py start     # Start all services
python run.py status    # Check they're running
python run.py stop      # Stop when done
```

Or directly: `docker compose up -d`

Once running, Memory listens on:
- **Port 50052** - Rust fast path (use this for most calls)
- **Port 50051** - Python storage (direct access, usually not needed)

## Connecting from Other Code

Other subsystems talk to Memory via **gRPC**. Here's what you need:

### 1. Get the proto file

The API contract is defined in [`proto/memory.proto`](../../proto/memory.proto) at the project root. This file defines:
- `StoreEpisode` - Save a memory
- `QueryEpisodes` - Search memories by similarity
- `GenerateEmbedding` - Get vector embedding for text
- etc.

### 2. Generate client code for your language

**Rust** (like the SalienceGateway):
```toml
# Cargo.toml
[dependencies]
tonic = "0.12"
prost = "0.13"

[build-dependencies]
tonic-build = "0.12"
```

```rust
// build.rs - see src/memory/rust/build.rs for working example
fn main() {
    tonic_build::compile_protos(&["proto/memory.proto"], &["proto/"]).unwrap();
}
```

**Python**:
```bash
# From project root
python scripts/proto_gen.py
```

**C#** (like Executive):
```xml
<!-- .csproj -->
<PackageReference Include="Grpc.Net.Client" Version="2.x" />
<PackageReference Include="Google.Protobuf" Version="3.x" />
<Protobuf Include="proto/memory.proto" />
```

### 3. Connect and call

```rust
// Rust example
let mut client = MemoryClient::connect("http://localhost:50052").await?;

let response = client.store_episode(StoreEpisodeRequest {
    source: "orchestrator".into(),
    raw_text: "User said hello".into(),
    ..Default::default()
}).await?;
```

```python
# Python example
import grpc
from memory_pb2_grpc import MemoryStub

channel = grpc.insecure_channel("localhost:50052")
client = MemoryStub(channel)
response = client.StoreEpisode(StoreEpisodeRequest(source="test", raw_text="Hello"))
```

## Architecture

```
┌──────────────────────────────────────┐
│     Orchestrator / Executive / etc   │
│         (your code goes here)        │
└──────────────────┬───────────────────┘
                   │ gRPC calls
                   ▼
┌──────────────────────────────────────┐
│    SalienceGateway (port 50052)      │  ← EvaluateSalience, cache mgmt
│  • Rust service                      │
│  • LRU cache (50 heuristics max)     │
│  • Calls Python for semantic search  │
│  • Cache tracks hits/misses/stats    │
└──────────────────┬───────────────────┘
                   │ QueryMatchingHeuristics RPC
                   ▼
┌──────────────────────────────────────┐
│    MemoryStorage (port 50051)        │  ← Store/query data
│  • Python service                    │
│  • Embedding-based semantic search   │
│  • PostgreSQL + pgvector storage     │
│  • All heuristic/event persistence   │
└──────────────────────────────────────┘
```

**Key distinction**:
- **SalienceGateway (Rust, 50052)**: Handles `EvaluateSalience` RPC. Calls Python on every salience eval for semantic matching. Cache is for stats/tracking.
- **MemoryStorage (Python, 50051)**: Handles `Store*`, `Query*`, `Update*` RPCs. Does the actual embedding search.

---

## Development (Memory Contributors Only)

If you're changing the Memory subsystem itself:

### Running tests

```bash
# Start database first
docker compose up -d postgres

# Python tests
cd python && uv sync && uv run pytest

# Rust tests
cd rust && cargo test
```

### Running locally (instead of Docker)

For faster iteration when debugging:

```bash
# Option 1: Use the admin script (recommended)
python scripts/local.py start all

# Option 2: Start manually
# Terminal 1: Database (using local PostgreSQL or Docker)
docker compose up -d postgres

# Terminal 2: Python MemoryStorage
cd python && uv run python -m gladys_memory start

# Terminal 3: Rust SalienceGateway
cd rust && cargo run --release
```

### Directory structure

```
src/memory/
├── proto/memory.proto      # gRPC API contract (shared with clients)
├── python/                 # Storage layer + ML
├── rust/                   # Fast path cache
├── migrations/             # Database schema
└── docker-compose.yml      # Runs everything
```

## Troubleshooting

**"Connection refused" when calling Memory:**
- Is Docker running? `python run.py status`
- Are you calling the right port? (50052 for fast path)

**Services won't start:**
- Check logs: `python run.py logs`
- Port already in use? Check with `netstat -ano | findstr :50052` (Windows) or `lsof -i :50052` (Mac)

**Reset everything:**
```
python run.py reset    # WARNING: Deletes all data
python run.py start
```
