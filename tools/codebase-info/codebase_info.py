"""Generate live codebase reference data from source files.

Subcommands:
    rpcs     - gRPC service/RPC tables from proto files
    ports    - Port assignments (local + Docker)
    schema   - Database table summaries from migrations
    tree     - Annotated directory tree
    routers  - Dashboard + API router inventory
    all      - All of the above
"""

import ast
import re
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple


def find_root() -> Path:
    """Walk up from this file to find the repo root (contains CLAUDE.md)."""
    p = Path(__file__).resolve().parent
    for _ in range(5):
        if (p / "CLAUDE.md").exists():
            return p
        p = p.parent
    print("ERROR: Could not find repo root (no CLAUDE.md found)", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# rpcs
# ---------------------------------------------------------------------------

# Map proto service names to their implementation paths
SERVICE_IMPL = {
    "MemoryStorage": "src/services/memory/ (Python)",
    "SalienceGateway": "src/services/salience/ (Rust)",
    "OrchestratorService": "src/services/orchestrator/ (Python)",
    "ExecutiveService": "src/services/executive/ (Python)",
}


def cmd_rpcs(root: Path) -> str:
    """Parse proto files and generate service/RPC tables."""
    proto_dir = root / "proto"
    lines = ["# gRPC Services and RPCs", ""]
    lines.append("Generated from `proto/*.proto`")
    lines.append("")

    proto_files = sorted(proto_dir.glob("*.proto"))
    for pf in proto_files:
        content = pf.read_text(encoding="utf-8")
        services = _parse_proto_services(content)
        if not services:
            continue

        for svc_name, rpcs in services:
            impl = SERVICE_IMPL.get(svc_name, "unknown")
            lines.append(f"## `{svc_name}` ({pf.name})")
            lines.append(f"**Implemented by**: `{impl}`")
            lines.append("")
            lines.append("| RPC | Purpose |")
            lines.append("|-----|---------|")
            for rpc_name, purpose in rpcs:
                lines.append(f"| {rpc_name} | {purpose} |")
            lines.append("")

    return "\n".join(lines)


def _parse_proto_services(content: str) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """Extract services and their RPCs with preceding comments."""
    results = []
    # Find each service block
    for svc_match in re.finditer(r"service\s+(\w+)\s*\{", content):
        svc_name = svc_match.group(1)
        start = svc_match.end()
        # Find matching closing brace (simple: count braces)
        depth = 1
        pos = start
        while pos < len(content) and depth > 0:
            if content[pos] == "{":
                depth += 1
            elif content[pos] == "}":
                depth -= 1
            pos += 1
        svc_body = content[start:pos - 1]

        rpcs = []
        # For each rpc, capture preceding comment lines
        for rpc_match in re.finditer(r"rpc\s+(\w+)\s*\(", svc_body):
            rpc_name = rpc_match.group(1)
            # Look backwards from the rpc for comment lines
            before = svc_body[:rpc_match.start()].rstrip()
            comment_lines = []
            for line in reversed(before.split("\n")):
                stripped = line.strip()
                if stripped.startswith("//"):
                    text = stripped.lstrip("/").strip()
                    # Stop at section dividers (--- Name ---, ====, ----)
                    if not text or re.match(r"^[-=]+$", text):
                        break
                    if re.match(r"^---\s+.+\s+---$", text):
                        break
                    comment_lines.insert(0, text)
                elif stripped == "":
                    # Blank line: stop if we already have comments (section boundary)
                    if comment_lines:
                        break
                    continue
                else:
                    break
            purpose = " ".join(comment_lines) if comment_lines else rpc_name
            rpcs.append((rpc_name, purpose))

        results.append((svc_name, rpcs))
    return results


# ---------------------------------------------------------------------------
# ports
# ---------------------------------------------------------------------------

def cmd_ports(root: Path) -> str:
    """Parse port configurations from CLI and docker-compose."""
    lines = ["# Port Reference", ""]

    # Parse CLI port config
    cli_path = root / "cli" / "_gladys.py"
    local_ports, docker_ports, descriptions = _parse_cli_ports(cli_path)

    # Parse docker-compose for verification
    docker_path = root / "docker" / "docker-compose.yml"
    docker_compose_ports = _parse_docker_compose_ports(docker_path)

    lines.append("| Service | Local | Docker | Description |")
    lines.append("|---------|-------|--------|-------------|")

    all_services = sorted(set(list(local_ports.keys()) + list(docker_ports.keys())))
    for svc in all_services:
        local = local_ports.get(svc, "---")
        docker = docker_ports.get(svc, "---")
        # Descriptions use hyphens (memory-python), PortConfig uses underscores
        desc = descriptions.get(svc, "") or descriptions.get(svc.replace("_", "-"), "")
        lines.append(f"| {svc} | {local} | {docker} | {desc} |")

    # Note any docker-compose ports not in CLI
    if docker_compose_ports:
        lines.append("")
        lines.append("Docker Compose port mappings (host:container):")
        for svc_name, mapping in sorted(docker_compose_ports.items()):
            lines.append(f"  {svc_name}: {mapping}")

    lines.append("")
    lines.append("Sources: `cli/_gladys.py`, `docker/docker-compose.yml`")
    return "\n".join(lines)


def _parse_cli_ports(path: Path) -> Tuple[Dict, Dict, Dict]:
    """Parse LOCAL_PORTS, DOCKER_PORTS, SERVICE_DESCRIPTIONS from _gladys.py using AST."""
    content = path.read_text(encoding="utf-8")
    tree = ast.parse(content)
    local = {}
    docker = {}
    descriptions = {}

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            name = target.id

            if name in ("LOCAL_PORTS", "DOCKER_PORTS"):
                dest = local if name == "LOCAL_PORTS" else docker
                # PortConfig(...) call
                if isinstance(node.value, ast.Call):
                    for kw in node.value.keywords:
                        val = _ast_extract_int(kw.value)
                        if val is not None:
                            dest[kw.arg] = str(val)

            elif name == "SERVICE_DESCRIPTIONS":
                # Dict literal
                if isinstance(node.value, ast.Dict):
                    for k, v in zip(node.value.keys, node.value.values):
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                            descriptions[k.value] = v.value

    return local, docker, descriptions


def _ast_extract_int(node: ast.AST) -> int | None:
    """Extract an integer value from an AST node, handling int() and os.environ.get() wrappers."""
    # Plain integer literal
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value

    # int(...) call — extract the inner value
    if isinstance(node, ast.Call):
        # int(os.environ.get("X", default)) — get the default arg
        if node.args:
            inner = node.args[0]
            if isinstance(inner, ast.Call) and node.args:
                # os.environ.get("X", default) — second arg is the default
                if len(inner.args) >= 2:
                    return _ast_extract_int(inner.args[1])
            return _ast_extract_int(inner)

    return None


def _parse_docker_compose_ports(path: Path) -> Dict[str, str]:
    """Parse port mappings from docker-compose.yml."""
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8")
    result = {}
    current_service = None

    for line in content.split("\n"):
        # Service name (2-space indent, no further indent)
        svc_match = re.match(r"^  (\w[\w-]*):", line)
        if svc_match and not line.strip().startswith("#"):
            current_service = svc_match.group(1)
        # Port mapping
        port_match = re.match(r'^\s+- "(\d+:\d+)"', line)
        if port_match and current_service:
            mapping = port_match.group(1)
            if current_service in result:
                result[current_service] += f", {mapping}"
            else:
                result[current_service] = mapping

    return result


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

def cmd_schema(root: Path) -> str:
    """Parse database schema from migration files."""
    migrations_dir = root / "src" / "db" / "migrations"
    lines = ["# Database Schema", ""]
    lines.append(f"Consolidated from migrations in `src/db/migrations/`")
    lines.append("")

    if not migrations_dir.exists():
        lines.append("(no migrations directory found)")
        return "\n".join(lines)

    migration_files = sorted(migrations_dir.glob("*.sql"))
    tables: Dict[str, List[Tuple[str, str]]] = {}  # table -> [(col, type)]
    table_comments: Dict[str, str] = {}  # table -> comment from SQL

    for mf in migration_files:
        content = mf.read_text(encoding="utf-8")
        _parse_create_tables(content, tables, table_comments)
        _parse_alter_add_columns(content, tables)

    for table_name in sorted(tables.keys()):
        cols = tables[table_name]
        comment = table_comments.get(table_name, "")
        header = f"## `{table_name}`"
        if comment:
            header += f" -- {comment}"
        lines.append(header)
        lines.append("")
        lines.append("| Column | Type |")
        lines.append("|--------|------|")
        for col_name, col_type in cols:
            lines.append(f"| {col_name} | {col_type} |")
        lines.append("")

    return "\n".join(lines)


def _parse_create_tables(content: str, tables: Dict, comments: Dict):
    """Extract CREATE TABLE definitions."""
    # Match CREATE TABLE with optional IF NOT EXISTS
    for match in re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\);",
        content,
        re.S | re.I,
    ):
        table_name = match.group(1)
        body = match.group(2)

        # Look for comment block before CREATE TABLE
        before = content[:match.start()].rstrip()
        for line in reversed(before.split("\n")):
            stripped = line.strip()
            if stripped.startswith("--") and not stripped.startswith("-- ==="):
                comment_text = stripped.lstrip("-").strip()
                if comment_text:
                    comments[table_name] = comment_text
                    break
            elif stripped == "":
                continue
            else:
                break

        cols = []
        for col_line in body.split("\n"):
            col_line = col_line.strip().rstrip(",")
            if not col_line or col_line.startswith("--"):
                continue
            # Skip constraints, indexes, UNIQUE
            if re.match(r"^(UNIQUE|CHECK|PRIMARY KEY|FOREIGN KEY|CONSTRAINT)\b", col_line, re.I):
                continue
            # Parse column: name TYPE [rest...]
            col_match = re.match(r"(\w+)\s+([\w()]+(?:\(\d+\))?)", col_line)
            if col_match:
                col_name = col_match.group(1)
                col_type = col_match.group(2)
                # Skip SQL keywords that aren't column names
                if col_name.upper() in ("UNIQUE", "CHECK", "CONSTRAINT", "PRIMARY", "FOREIGN"):
                    continue
                cols.append((col_name, col_type))

        if cols:
            tables[table_name] = cols


def _parse_alter_add_columns(content: str, tables: Dict):
    """Extract ALTER TABLE ... ADD COLUMN definitions."""
    for match in re.finditer(
        r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+([\w()]+)",
        content,
        re.I,
    ):
        table_name = match.group(1)
        col_name = match.group(2)
        col_type = match.group(3)
        if table_name not in tables:
            tables[table_name] = []
        # Only add if not already present
        existing = {c[0] for c in tables[table_name]}
        if col_name not in existing:
            tables[table_name].append((col_name, col_type))


# ---------------------------------------------------------------------------
# tree
# ---------------------------------------------------------------------------

# Top-level dirs to include
TREE_ALLOWLIST = [
    "cli", "docker", "docs", "packs", "proto", "sdk", "src", "tests", "tools",
]

# Patterns to skip
TREE_IGNORE = {
    ".git", "__pycache__", ".venv", "node_modules", "generated",
    ".pytest_cache", "uv.lock", ".mypy_cache", "build", "dist",
    "*.egg-info",
}

# Annotations for known paths
TREE_ANNOTATIONS = {
    "cli": "CLI entry points",
    "docker": "Docker Compose configs",
    "docs": "Documentation (ADRs, design docs, guides)",
    "docs/adr": "Architecture Decision Records",
    "docs/design": "Design documents",
    "docs/codebase": "Codebase reference docs",
    "packs": "Skill packs (sensors + domain skills)",
    "proto": "Protocol Buffer definitions",
    "sdk": "Language SDKs (Java, JS/TS)",
    "src": "Source code",
    "src/db": "Database migrations",
    "src/services": "Service implementations",
    "src/services/memory": "Memory Storage (Python)",
    "src/services/salience": "Salience Gateway (Rust)",
    "src/services/orchestrator": "Orchestrator (Python)",
    "src/services/executive": "Executive stub (Python)",
    "src/services/dashboard": "Web Dashboard (FastAPI + htmx)",
    "src/services/fun_api": "JSON API layer",
    "tests": "Integration + cross-service tests",
    "tools": "Dev tools (drift-check, docsearch, codebase-info)",
}


def cmd_tree(root: Path, max_depth: int = 3) -> str:
    """Generate annotated directory tree."""
    lines = ["# Directory Tree", ""]
    lines.append(f"Depth: {max_depth}")
    lines.append("")

    for name in sorted(TREE_ALLOWLIST):
        dir_path = root / name
        if dir_path.is_dir():
            _tree_walk(dir_path, root, lines, depth=0, max_depth=max_depth)
            lines.append("")

    return "\n".join(lines)


def _should_skip(name: str) -> bool:
    """Check if a file/dir should be skipped."""
    if name in TREE_IGNORE:
        return True
    for pattern in TREE_IGNORE:
        if "*" in pattern and name.endswith(pattern.lstrip("*")):
            return True
    return False


def _tree_walk(path: Path, root: Path, lines: List[str], depth: int, max_depth: int):
    """Recursively walk and format directory tree."""
    indent = "  " * depth
    rel = path.relative_to(root).as_posix()
    name = path.name

    if path.is_dir():
        annotation = TREE_ANNOTATIONS.get(rel, "")
        suffix = f"  -- {annotation}" if annotation else ""
        lines.append(f"{indent}{name}/{suffix}")

        if depth < max_depth:
            try:
                children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            except PermissionError:
                return
            for child in children:
                if not _should_skip(child.name):
                    _tree_walk(child, root, lines, depth + 1, max_depth)


# ---------------------------------------------------------------------------
# routers
# ---------------------------------------------------------------------------

ROUTER_DIRS = {
    "Dashboard (HTML)": "src/services/dashboard/backend/routers",
    "Fun API (JSON)": "src/services/fun_api/routers",
}


def cmd_routers(root: Path) -> str:
    """List dashboard and API router files."""
    lines = ["# Router Inventory", ""]

    for label, rel_path in ROUTER_DIRS.items():
        dir_path = root / rel_path
        lines.append(f"## {label}")
        lines.append(f"Path: `{rel_path}/`")
        lines.append("")

        if not dir_path.exists():
            lines.append("(directory not found)")
            lines.append("")
            continue

        py_files = sorted(dir_path.glob("*.py"))
        router_files = [f for f in py_files if f.name != "__init__.py"]

        if not router_files:
            lines.append("(no router files)")
            lines.append("")
            continue

        lines.append("| Router | Endpoints |")
        lines.append("|--------|-----------|")

        for rf in router_files:
            name = rf.stem
            endpoints = _count_endpoints(rf)
            lines.append(f"| {name} | {endpoints} |")

        lines.append("")

    return "\n".join(lines)


def _count_endpoints(path: Path) -> str:
    """Count route decorators in a router file."""
    content = path.read_text(encoding="utf-8")
    gets = len(re.findall(r"@\w+\.get\(", content))
    posts = len(re.findall(r"@\w+\.post\(", content))
    puts = len(re.findall(r"@\w+\.put\(", content))
    deletes = len(re.findall(r"@\w+\.delete\(", content))
    patches = len(re.findall(r"@\w+\.patch\(", content))

    parts = []
    if gets:
        parts.append(f"{gets} GET")
    if posts:
        parts.append(f"{posts} POST")
    if puts:
        parts.append(f"{puts} PUT")
    if deletes:
        parts.append(f"{deletes} DELETE")
    if patches:
        parts.append(f"{patches} PATCH")
    return ", ".join(parts) if parts else "0"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

COMMANDS = {
    "rpcs": cmd_rpcs,
    "ports": cmd_ports,
    "schema": cmd_schema,
    "routers": cmd_routers,
}


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate live codebase reference data from source files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  rpcs      gRPC service/RPC tables from proto files
  ports     Port assignments (local + Docker)
  schema    Database table summaries from migrations
  tree      Annotated directory tree
  routers   Dashboard + API router inventory
  all       All of the above
""",
    )
    parser.add_argument("command", choices=["rpcs", "ports", "schema", "tree", "routers", "all"])
    parser.add_argument("--depth", type=int, default=3, help="Tree depth (default: 3)")

    args = parser.parse_args()
    root = find_root()

    if args.command == "all":
        sections = []
        for cmd_name, cmd_func in COMMANDS.items():
            sections.append(cmd_func(root))
        sections.append(cmd_tree(root, max_depth=args.depth))
        print("\n---\n\n".join(sections))
    elif args.command == "tree":
        print(cmd_tree(root, max_depth=args.depth))
    else:
        print(COMMANDS[args.command](root))


if __name__ == "__main__":
    main()
