# GLADyS Makefile
# Cross-platform targets for common operations

.PHONY: setup init-db proto test help up down restart build benchmark rust-rebuild exec-rebuild verify verify-local dashboard start stop status workspace-create workspace-list workspace-destroy

DASHBOARD_PORT ?= 8502

# Default target
help:
	@echo "GLADyS Development Tasks"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Local Development (preferred):"
	@echo "  setup         Install all Python deps across all services"
	@echo "  init-db       Create gladys user/database and run migrations"
	@echo "  start         Start all local services (memory, orchestrator, executive)"
	@echo "  stop          Stop all local services"
	@echo "  status        Show status of local services"
	@echo "  dashboard     Start the dashboard in foreground (Ctrl+C to stop)"
	@echo "  verify-local  Check local environment (PostgreSQL, pgvector, tables)"
	@echo ""
	@echo "Docker Development:"
	@echo "  verify        Verify Docker environment (containers, gRPC services)"
	@echo "  up            Start Docker services"
	@echo "  down          Stop Docker services"
	@echo "  restart       Restart Docker services"
	@echo "  build         Rebuild all Docker containers"
	@echo "  rust-rebuild  Rebuild Rust container (after Rust code changes)"
	@echo "  exec-rebuild  Rebuild Executive container (after proto changes)"
	@echo ""
	@echo "Common:"
	@echo "  proto         Regenerate all gRPC stubs from .proto files"
	@echo "  test          Run all tests"
	@echo "  benchmark     Run salience benchmark"
	@echo "  help          Show this help"
	@echo ""
	@echo "Workspaces (multi-agent):"
	@echo "  workspace-create NAME=x  Create isolated agent workspace ../GLADys-x/"
	@echo "  workspace-list           Show all workspaces and their configs"
	@echo "  workspace-destroy NAME=x Remove workspace and its database"

# Install all Python dependencies across all services (uv handles Python version via .python-version)
setup:
	uv run cli/setup_dev.py

# Create gladys user/database and run all migrations
init-db:
	uv run cli/init_db.py

# Verify local environment (PostgreSQL, no Docker)
verify-local:
	uv run cli/verify_local.py

# Verify Docker environment
verify:
	uv run cli/verify_env.py

# Regenerate proto stubs
proto:
	uv run cli/proto_gen.py

# Run unit tests across all services
test:
	cd src/services/memory && uv run pytest tests/ -v
	cd src/services/orchestrator && uv run pytest tests/ -v
	cd src/services/executive && uv run pytest tests/ -v
	cd src/services/dashboard && uv run pytest tests/ -v
	cd tests/unit && uv run pytest -v

# Docker operations
up:
	cd docker && docker compose up -d

down:
	cd docker && docker compose down

restart:
	cd docker && docker compose restart

# Rebuild all Docker containers
build:
	cd docker && docker compose build --no-cache

# Rebuild ONLY the Rust container (Python uses volume mounts, doesn't need rebuild)
rust-rebuild:
	cd docker && docker compose up -d --build --force-recreate memory-rust

# Rebuild Executive container (required after proto changes or Dockerfile changes)
exec-rebuild:
	cd docker && docker compose up -d --build --force-recreate executive-stub

# Local service management (init-db is idempotent — safe to run every time)
start: init-db
	uv run cli/local.py start all
	@echo ""
	@echo "Start the dashboard with: make dashboard (http://localhost:$(DASHBOARD_PORT))"

stop:
	uv run cli/local.py stop all

status:
	uv run cli/local.py status

# Start the dashboard (foreground - useful for seeing logs)
dashboard:
	cd src/services/dashboard && uv run uvicorn backend.main:app --host 0.0.0.0 --port $(DASHBOARD_PORT) --reload

# Run benchmark
benchmark:
	cd src/services/orchestrator && uv run python ../../tests/integration/benchmark_salience.py

# Workspace management for multi-agent development
workspace-create:
	uv run cli/workspace.py create $(NAME)

workspace-list:
	uv run cli/workspace.py list

workspace-destroy:
	uv run cli/workspace.py destroy $(NAME)
