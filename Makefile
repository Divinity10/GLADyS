# GLADyS Makefile
# Cross-platform targets for common operations

.PHONY: setup init-db proto test help up down restart build benchmark rust-rebuild exec-rebuild verify verify-local dashboard dashboard-start dashboard-stop start stop status

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
	@echo "  dashboard-start  Start the dashboard in background"
	@echo "  dashboard-stop   Stop the dashboard"
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
	@echo "Start the dashboard with: make dashboard (http://localhost:8502)"

stop:
	uv run cli/local.py stop all

status:
	uv run cli/local.py status

# Start the dashboard (foreground - useful for seeing logs)
dashboard:
	cd src/services/dashboard && uv run uvicorn backend.main:app --host 0.0.0.0 --port 8502 --reload

# Start the dashboard in background
dashboard-start:
	cd cli && uv run python local.py start dashboard

# Stop the dashboard
dashboard-stop:
	cd cli && uv run python local.py stop dashboard

# Run benchmark
benchmark:
	cd src/services/orchestrator && uv run python ../../tests/integration/benchmark_salience.py
