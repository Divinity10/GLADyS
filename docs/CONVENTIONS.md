# Project Conventions

Conventions for code, testing, and dependencies across GLADyS services. These are patterns already established in the codebase — follow them for consistency.

For architectural principles and design decisions, see `CLAUDE.md` and ADRs in `docs/adr/`.

## Python Dependencies

### pyproject.toml Structure

```toml
[project]
name = "gladys-{service}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    # Runtime deps only
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[tool.uv.sources]
gladys-common = { path = "../../lib/gladys_common", editable = true }

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Rules:**
- Test dependencies go in `[project.optional-dependencies] dev`, never in main `dependencies`
- Version pins: `pytest>=8.0`, `pytest-asyncio>=0.23` (match project standard)
- Always include `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` for async services
- Local editable deps use `[tool.uv.sources]`

### Build Backends

- **setuptools**: Services with multiple packages (memory, orchestrator)
- **hatchling**: Libraries and smaller packages (executive, gladys_common, gladys_client)

## Testing

### File Organization

```
src/services/{service}/
├── {package}/
│   └── *.py
└── tests/
    ├── __init__.py      # Always present (even if empty)
    ├── conftest.py      # Fixtures, markers, setup
    └── test_{module}.py # Test files
```

### Naming

- Test files: `test_{module}.py`
- Test functions: `test_{scenario}` (e.g., `test_generate_returns_none_when_unavailable`)
- Test classes: `Test{Feature}` (only when grouping related tests)

### Running Tests

```
make test                          # All services
cd src/services/{service} && uv run pytest tests/ -v  # Single service
```

### Integration Tests

- Live in `tests/integration/` (separate from unit tests)
- Require explicit environment: `LOCAL` or `DOCKER`
- conftest.py auto-skips when prerequisites (PostgreSQL, services) unavailable

## Proto / gRPC

### Source and Output

- Proto source: `proto/` at project root
- Generate: `make proto` (runs `cli/proto_gen.py`)
- Output locations are service-specific (configured in proto_gen.py)

### Import Patterns

Within own service (relative imports):
```python
from . import memory_pb2
from .generated import orchestrator_pb2
```

Cross-service (sys.path — executive importing orchestrator protos):
```python
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "orchestrator"))
from gladys_orchestrator.generated import executive_pb2
```

## Commits

See `CLAUDE.md` for full convention. Summary:

```
type(scope): message
```

Types: `doc`, `feat`, `fix`, `refactor`, `test`, `chore`

- `refactor` for extracting interfaces, renaming, restructuring
- `feat` for new user-visible functionality
- `fix` for bug fixes and review feedback fixes
- No AI attribution in commits

## Makefile

Key targets: `make setup`, `make proto`, `make test`, `make dashboard`, `make start/stop/status`.

Full list: `make help`.
