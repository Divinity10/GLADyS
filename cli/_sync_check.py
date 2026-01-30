"""Environment sync checking for GLADyS services.

Checks for drift between:
- Proto files in memory/proto vs orchestrator/proto
- Generated stubs vs source protos
- Applied migrations vs migration files
"""

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from _gladys import ROOT, LOCAL_PORTS, DOCKER_PORTS


@dataclass
class SyncIssue:
    """Represents a sync issue found."""
    category: str  # "proto", "stub", "migration"
    severity: str  # "error", "warning"
    message: str
    action: Optional[str] = None


def file_hash(path: Path) -> str:
    """Calculate MD5 hash of a file."""
    if not path.exists():
        return "MISSING"
    return hashlib.md5(path.read_bytes()).hexdigest()[:12]


def check_proto_sync() -> Tuple[List[SyncIssue], List[str]]:
    """Check if proto files are in sync between locations.

    Returns:
        Tuple of (issues, success_messages)
    """
    issues = []
    successes = []

    # Canonical source is memory/proto
    memory_proto = ROOT / "src" / "memory" / "proto"
    orchestrator_proto = ROOT / "src" / "orchestrator" / "proto"

    if not memory_proto.exists():
        issues.append(SyncIssue(
            "proto", "error",
            f"Canonical proto dir not found: {memory_proto}"
        ))
        return issues, successes

    if not orchestrator_proto.exists():
        issues.append(SyncIssue(
            "proto", "error",
            f"Orchestrator proto dir not found: {orchestrator_proto}"
        ))
        return issues, successes

    # Check each proto file
    for proto_file in memory_proto.glob("*.proto"):
        name = proto_file.name
        orch_file = orchestrator_proto / name

        mem_hash = file_hash(proto_file)
        orch_hash = file_hash(orch_file)

        if orch_hash == "MISSING":
            issues.append(SyncIssue(
                "proto", "error",
                f"{name}: Missing from orchestrator/proto",
                action="Run: python cli/proto_gen.py"
            ))
        elif mem_hash != orch_hash:
            issues.append(SyncIssue(
                "proto", "error",
                f"{name}: OUT OF SYNC\n"
                f"     - memory/proto: {mem_hash}\n"
                f"     - orchestrator/proto: {orch_hash} (stale)",
                action="Run: python cli/proto_gen.py"
            ))
        else:
            successes.append(f"{name}: in sync ({mem_hash})")

    return issues, successes


def check_stub_freshness() -> Tuple[List[SyncIssue], List[str]]:
    """Check if generated stubs are newer than source protos.

    Returns:
        Tuple of (issues, success_messages)
    """
    issues = []
    successes = []

    # Check memory-python stubs
    memory_proto = ROOT / "src" / "memory" / "proto"
    memory_stubs = ROOT / "src" / "memory" / "python" / "gladys_memory"

    # Check orchestrator stubs
    orch_proto = ROOT / "src" / "orchestrator" / "proto"
    orch_stubs = ROOT / "src" / "orchestrator" / "gladys_orchestrator" / "generated"

    stub_locations = [
        ("memory-python", memory_proto, memory_stubs, "_pb2.py"),
        ("orchestrator", orch_proto, orch_stubs, "_pb2.py"),
    ]

    for service, proto_dir, stub_dir, suffix in stub_locations:
        if not proto_dir.exists() or not stub_dir.exists():
            continue

        for proto_file in proto_dir.glob("*.proto"):
            base_name = proto_file.stem
            stub_file = stub_dir / f"{base_name}{suffix}"

            if not stub_file.exists():
                issues.append(SyncIssue(
                    "stub", "warning",
                    f"{service}: {base_name}{suffix} not found",
                    action="Regenerate stubs with proto_sync.py"
                ))
                continue

            proto_mtime = proto_file.stat().st_mtime
            stub_mtime = stub_file.stat().st_mtime

            if proto_mtime > stub_mtime:
                issues.append(SyncIssue(
                    "stub", "warning",
                    f"{service}: {base_name}{suffix} may be stale (proto newer than stub)",
                    action="Run: python cli/proto_gen.py"
                ))
            else:
                successes.append(f"{service}/{base_name}{suffix}: up to date")

    return issues, successes


def count_migrations_in_db(port: int) -> Optional[int]:
    """Count migrations by looking at schema state.

    Note: This is a heuristic - we check if certain tables/columns exist
    that are added in specific migrations.
    """
    env = os.environ.copy()
    env["PGPASSWORD"] = "gladys"

    # Try to count by checking which migration markers exist
    # For simplicity, just check if db is reachable and return file count as baseline
    result = subprocess.run(
        ["psql", "-h", "localhost", "-p", str(port),
         "-U", "gladys", "-d", "gladys", "-c", "SELECT 1"],
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        return None

    # Count by checking specific markers from migrations
    # Migration 008 adds heuristic_fires table
    result = subprocess.run(
        ["psql", "-h", "localhost", "-p", str(port),
         "-U", "gladys", "-d", "gladys", "-t", "-c",
         "SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN ('heuristics', 'episodic_events', 'heuristic_fires')"],
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode == 0:
        try:
            return int(result.stdout.strip())
        except ValueError:
            pass

    return None


def count_migration_files() -> int:
    """Count migration .sql files."""
    migrations_dir = ROOT / "src" / "memory" / "migrations"
    if not migrations_dir.exists():
        return 0
    return len(list(f for f in migrations_dir.glob("*.sql") if not f.name.endswith(".bak")))


def check_migrations(local_port: int = LOCAL_PORTS.db, docker_port: int = DOCKER_PORTS.db) -> Tuple[List[SyncIssue], List[str]]:
    """Check migration status.

    Returns:
        Tuple of (issues, success_messages)
    """
    issues = []
    successes = []

    file_count = count_migration_files()

    # Check local DB
    local_tables = count_migrations_in_db(local_port)
    if local_tables is not None:
        # We expect 3 core tables if all migrations applied
        if local_tables >= 3:
            successes.append(f"Local DB (port {local_port}): {local_tables} core tables present")
        else:
            issues.append(SyncIssue(
                "migration", "warning",
                f"Local DB: Only {local_tables}/3 core tables present",
                action="Run: python cli/local.py migrate"
            ))
    else:
        issues.append(SyncIssue(
            "migration", "warning",
            f"Local DB (port {local_port}): Not reachable"
        ))

    # Check Docker DB
    docker_tables = count_migrations_in_db(docker_port)
    if docker_tables is not None:
        if docker_tables >= 3:
            successes.append(f"Docker DB (port {docker_port}): {docker_tables} core tables present")
        else:
            issues.append(SyncIssue(
                "migration", "warning",
                f"Docker DB: Only {docker_tables}/3 core tables present",
                action="Run: python cli/docker.py migrate"
            ))
    else:
        # Docker DB not running is not necessarily an error
        successes.append(f"Docker DB (port {docker_port}): Not running (OK if not using Docker)")

    successes.append(f"Migration files: {file_count}")

    return issues, successes


def run_sync_check(verbose: bool = True) -> int:
    """Run all sync checks and report results.

    Returns:
        Exit code (0 = all good, 1 = issues found)
    """
    print("=" * 60)
    print("GLADyS Environment Sync Check")
    print("=" * 60)

    all_issues = []
    all_successes = []

    # Proto files
    print("\nProto Files:")
    issues, successes = check_proto_sync()
    all_issues.extend(issues)
    all_successes.extend(successes)

    for s in successes:
        print(f"  [OK] {s}")
    for i in issues:
        icon = "[X]" if i.severity == "error" else "[!]"
        print(f"  {icon} {i.message}")

    # Generated stubs
    print("\nGenerated Stubs:")
    issues, successes = check_stub_freshness()
    all_issues.extend(issues)
    all_successes.extend(successes)

    for s in successes:
        print(f"  [OK] {s}")
    for i in issues:
        icon = "[X]" if i.severity == "error" else "[!]"
        print(f"  {icon} {i.message}")

    # Migrations
    print("\nMigrations:")
    issues, successes = check_migrations()
    all_issues.extend(issues)
    all_successes.extend(successes)

    for s in successes:
        print(f"  [OK] {s}")
    for i in issues:
        icon = "[X]" if i.severity == "error" else "[!]"
        print(f"  {icon} {i.message}")

    # Summary
    errors = [i for i in all_issues if i.severity == "error"]
    warnings = [i for i in all_issues if i.severity == "warning"]

    print("\n" + "=" * 60)
    if not all_issues:
        print("[OK] All checks passed - environment is in sync!")
        return 0
    else:
        print(f"Found {len(errors)} error(s), {len(warnings)} warning(s)")

        # Collect unique actions
        actions = set()
        for i in all_issues:
            if i.action:
                actions.add(i.action)

        if actions:
            print("\nRecommended actions:")
            for a in sorted(actions):
                print(f"  - {a}")

        return 1 if errors else 0


if __name__ == "__main__":
    import sys
    sys.exit(run_sync_check())
