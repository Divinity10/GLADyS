#!/usr/bin/env python3
"""Proto Sync Script - Regenerate all gRPC stubs from proto files.

Usage:
    python scripts/proto_sync.py [--check]

This script:
1. Regenerates Python stubs from all .proto files
2. Fixes the import issue (absolute -> relative imports)
3. Verifies the generated files are valid Python
4. Validates Rust proto compilation (via cargo check)

Options:
    --check     Only verify sync status, don't regenerate

Proto locations:
- src/memory/proto/memory.proto -> src/memory/python/gladys_memory/
- src/memory/proto/memory.proto -> src/memory/rust/src/ (via build.rs)
- src/orchestrator/proto/*.proto -> src/orchestrator/gladys_orchestrator/generated/

IMPORTANT: Always run this script after modifying any .proto file to ensure
both Python and Rust implementations are in sync.

Requires grpc_tools. Install with: pip install grpcio-tools
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent


def find_python_with_grpc() -> str:
    """Find a Python interpreter that has grpc_tools installed."""
    # Try common venv locations first
    venv_pythons = [
        ROOT / "src" / "memory" / "python" / ".venv" / "Scripts" / "python.exe",  # Windows
        ROOT / "src" / "memory" / "python" / ".venv" / "bin" / "python",  # Unix
        ROOT / "src" / "orchestrator" / ".venv" / "Scripts" / "python.exe",  # Windows
        ROOT / "src" / "orchestrator" / ".venv" / "bin" / "python",  # Unix
    ]

    for python in venv_pythons:
        if python.exists():
            # Check if grpc_tools is available
            result = subprocess.run(
                [str(python), "-c", "import grpc_tools.protoc"],
                capture_output=True,
            )
            if result.returncode == 0:
                return str(python)

    # Fall back to system Python
    return sys.executable

# Proto configurations: (proto_dir, output_dir, proto_files)
# NOTE: All configs ALWAYS get import fixes applied - grpc_tools generates
# absolute imports (import X_pb2) but we need relative (from . import X_pb2)
# for proper package structure. Never disable this.
PROTO_CONFIGS = [
    {
        "name": "memory",
        "proto_dir": ROOT / "src" / "memory" / "proto",
        "output_dir": ROOT / "src" / "memory" / "python" / "gladys_memory",
        "protos": ["memory.proto"],
    },
    {
        "name": "orchestrator",
        "proto_dir": ROOT / "src" / "orchestrator" / "proto",
        "output_dir": ROOT / "src" / "orchestrator" / "gladys_orchestrator" / "generated",
        "protos": ["common.proto", "memory.proto", "orchestrator.proto", "executive.proto"],
    },
]


def run_protoc(proto_dir: Path, output_dir: Path, proto_file: str, python: str) -> bool:
    """Run grpc_tools.protoc for a single proto file."""
    cmd = [
        python, "-m", "grpc_tools.protoc",
        f"-I{proto_dir}",
        f"--python_out={output_dir}",
        f"--grpc_python_out={output_dir}",
        str(proto_dir / proto_file),
    ]

    print(f"  Generating {proto_file}...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"    ERROR: {result.stderr}")
        return False

    return True


def fix_relative_imports(output_dir: Path, proto_name: str) -> None:
    """Fix absolute imports to relative imports in generated files.

    grpc_tools generates:
        import foo_pb2 as foo__pb2

    We need:
        from . import foo_pb2 as foo__pb2

    This applies to BOTH _pb2.py AND _pb2_grpc.py files.
    """
    base_name = proto_name.replace(".proto", "")

    # Fix both _pb2.py and _pb2_grpc.py files
    for suffix in ["_pb2.py", "_pb2_grpc.py"]:
        gen_file = output_dir / f"{base_name}{suffix}"

        if not gen_file.exists():
            continue

        content = gen_file.read_text()

        # Pattern: import X_pb2 as X__pb2
        # Replace with: from . import X_pb2 as X__pb2
        pattern = r'^import (\w+_pb2) as (\w+__pb2)$'
        replacement = r'from . import \1 as \2'

        new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

        if new_content != content:
            gen_file.write_text(new_content)
            print(f"    Fixed imports in {gen_file.name}")


def verify_python_syntax(file_path: Path) -> bool:
    """Verify a Python file has valid syntax."""
    try:
        with open(file_path, "r") as f:
            compile(f.read(), file_path, "exec")
        return True
    except SyntaxError as e:
        print(f"    SYNTAX ERROR in {file_path.name}: {e}")
        return False


def check_rust_builds(rust_dir: Path) -> bool:
    """Verify Rust code compiles with current proto."""
    print("\n[Rust Proto Check]")
    print(f"  Checking: {rust_dir}")

    if not rust_dir.exists():
        print("  SKIP: Rust directory not found")
        return True

    # Run cargo check
    result = subprocess.run(
        ["cargo", "check"],
        cwd=rust_dir,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("  ERROR: Rust proto compilation failed!")
        print("  This usually means the Rust code is out of sync with proto changes.")
        print("  Review the error and update Rust code to match the proto schema.")
        if result.stderr:
            # Show first few lines of error
            lines = result.stderr.strip().split("\n")[:10]
            for line in lines:
                print(f"    {line}")
        return False

    print("  OK: Rust code compiles successfully")
    return True


def check_proto_consistency() -> tuple[bool, list[str]]:
    """Check that proto files are consistent across locations.

    Returns (success, list of issues found)
    """
    issues = []

    # Check that orchestrator's memory.proto matches memory's memory.proto
    memory_proto = ROOT / "src" / "memory" / "proto" / "memory.proto"
    orch_memory_proto = ROOT / "src" / "orchestrator" / "proto" / "memory.proto"

    if memory_proto.exists() and orch_memory_proto.exists():
        mem_content = memory_proto.read_text()
        orch_content = orch_memory_proto.read_text()
        if mem_content != orch_content:
            issues.append(
                "memory.proto differs between memory/ and orchestrator/. "
                "Copy the canonical version from src/memory/proto/ to src/orchestrator/proto/"
            )

    return len(issues) == 0, issues


def sync_protos(check_only: bool = False) -> int:
    """Synchronize all proto files."""
    print("=" * 60)
    if check_only:
        print("Proto Sync - Checking synchronization status")
    else:
        print("Proto Sync - Regenerating gRPC stubs")
    print("=" * 60)

    # Find Python with grpc_tools
    python = find_python_with_grpc()
    print(f"\nUsing Python: {python}")

    errors = 0

    for config in PROTO_CONFIGS:
        name = config["name"]
        proto_dir = config["proto_dir"]
        output_dir = config["output_dir"]
        protos = config["protos"]

        print(f"\n[{name}]")
        print(f"  Proto dir: {proto_dir}")
        print(f"  Output dir: {output_dir}")

        if not proto_dir.exists():
            print(f"  SKIP: Proto directory not found")
            continue

        if not check_only:
            output_dir.mkdir(parents=True, exist_ok=True)

        for proto in protos:
            proto_path = proto_dir / proto
            if not proto_path.exists():
                print(f"  SKIP: {proto} not found")
                continue

            if not check_only:
                if not run_protoc(proto_dir, output_dir, proto, python):
                    errors += 1
                    continue

                # ALWAYS fix imports - grpc_tools generates broken absolute imports
                fix_relative_imports(output_dir, proto)

            # Verify generated files exist and are valid
            base_name = proto.replace(".proto", "")
            for suffix in ["_pb2.py", "_pb2_grpc.py"]:
                gen_file = output_dir / f"{base_name}{suffix}"
                if gen_file.exists():
                    if not verify_python_syntax(gen_file):
                        errors += 1
                elif check_only:
                    print(f"  MISSING: {gen_file.name} - run without --check to generate")
                    errors += 1

    # Check proto consistency across locations
    print("\n[Proto Consistency Check]")
    consistent, issues = check_proto_consistency()
    if not consistent:
        for issue in issues:
            print(f"  WARNING: {issue}")
        errors += len(issues)
    else:
        print("  OK: Proto files are consistent across locations")

    # Check Rust compilation
    rust_dir = ROOT / "src" / "memory" / "rust"
    if not check_rust_builds(rust_dir):
        errors += 1

    print("\n" + "=" * 60)
    if errors == 0:
        print("SUCCESS: All protos synced successfully")
    else:
        print(f"FAILED: {errors} errors occurred")
        print("\nTo fix proto sync issues:")
        print("1. Ensure proto files are identical across locations")
        print("2. Run: python scripts/proto_sync.py")
        print("3. Update Rust code to match any proto schema changes")
        print("4. Run: cargo check in src/memory/rust/")
    print("=" * 60)

    return errors


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync proto files")
    parser.add_argument("--check", action="store_true", help="Only check, don't regenerate")
    args = parser.parse_args()

    sys.exit(sync_protos(check_only=args.check))
