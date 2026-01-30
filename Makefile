# GLADyS Makefile
# Cross-platform targets for common operations

.PHONY: setup proto test help up down restart benchmark rust-rebuild exec-rebuild verify verify-local

# Default target
help:
	@echo "GLADyS Development Tasks"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Local Development (preferred):"
	@echo "  setup         Install all Python deps across all services"
	@echo "  verify-local  Check local environment (PostgreSQL, pgvector, tables)"
	@echo ""
	@echo "Docker Development:"
	@echo "  verify        Verify Docker environment (containers, gRPC services)"
	@echo "  up            Start Docker services"
	@echo "  down          Stop Docker services"
	@echo "  restart       Restart Docker services"
	@echo "  rust-rebuild  Rebuild Rust container (after Rust code changes)"
	@echo "  exec-rebuild  Rebuild Executive container (after proto changes)"
	@echo ""
	@echo "Common:"
	@echo "  proto         Regenerate all gRPC stubs from .proto files"
	@echo "  test          Run all tests"
	@echo "  benchmark     Run salience benchmark"
	@echo "  help          Show this help"

# Install all Python dependencies across all services
setup:
	python cli/setup_dev.py

# Verify local environment (PostgreSQL, no Docker)
verify-local:
	python cli/verify_local.py

# Verify Docker environment
verify:
	python cli/verify_env.py

# Regenerate proto stubs
proto:
	python cli/proto_gen.py

# Run unit tests across all services
test:
	cd src/services/memory && uv run pytest tests/ -v
	cd src/services/orchestrator && uv run pytest tests/ -v
	cd src/services/dashboard && uv run pytest tests/ -v
	cd tests/unit && python -m pytest -v

# Docker operations
up:
	cd tests/integration && docker compose up -d

down:
	cd tests/integration && docker compose down

restart:
	cd tests/integration && docker compose restart

# Rebuild ONLY the Rust container (Python uses volume mounts, doesn't need rebuild)
rust-rebuild:
	cd tests/integration && docker compose up -d --build --force-recreate memory-rust

# Rebuild Executive container (required after proto changes or Dockerfile changes)
exec-rebuild:
	cd tests/integration && docker compose up -d --build --force-recreate executive-stub

# Run benchmark
benchmark:
	cd src/services/orchestrator && uv run python ../../tests/integration/benchmark_salience.py
