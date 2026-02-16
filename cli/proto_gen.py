#!/usr/bin/env python3
"""Proto Generation Script - Regenerate all gRPC stubs from shared proto directory.

Usage:
    python cli/proto_gen.py [--check]

This script:
1. Regenerates Python stubs from proto/*.proto
2. Fixes imports (absolute -> relative)
3. Validates Rust proto compilation

Options:
    --check     Only verify status, don't regenerate

Proto location: proto/ (shared at repository root)
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PROTO_DIR = ROOT / "proto"

# Output configurations: where to generate stubs for each service
STUB_CONFIGS = [
    {
        "name": "memory-python",
        "output_dir": ROOT / "src" / "services" / "memory" / "gladys_memory",
        "protos": ["types.proto", "memory.proto"],
    },
    {
        "name": "orchestrator",
        "output_dir": ROOT / "src" / "services" / "orchestrator" / "gladys_orchestrator" / "generated",
        "protos": ["types.proto", "common.proto", "memory.proto", "orchestrator.proto", "executive.proto"],
    },
]


def find_python_with_grpc() -> str:
    """Find Python with grpc_tools installed."""
    venvs = [
        ROOT / "src" / "services" / "memory" / ".venv" / "Scripts" / "python.exe",
        ROOT / "src" / "services" / "memory" / ".venv" / "bin" / "python",
        ROOT / "src" / "services" / "orchestrator" / ".venv" / "Scripts" / "python.exe",
        ROOT / "src" / "services" / "orchestrator" / ".venv" / "bin" / "python",
    ]
    for python in venvs:
        if python.exists():
            result = subprocess.run([str(python), "-c", "import grpc_tools.protoc"], capture_output=True)
            if result.returncode == 0:
                return str(python)
    return sys.executable


def run_protoc(output_dir: Path, proto_file: str, python: str) -> bool:
    """Run grpc_tools.protoc for a single proto file."""
    cmd = [
        python, "-m", "grpc_tools.protoc",
        f"-I{PROTO_DIR}",
        f"--python_out={output_dir}",
        f"--grpc_python_out={output_dir}",
        str(PROTO_DIR / proto_file),
    ]
    print(f"  Generating {proto_file}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    ERROR: {result.stderr}")
        return False
    return True


def normalize_line_endings(file_path: Path) -> None:
    """Ensure file uses LF line endings (not CRLF)."""
    raw = file_path.read_bytes()
    if b"\r\n" in raw:
        file_path.write_bytes(raw.replace(b"\r\n", b"\n"))


def fix_imports(output_dir: Path, proto_name: str) -> None:
    """Fix absolute imports to relative imports."""
    base_name = proto_name.replace(".proto", "")
    for suffix in ["_pb2.py", "_pb2_grpc.py"]:
        gen_file = output_dir / f"{base_name}{suffix}"
        if not gen_file.exists():
            continue
        content = gen_file.read_text(encoding="utf-8")
        pattern = r'^import (\w+_pb2) as (\w+__pb2)$'
        new_content = re.sub(pattern, r'from . import \1 as \2', content, flags=re.MULTILINE)
        if new_content != content:
            gen_file.write_text(new_content, encoding="utf-8")
            print(f"    Fixed imports in {gen_file.name}")
        normalize_line_endings(gen_file)


def verify_syntax(file_path: Path) -> bool:
    """Verify Python file has valid syntax."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            compile(f.read(), file_path, "exec")
        return True
    except SyntaxError as e:
        print(f"    SYNTAX ERROR in {file_path.name}: {e}")
        return False


def check_rust_builds() -> bool:
    """Verify Rust code compiles with current proto."""
    rust_dir = ROOT / "src" / "services" / "salience"
    print("\n[Rust Proto Check]")
    if not rust_dir.exists():
        print("  SKIP: Rust directory not found")
        return True

    result = subprocess.run(["cargo", "check"], cwd=rust_dir, capture_output=True, text=True)
    if result.returncode != 0:
        print("  ERROR: Rust proto compilation failed!")
        lines = result.stderr.strip().split("\n")[:10]
        for line in lines:
            print(f"    {line}")
        return False
    print("  OK: Rust code compiles")
    return True


def generate_stubs(check_only: bool = False) -> int:
    """Generate all proto stubs."""
    print("=" * 60)
    print("Proto Generation" + (" - CHECK MODE" if check_only else ""))
    print("=" * 60)
    print(f"\nShared proto directory: {PROTO_DIR}")

    if not PROTO_DIR.exists():
        print(f"ERROR: Proto directory not found: {PROTO_DIR}")
        return 1

    python = find_python_with_grpc()
    print(f"Using Python: {python}")

    errors = 0

    for config in STUB_CONFIGS:
        name = config["name"]
        output_dir = config["output_dir"]
        protos = config["protos"]

        print(f"\n[{name}]")
        print(f"  Output: {output_dir}")

        if not check_only:
            output_dir.mkdir(parents=True, exist_ok=True)

        for proto in protos:
            if not (PROTO_DIR / proto).exists():
                print(f"  SKIP: {proto} not found")
                continue

            if not check_only:
                if not run_protoc(output_dir, proto, python):
                    errors += 1
                    continue
                fix_imports(output_dir, proto)

            # Verify generated files
            base_name = proto.replace(".proto", "")
            for suffix in ["_pb2.py", "_pb2_grpc.py"]:
                gen_file = output_dir / f"{base_name}{suffix}"
                if gen_file.exists():
                    if not verify_syntax(gen_file):
                        errors += 1
                elif check_only:
                    print(f"  MISSING: {gen_file.name}")
                    errors += 1

    if not check_rust_builds():
        errors += 1

    print("\n" + "=" * 60)
    if errors == 0:
        print("SUCCESS: All stubs generated")
    else:
        print(f"FAILED: {errors} errors")
    print("=" * 60)
    return errors


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate proto stubs")
    parser.add_argument("--check", action="store_true", help="Only check, don't regenerate")
    args = parser.parse_args()
    sys.exit(generate_stubs(check_only=args.check))
