# Task: Evaluation Dashboard (Streamlit)

**Assigned to**: Gemini
**Date**: 2026-01-25
**Parallel work**: Claude is implementing TD Learning in `src/memory/` - do not modify those files.

---

## Objective

Build a minimal Streamlit dashboard to visualize and evaluate the GLADyS learning loop. This UI will help us:
1. See what's happening in real-time (events, heuristics, decisions)
2. Evaluate effectiveness (cache hit rate, rules learned)
3. Demo the system to non-technical stakeholders

---

## Context

GLADyS learns user preferences by converting expensive LLM reasoning into cheap heuristic rules:
- **Events** come in from sensors (games, smart home, etc.)
- **Heuristics** are learned rules with confidence scores
- When confidence is high enough, the system uses the rule instead of calling the LLM
- User feedback (thumbs up/down) adjusts confidence

The "killer feature" is: slow expensive thinking → fast cheap pattern-matching over time.

---

## Technical Requirements

### Stack
- **Streamlit** for the UI (quick to build, Python-native)
- **psycopg2** for direct database reads (no gRPC needed for MVP)
- **No modifications** to existing services - this is a read-only dashboard

### Environment
- Use Docker containers for testing: `src/integration/docker-compose.yml`
- Database: PostgreSQL (in Docker: `gladys-db` container, host port **5433**)
- Database name: `gladys`, user: `gladys`, password: `gladys`

### Port Separation (IMPORTANT)
Docker and local services use **different ports** to avoid conflicts:

| Service        | Local Port | Docker Port |
|----------------|------------|-------------|
| Orchestrator   | 50050      | 50060       |
| Memory Python  | 50051      | 50061       |
| Memory Rust    | 50052      | 50062       |
| Executive      | 50053      | 50063       |
| PostgreSQL     | 5432       | 5433        |

For tests against Docker, set environment variables:
```bash
export PYTHON_ADDRESS=localhost:50061
export RUST_ADDRESS=localhost:50062
export ORCHESTRATOR_ADDRESS=localhost:50060
```

### File Location
Create new directory: `src/ui/`
```
src/ui/
├── pyproject.toml      # Dependencies: streamlit, psycopg2-binary
├── dashboard.py        # Main Streamlit app
└── README.md           # How to run
```

---

## UI Components

### 1. Recent Events Panel
Show last 20 events from `episodic_events` table:
- Timestamp
- Source (e.g., "minecraft", "smart_home")
- Event text (truncated)
- How it was handled: "Cache Hit" vs "LLM Reasoning"
  - If `response_id` is set → LLM was called
  - If `predicted_success` is set → show the prediction

### 2. Heuristics Table
Show all heuristics from `heuristics` table:
- Name
- Condition (JSON, show summary)
- Confidence (0.0-1.0, maybe color-coded: red < 0.3, yellow 0.3-0.7, green > 0.7)
- Fire count
- Success count
- Origin (built_in, pack, learned, user)
- Frozen status

### 3. Stats Summary
Calculate and display:
- Total events processed
- Total heuristics
- Cache hit rate (events with high-confidence heuristic match vs total)
- LLM calls (events with response_id set)
- Average heuristic confidence

### 4. Controls
- **Refresh button** - manually reload data
- **Auto-refresh toggle** - poll every N seconds
- **Time filter** - show events from last hour/day/all

---

## Database Schema Reference

### episodic_events
```sql
id                    UUID
timestamp             TIMESTAMP
source                TEXT        -- e.g., "minecraft", "smart_home"
raw_text              TEXT        -- Event description
predicted_success     FLOAT       -- LLM prediction (0.0-1.0), NULL if cache hit
prediction_confidence FLOAT       -- LLM confidence in prediction
response_id           TEXT        -- Set if LLM was called
```

### heuristics
```sql
id                    UUID
name                  TEXT
condition             JSONB       -- Pattern to match
action                JSONB       -- What to do when matched
confidence            FLOAT       -- 0.0-1.0
fire_count            INTEGER
success_count         INTEGER
origin                TEXT        -- 'built_in', 'pack', 'learned', 'user'
origin_id             TEXT
frozen                BOOLEAN
created_at            TIMESTAMP
```

---

## Service Management

Use the Docker service management script for all service operations:

```bash
# From project root

# Start/stop services
python scripts/docker.py start all           # Start all services
python scripts/docker.py stop all            # Stop all services
python scripts/docker.py status              # Check service status

# Database utilities
python scripts/docker.py psql                # Open database shell
python scripts/docker.py clean heuristics    # Clear heuristics table
python scripts/docker.py clean events        # Clear events table
python scripts/docker.py clean all           # Clear all data
python scripts/docker.py reset               # Full reset (stop, clean, restart)

# Logs
python scripts/docker.py logs memory         # Follow memory service logs
python scripts/docker.py logs all            # Follow all logs
```

Full documentation: `docs/design/SERVICE_MANAGEMENT.md`

---

## Testing

1. Start Docker services:
   ```bash
   python scripts/docker.py start all
   python scripts/docker.py status           # Verify all services are healthy
   ```

2. Run integration tests to populate data:
   ```bash
   python scripts/docker.py test test_scenario_5_learning_loop.py
   ```

3. Run the dashboard:
   ```bash
   cd src/ui
   uv run streamlit run dashboard.py
   ```

4. Verify:
   - Events appear in the Recent Events panel
   - Heuristics show up with confidence values
   - Stats are calculated correctly

5. To reset and test again:
   ```bash
   python scripts/docker.py clean all        # Clear data
   # Re-run tests
   ```

---

## File Boundaries

**You CAN modify:**
- `src/ui/*` (new directory you create)
- `src/integration/docker-compose.yml` (if needed for UI container)

**Do NOT modify:**
- `src/memory/*` - Claude is working here
- `src/executive/*`
- `src/orchestrator/*`
- Any proto files

---

## Deliverables

1. Working Streamlit dashboard in `src/ui/`
2. README with setup/run instructions
3. Update `gemini_memory.md` with progress and decisions

---

## Notes

- Keep it simple - this is an evaluation tool, not a production UI
- Direct SQL queries are fine - no need for an ORM
- If you need sample data, run the integration tests first
- The Docker database is separate from Scott's local database - no conflicts
