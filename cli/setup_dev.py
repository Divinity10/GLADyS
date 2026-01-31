#!/usr/bin/env python3
"""GLADyS developer environment setup.

Installs all Python dependencies across all services using uv.
Run via: make setup  (or: python cli/setup_dev.py)
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Install order matters: libs first, then services, then CLI/tests.
PACKAGES = [
    ("src/lib/gladys_common", "gladys-common"),
    ("src/lib/gladys_client", "gladys-client"),
    ("src/services/memory", "gladys-memory"),
    ("src/services/orchestrator", "gladys-orchestrator"),
    ("src/services/executive", "gladys-executive"),
    ("src/services/dashboard", "gladys-dashboard"),
    ("cli", "gladys-admin"),
    ("tests/integration", "gladys-integration-tests"),
]


def check_command(name: str, args: list[str] | None = None) -> bool:
    """Check if a command is available on PATH."""
    path = shutil.which(name)
    if not path:
        return False
    if args:
        try:
            subprocess.run([path, *args], capture_output=True, timeout=10)
        except Exception:
            return False
    return True


def check_prerequisites() -> bool:
    """Check required and optional prerequisites. Returns False if required ones missing."""
    ok = True

    # Python version
    v = sys.version_info
    if v < (3, 11):
        print(f"  FAIL  Python 3.11+ required (found {v.major}.{v.minor}.{v.micro})")
        ok = False
    else:
        print(f"  OK    Python {v.major}.{v.minor}.{v.micro}")

    # uv
    if check_command("uv"):
        print("  OK    uv")
    else:
        print("  FAIL  uv not found — install from https://docs.astral.sh/uv/")
        ok = False

    # protoc (required for proto stub generation)
    if check_command("protoc"):
        print("  OK    protoc")
    else:
        print("  FAIL  protoc not found — install protobuf-compiler (apt install protobuf-compiler)")
        ok = False

    # PostgreSQL (required for local dev — all services use it)
    if check_command("psql"):
        print("  OK    psql")
    else:
        print("  FAIL  psql not found — install PostgreSQL (apt install postgresql)")
        ok = False

    # Optional: cargo (only needed if running Rust salience gateway locally)
    if check_command("cargo"):
        print("  OK    cargo (optional — for local Rust salience gateway)")
    else:
        print("  SKIP  cargo not found (optional — Docker mode runs Rust service in container)")

    return ok


def setup_package(rel_path: str, name: str) -> bool:
    """Run uv sync for a single package directory."""
    pkg_dir = REPO_ROOT / rel_path
    if not (pkg_dir / "pyproject.toml").exists():
        print(f"  SKIP  {name} — no pyproject.toml at {rel_path}/")
        return True

    print(f"  ...   {name} ({rel_path}/)")
    result = subprocess.run(
        ["uv", "sync", "--all-extras"],
        cwd=pkg_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        print(f"  FAIL  {name}")
        if result.stderr:
            for line in result.stderr.strip().splitlines()[:10]:
                print(f"        {line}")
        return False

    print(f"  OK    {name}")
    return True


def generate_protos() -> bool:
    """Run proto generation if proto_gen.py exists."""
    proto_gen = REPO_ROOT / "cli" / "proto_gen.py"
    if not proto_gen.exists():
        print("  SKIP  proto_gen.py not found")
        return True

    print("  ...   Generating gRPC stubs")
    result = subprocess.run(
        [sys.executable, str(proto_gen)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print("  FAIL  Proto generation")
        if result.stderr:
            for line in result.stderr.strip().splitlines()[:10]:
                print(f"        {line}")
        return False

    print("  OK    Proto stubs generated")
    return True


def main() -> int:
    print("GLADyS Developer Setup")
    print("=" * 40)

    print("\nPrerequisites:")
    if not check_prerequisites():
        print("\nFix required prerequisites above and re-run.")
        return 1

    print("\nInstalling packages:")
    failures = []
    for rel_path, name in PACKAGES:
        if not setup_package(rel_path, name):
            failures.append(name)

    print("\nProto generation:")
    if not generate_protos():
        failures.append("proto-gen")

    print("\n" + "=" * 40)
    if failures:
        print(f"Done with {len(failures)} failure(s): {', '.join(failures)}")
        return 1

    print("All packages installed successfully.")
    print("\nNext steps:")
    print("  - Start PostgreSQL: sudo systemctl start postgresql")
    print("  - Initialize database: make init-db")
    print("  - Run 'make test' to verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
