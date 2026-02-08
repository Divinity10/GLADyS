# Troubleshooting


## Common Mistakes to Avoid

1. **Port confusion**: MemoryStorage is 50051, SalienceGateway is 50052. They're different!
2. **Assuming keyword matching**: Heuristics use embedding similarity, not word overlap
3. **source vs origin**: `source` is the event sensor, `origin` is how the heuristic was created
4. **source_filter misuse**: Filters by condition_text PREFIX (e.g., "minecraft:..."), NOT by event.source
5. **Stale stubs**: After editing `proto/*.proto`, run `python cli/proto_gen.py` to regenerate
6. **Docker ports**: Add 10 to local ports (50051 -> 50061)
7. **Missing trace IDs**: Always extract/propagate `x-gladys-trace-id` from gRPC metadata
8. **Fire-and-forget tasks**: `asyncio.create_task()` without error handling silently drops exceptions
9. **gRPC channel leaks**: Always close channels or use a managed client class
10. **Async lock scope**: If using `asyncio.Lock`, protect ALL access points, not just some
11. **Adding gladys_common import without Dockerfile update**: If you add `from gladys_common import ...` to a service, the Dockerfile MUST be updated (see Docker Build Requirements)
12. **Using local context for services with shared deps**: docker-compose.yml must use project root context (`../..`) for any service that depends on gladys_common
13. **Dashboard router confusion**: `dashboard/backend/routers/` returns HTML (htmx), `fun_api/routers/` returns JSON (REST API). Both are mounted in `main.py`. Check which you need before modifying.
14. **Using Alpine x-for for server data in htmx content**: x-for doesn't reliably render when content is loaded via htmx. Use Jinja loops (Pattern A) instead. See `DASHBOARD_COMPONENT_ARCHITECTURE.md`.
15. **fun_api location confusion**: `fun_api/` is at `src/services/fun_api/` (sibling to `dashboard/`), NOT inside the dashboard directory. The dashboard imports it via `from fun_api.routers import ...`.
16. **JSON vs HTML endpoints**: Both exist for many entities. JSON: `fun_api/routers/heuristics.py`. HTML: `dashboard/backend/routers/heuristics.py`. htmx tabs need HTML routers.

---

## "No immediate response" in UI despite services running

**Symptoms**: Event submitted in UI shows "(No immediate response)" even though all services show healthy.

**Diagnostic steps**:

1. **Run the integration test**:
   ```bash
   uv run python tests/integration/test_llm_response_flow.py
   ```
   This tests Executive directly AND through Orchestrator. If both pass, the issue is in the UI.

2. **Check LLM configuration**:
   ```bash
   python cli/local.py status
   ```
   Look for the `ollama` line - it should show `[OK] running` with your model name.

3. **Verify named endpoint resolution**: The Executive uses named endpoints. If you changed `.env` to use `OLLAMA_ENDPOINT=local`, the Executive MUST be restarted to pick up the change:
   ```bash
   python cli/local.py restart executive-stub
   ```

**Root causes** (in order of likelihood):

| Cause | Check | Fix |
|-------|-------|-----|
| Executive not restarted after config change | `status` shows wrong model | `restart executive-stub` |
| Salience too low (event queued) | UI shows "QUEUED" path | Select "Force HIGH (Immediate)" in UI or wait for async processing |
| Named endpoint not resolved | Executive startup doesn't show Ollama URL | Check `.env` has `OLLAMA_ENDPOINT_<NAME>` matching `OLLAMA_ENDPOINT` |
| Ollama unreachable | `status` shows `[--] unreachable` | Start Ollama or fix URL |
| Wrong environment selected | UI sidebar shows "Docker" | Switch to "Local" in UI sidebar |

**Key insight**: The Executive reads `.env` at startup and resolves named endpoints then. Changing `.env` has no effect until restart. This is different from the scripts which re-read `.env` on every invocation.

---

## Services fail to start

**"Address already in use"**: Another instance is running. Use `local.py stop all` first or check for zombie processes.

**"Connection refused" on health check**: Service crashed immediately after starting. Run in foreground to see errors:
```bash
python -m gladys_executive start  # instead of via local.py
```

## Database schema issues

**"column does not exist"**: Migration not applied. Run:
```bash
python cli/local.py migrate
```

**Different behavior local vs Docker**: Schema drift. Ensure both use same migrations:
```bash
python cli/local.py migrate
python cli/docker.py migrate
```

---

## Quick Commands

```bash
# Start all services locally
python cli/local.py start all

# Check status (process-level)
python cli/local.py status

# Check health (gRPC-level)
python cli/local.py health
python cli/local.py health -d    # detailed with uptime/metrics

# Regenerate proto stubs after editing proto/
python cli/proto_gen.py

# Cache management
python cli/local.py cache stats
python cli/local.py cache list
python cli/local.py cache flush

# Run integration tests
cd tests/integration && uv run pytest -v

# Database query
python cli/local.py query "SELECT * FROM heuristics LIMIT 5"
```
