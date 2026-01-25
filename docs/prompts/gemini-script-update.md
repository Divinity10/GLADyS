# Script Location Changes (2026-01-25)

The service management scripts were consolidated. You need to update your code.

## What Changed

| Old | New |
|-----|-----|
| `src/integration/run.py` | **DELETED** - use `scripts/docker.py` instead |
| `scripts/services.py` | **DELETED** - use `scripts/local.py` instead |

Port config is now in `scripts/_gladys.py`.

## How to Use

```bash
python scripts/docker.py start all      # Start Docker services
python scripts/docker.py status         # Check status
python scripts/docker.py test <test>    # Run tests against Docker
python scripts/docker.py clean all      # Clean DB
python scripts/docker.py logs memory    # Follow logs
python scripts/docker.py psql           # Database shell
```

## Running Tests

Tests now require the wrapper script (they fail if run directly):

```bash
python scripts/docker.py test test_scenario_5_learning_loop.py
```

The wrapper sets these env vars automatically:
- `PYTHON_ADDRESS=localhost:50061`
- `RUST_ADDRESS=localhost:50062`
- `ORCHESTRATOR_ADDRESS=localhost:50060`
- `EXECUTIVE_ADDRESS=localhost:50063`
- `DB_HOST=localhost`
- `DB_PORT=5433`

## Ports (Unchanged)

Docker still uses:
- Memory Python: 50061
- Memory Rust: 50062
- Orchestrator: 50060
- Executive: 50063
- PostgreSQL: 5433

## If Your Code Imports from run.py

Update imports or call `scripts/docker.py` as a subprocess instead.
