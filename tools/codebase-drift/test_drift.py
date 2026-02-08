import pytest
from pathlib import Path
from drift_check import DriftChecker


@pytest.fixture
def temp_root(tmp_path):
    """Creates a mock root directory with a minimal GLADyS structure."""
    root = tmp_path / "gladys"
    root.mkdir()
    (root / "src" / "services").mkdir(parents=True)
    return root


def test_detects_stale_path(temp_root):
    """Map references a directory that doesn't exist."""
    (temp_root / "CONCEPT_MAP.md").write_text(
        "| Module | Role |\n|---|---|\n| `src/services/ghost/` | Does not exist |"
    )
    checker = DriftChecker(temp_root)
    assert checker.run() == 1
    assert any("src/services/ghost/" in i for i in checker.issues)


def test_detects_unmapped_service(temp_root):
    """Service directory exists but isn't in the map."""
    (temp_root / "CONCEPT_MAP.md").write_text("No paths here.")
    (temp_root / "src" / "services" / "mystery").mkdir(parents=True)

    checker = DriftChecker(temp_root)
    assert checker.run() == 1
    assert any("mystery" in i for i in checker.issues)


def test_clean_run(temp_root):
    """All mapped paths exist, no unmapped services."""
    (temp_root / "src" / "services" / "memory").mkdir(parents=True)
    (temp_root / "CONCEPT_MAP.md").write_text(
        "| Module | Role |\n|---|---|\n| `src/services/memory/` | Storage |"
    )
    checker = DriftChecker(temp_root)
    assert checker.run() == 0


def test_ignores_non_path_backticks(temp_root):
    """Backtick text that isn't a directory path (no trailing /) is ignored."""
    (temp_root / "CONCEPT_MAP.md").write_text(
        "Run `codebase-info rpcs` for live data. See `docs/INDEX.md` for links."
    )
    checker = DriftChecker(temp_root)
    assert checker.run() == 0


def test_checks_multiple_path_types(temp_root):
    """Paths from different sections are all validated."""
    (temp_root / "src" / "services" / "orchestrator").mkdir(parents=True)
    (temp_root / "proto").mkdir()
    (temp_root / "cli").mkdir()

    (temp_root / "CONCEPT_MAP.md").write_text(
        "| `src/services/orchestrator/` | routing |\n"
        "| `proto/` | contracts |\n"
        "| `cli/` | scripts |\n"
        "| `sdk/missing/` | gone |\n"
    )
    checker = DriftChecker(temp_root)
    assert checker.run() == 1
    assert any("sdk/missing/" in i for i in checker.issues)
    assert len(checker.issues) == 1  # only the missing path, not the existing ones
