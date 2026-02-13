# Testing Strategy

## Purpose

Tests protect the validity of experimental results. GLADyS is hypothesis-driven incremental development (see `docs/design/ITERATIVE_DESIGN.md`) -- each Phase has proof obligations with observable success criteria. If a bug silently corrupts data flowing through the pipeline, experimental observations become untrustworthy and we won't know it.

The question isn't "is this code production-ready?" -- it's "can I trust the results I'm getting from this pipeline?"

## What to Test

### Priority 1: Data integrity through the pipeline

Events, heuristics, confidence updates, and feedback must flow correctly across service boundaries. A dropped candidate, a silently ignored magnitude, or a miscounted success_count invalidates the experiment.

**Examples**:

- Orchestrator passes all candidates to executive (not just the best match)
- Memory service applies magnitude-weighted Bayesian updates correctly
- Feedback source propagates end-to-end (implicit vs explicit vs llm_endorsement)
- Event accounting balances (submitted = stored + timed-out)

### Priority 2: Contract correctness at service boundaries

Proto contracts, gRPC request/response shapes, and field mapping between services. When one service changes, tests at the boundary catch mismatches before they become silent data corruption.

**Examples**:

- Proto fields populated correctly in request construction
- Response fields mapped to the right internal fields
- Graceful behavior when a downstream service is unavailable

### Priority 3: Decision logic that affects experimental outcomes

Strategy decisions (heuristic vs LLM path), confidence thresholds, endorsement logic. These directly determine what the system does -- errors here produce misleading experimental data.

**Examples**:

- Heuristic fires when confidence >= threshold (System 1 path)
- Below-threshold candidates go to LLM (System 2 path)
- Endorsement only triggers above similarity threshold

### Lower priority: Presentation, formatting, non-critical paths

UI rendering, log message wording, prompt text formatting. These matter for usability but don't affect experimental validity. Test them when convenient, don't block on them.

## Principles

### Test expected behavior, not current implementation

Tests define what the system *should* do. If the design changes, update the tests first to reflect the new expected behavior, then update the code. Never write code to satisfy a test that validates outdated behavior.

**Anti-pattern** (from #152 review): Codex added a duplicate format line to production code with the comment "backward-compatible formatting expected by existing strategy tests." The correct action was to update the test to match the design spec.

### One behavior per test

Each test should validate one specific behavior. The test name should describe that behavior. If a test fails, the name should tell you what's broken without reading the test body.

**Good**: `test_below_threshold_no_update`, `test_endorsement_updates_confidence`
**Bad**: `test_llm_path` (tests decision path, prompt format, confidence capping, and call count in one test)

### No duplicate coverage

If two tests validate the same behavior, one is redundant. When adding a new test that covers a behavior already tested elsewhere, remove the old test.

**Anti-pattern** (from #152 review): `test_candidates_in_prompt_randomized` in `test_decision_strategy.py` tested the same prompt format as `test_evaluation_prompt_includes_candidates` in `test_bootstrapping.py` -- and the bootstrapping version was strictly better (actually mocked shuffle to verify randomization). The old test was removed.

### Test at the right level

- **Unit tests**: Logic that can be tested in isolation (cosine similarity, config parsing, prompt building). Fast, deterministic.
- **Integration tests**: Behavior that depends on multiple components working together (strategy + LLM + memory client). Use mocks for external services.
- **Pipeline tests**: End-to-end data flow (event submission -> storage -> retrieval). Run against real services or realistic fakes.

Prefer unit tests for logic, integration tests for wiring, pipeline tests for proof obligations.

### Mocks should reflect real behavior

A mock that always returns success masks bugs. Mocks should model the real service's behavior including failure modes.

**Good**: Mock memory client that returns `(False, "not connected", 0.0, 0.0)` when unavailable
**Bad**: Mock that always returns `(True, "", 0.5, 0.7)` regardless of input

Test the failure paths too -- what happens when the memory service is down, when embedding generation fails, when the LLM returns garbage?

## Organization

### File structure

Each service has its own test directory: `src/services/<service>/tests/`

Test files are organized by concern, not by source file:

| Pattern | When to use |
|---------|-------------|
| `test_<feature>.py` | Tests for a specific feature (e.g., `test_bootstrapping.py`) |
| `test_<concern>.py` | Tests for a cross-cutting concern (e.g., `test_decision_strategy.py`) |

### Naming

Test functions: `test_<what_it_verifies>`

Be specific enough that the name communicates the behavior:

- `test_alpha_beta_fractional_magnitude` -- clear
- `test_update` -- too vague

### Dependencies

Test dependencies go in `[project.optional-dependencies] dev`, not main `dependencies` (see `docs/CONVENTIONS.md`).

## Test Database Setup

Tests use an isolated `gladys_test` database to prevent destructive operations against your development data.

**Automatic setup** (recommended):
```bash
make setup  # Creates gladys_test database automatically
```

**Manual setup**:
```bash
psql -U postgres -c "CREATE DATABASE gladys_test OWNER gladys;"
```

**Environment variable**:
Tests use `TEST_DB_URL` from your `.env` file:

```bash
# In .env
TEST_DB_URL=postgresql://gladys:gladys_dev@localhost:5432/gladys_test
```

**Why this matters**: Test fixtures delete data from tables. Running tests without `TEST_DB_URL` against your dev database (`gladys`) would wipe your local development data.

**Default behavior**: If `TEST_DB_URL` is not set, database tests default to `gladys_test` database to prevent accidental data loss.

## Patterns

### Async tests

Use `pytest-asyncio`. Services use `asyncio_mode = "auto"` in `pyproject.toml`.

```python
@pytest.mark.asyncio
async def test_something():
    result = await some_async_function()
    assert result == expected
```

### Mock clients

```python
from unittest.mock import AsyncMock, MagicMock

# Mock a gRPC client
mock_memory = MagicMock()
mock_memory.generate_embedding = AsyncMock(return_value=embedding_bytes)
mock_memory.update_heuristic_confidence_weighted = AsyncMock(
    return_value=(True, "", 0.3, 0.6)
)
mock_memory._available = True
```

### Deterministic embeddings

For tests that compare embeddings, create deterministic test vectors:

```python
import struct

def make_embedding(values: list[float]) -> bytes:
    """Create 384-dim embedding bytes from a short list (pads with zeros)."""
    padded = (values + [0.0] * 384)[:384]
    return struct.pack(f'{384}f', *padded)
```

### Pinning randomness

When testing code that uses `random.shuffle` or similar:

```python
from unittest.mock import patch

with patch("module.random.shuffle", side_effect=lambda items: items.reverse()):
    result = function_under_test()
```

## Coverage Expectations

Coverage is proportional to the component's role in the current proof obligations (see `docs/design/ITERATIVE_DESIGN.md`).

| Component | Current Phase role | Coverage expectation |
|-----------|-----------------|---------------------|
| Memory storage (confidence, heuristics) | Core data integrity | High -- every update path tested |
| Orchestrator routing (candidates, events) | Pipeline plumbing | High -- data must arrive intact |
| Executive decision strategy | Experimental logic | Medium-high -- decision paths tested, prompt details lighter |
| Dashboard | Dev observation tool | Medium -- routing and data display, not pixel-perfect rendering |
| Salience (Rust) | Heuristic matching | Medium -- matching correctness, cache behavior |
| Sensors | Data sources | Per-sensor -- protocol compliance, not application logic |

This table updates as proof obligations shift Between phases.
