# PoC 0: Exploratory (COMPLETE)

**Status**: Complete
**Type**: Proof-of-concept

### Question answered

Can we build the individual subsystems and get them communicating?

### What was proven

- Event pipeline exists: sensor -> orchestrator -> salience -> executive -> response
- Heuristic storage and retrieval via embeddings (CBR with pgvector cosine similarity)
- LLM integration via Ollama (Executive stub responds to events)
- Salience gateway evaluates events using cached heuristics (Rust)
- Dashboard for dev/QA observation (FastAPI + htmx)
- Explicit feedback endpoint exists (SubmitFeedback RPC)

### What was NOT proven (known gaps)

- **Confidence updates from feedback**: Explicit feedback path exists but effect on confidence scores is unverified. We don't know if feedback actually changes heuristic behavior.
- **Salience cache not functioning as designed**: The Rust LRU cache was designed as the fast path for heuristic matching (cache -> DB -> LLM), but currently only tracks hit/miss stats - Python storage is always queried. The cache must become authoritative for matching in Phase 1. This requires solving cache staleness (invalidation when heuristics are created, updated, or decayed).
- **Python Orchestrator viability**: Works under trivial load (manual event submission). No data on behavior under realistic concurrent event volume. Adequate for PoC 0 scope; unknown beyond that.
- **Heuristic creation from feedback**: The LLM can respond to events, but the path from positive feedback -> new heuristic is not proven. This is the core claim Phase 1 must validate.

### Lessons learned

- Embedding-based semantic matching is the right approach
- Python is adequate for all services at Phase scale; no evidence C#/Rust rewrites are needed yet
- Current codebase structure doesn't match the architecture we've decided on - directory restructure needed before building more
- Integration gaps exist in the feedback pipeline (GetHeuristic RPC missing, feedback_source not propagated through gRPC)
- Orchestrator processes one event at a time; executive handles one per RPC call. Fine for PoC 0 but architectural constraint for real sensor data.
