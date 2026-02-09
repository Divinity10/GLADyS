# Agent Tools Reference

Tools and commands available in the GLADyS development environment. Include the relevant subset in prompts so agents use the right tools for the job.

---

## Platform

- **OS**: Windows 11
- **Shell**: PowerShell 7+ (`&&` chaining works)
- **Line endings**: LF (not CRLF) -- enforced by `.editorconfig`
- **Encoding**: UTF-8 without BOM

---

## Code Search: ripgrep (`rg`)

**Always prefer `rg` over `Select-String`, `grep`, or `findstr`.** It is faster by orders of magnitude on this codebase.

### Common patterns

```powershell
# Search all files (excluding generated/vendored)
rg -n "pattern" --glob "!node_modules" --glob "!*_pb2*" --glob "!build" --glob "!*.pyc"

# Search specific file types
rg -n "pattern" --type py
rg -n "pattern" --type rust
rg -n "pattern" --type java
rg -n "pattern" --type ts

# Search specific file type with exclusions
rg -n "pattern" --type py --glob "!*_pb2*.py"

# Case-insensitive
rg -ni "pattern"

# Files matching only (no line content)
rg -l "pattern"

# Count matches per file
rg -c "pattern"

# Context lines (3 before/after)
rg -n -C 3 "pattern"
```

### Standard exclusion set for blast-radius searches

Generated files, vendored deps, and build artifacts should always be excluded when searching for stale references:

```powershell
rg -n "pattern" --glob "!*_pb2*.py" --glob "!node_modules" --glob "!build" --glob "!*.pyc" --glob "!target"
```

---

## Codebase Reference: `codebase-info`

Generates live data from source files. Prefer this over reading static docs.

```powershell
uv run codebase-info rpcs      # gRPC service/RPC tables (from proto/*.proto)
uv run codebase-info ports     # Port assignments, local + Docker
uv run codebase-info schema    # Database table summaries (from migrations)
uv run codebase-info tree      # Annotated directory tree
uv run codebase-info routers   # Dashboard + API router inventory
uv run codebase-info all       # All of the above
```

**When to use**: Before writing cross-service code, checking proto contracts, or verifying DB schema.

---

## Documentation Search: `docsearch`

Searches indexed documentation (ADRs, design docs, codebase docs). Not for source code.

```powershell
uv run docsearch "query"           # Search docs
uv run docsearch --audit           # Validate doc anchors and links
```

**When to use**: Finding design decisions, ADR references, or architectural context. **Not** for finding code patterns -- use `rg` for that.

---

## Language-Specific Tools

### Python (services)

Each Python service has its own venv. Run commands from the service directory.

```powershell
# Run tests for a specific service
cd src/services/memory ; uv run python -m pytest tests/ -x -q

# Run all Python tests via Make
make test

# Regenerate Python proto stubs
uv run cli/proto_gen.py
```

**Services**: `src/services/memory/`, `src/services/executive/`, `src/services/orchestrator/`, `src/services/dashboard/`, `src/services/salience/` (Rust)

### Java (SDK)

```powershell
cd sdk/java/gladys-sensor-sdk

# Build (includes proto generation)
.\gradlew build

# Run tests only
.\gradlew test
```

### TypeScript (SDK)

```powershell
cd sdk/js/gladys-sensor-sdk

# Install dependencies
npm install

# Generate proto stubs
npm run proto:generate

# Run tests
npm test
```

### Rust (salience service)

```powershell
cd src/services/salience

# Check compilation (no tests)
cargo check

# Build
cargo build

# Run tests
cargo test
```

---

## Make Targets

From the project root:

```powershell
make test       # Run all Python service tests
make start      # Start all services
make stop       # Stop all services
make setup      # Install deps, generate stubs
```

---

## Proto Stub Generation

After changing `.proto` files, regenerate stubs for each language:

| Language | Command | Run from |
|----------|---------|----------|
| Python | `uv run cli/proto_gen.py` | Project root |
| Rust | `cargo build` | `src/services/salience/` |
| Java | `.\gradlew build` | `sdk/java/gladys-sensor-sdk/` |
| TypeScript | `npm run proto:generate` | `sdk/js/gladys-sensor-sdk/` |

---

## Encoding Fix: `fix_encoding.py`

Strips BOM and converts CRLF to LF. **Run after editing files** to ensure compliance with project encoding rules.

```powershell
# Fix specific files
python cli/fix_encoding.py path/to/file1.py path/to/file2.py

# Fix all modified (unstaged + untracked) files
python cli/fix_encoding.py --modified

# Fix all staged files (before commit)
python cli/fix_encoding.py --staged
```

**When to use**: After creating or editing files, before committing. Especially important if your editor/tool writes BOM or CRLF by default.

---

## Quick Reference: Which Tool When

| Task | Tool | Not this |
|------|------|----------|
| Find code patterns | `rg` | `Select-String`, `grep`, `findstr` |
| Find files by name | `Get-ChildItem -Filter` or `rg --files` | `find` |
| Live codebase data | `codebase-info` | Reading static docs |
| Search documentation | `docsearch` | `rg` in `docs/` |
| Run Python tests | `uv run python -m pytest` (from service dir) | `pytest` (wrong venv) |
