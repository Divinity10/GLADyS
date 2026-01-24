# GLADyS Makefile
# Cross-platform targets for common operations

.PHONY: proto test help up down restart benchmark rust-rebuild exec-rebuild verify verify-local

# Default target
help:
	@echo "GLADyS Development Tasks"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Local Development (preferred):"
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

# Verify local environment (PostgreSQL, no Docker)
verify-local:
	python scripts/verify_local.py

# Verify Docker environment
verify:
	python scripts/verify_env.py

# Regenerate proto stubs
proto:
	python scripts/proto_sync.py

# Run tests (requires Docker for integration tests)
test:
	cd src/memory/python && python -m pytest tests/ -v

# Docker operations
up:
	cd src/integration && docker compose up -d

down:
	cd src/integration && docker compose down

restart:
	cd src/integration && docker compose restart

# Rebuild ONLY the Rust container (Python uses volume mounts, doesn't need rebuild)
rust-rebuild:
	cd src/integration && docker compose up -d --build --force-recreate memory-rust

# Rebuild Executive container (required after proto changes or Dockerfile changes)
exec-rebuild:
	cd src/integration && docker compose up -d --build --force-recreate executive-stub

# Run benchmark
benchmark:
	cd src/orchestrator && uv run python ../integration/benchmark_salience.py
