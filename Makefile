# GLADyS Makefile
# Cross-platform targets for common operations

.PHONY: proto test help up down restart benchmark rust-rebuild

# Default target
help:
	@echo "GLADyS Development Tasks"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  proto         Regenerate all gRPC stubs from .proto files"
	@echo "  test          Run all tests"
	@echo "  up            Start Docker services (Python code changes auto-reload)"
	@echo "  down          Stop Docker services"
	@echo "  restart       Restart Docker services"
	@echo "  rust-rebuild  Rebuild Rust container (required after Rust code changes)"
	@echo "  benchmark     Run salience benchmark"
	@echo "  help          Show this help"
	@echo ""
	@echo "Development workflow:"
	@echo "  1. make up            - Start services"
	@echo "  2. Edit Python code   - Changes auto-reload (volume mounted)"
	@echo "  3. Edit Rust code     - Run 'make rust-rebuild'"
	@echo "  4. make benchmark     - Run performance benchmark"

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

# Run benchmark
benchmark:
	cd src/orchestrator && uv run python ../integration/benchmark_salience.py
