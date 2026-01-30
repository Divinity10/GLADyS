# GLADyS Orchestrator Dockerfile
# Build context is PROJECT ROOT so proto files are accessible.
FROM python:3.11-slim

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy gladys-common first (dependency)
COPY src/common/pyproject.toml ./common/pyproject.toml
COPY src/common/gladys_common ./common/gladys_common

# Copy dependency files first (better caching)
COPY src/orchestrator/pyproject.toml .

# Remove uv.sources (local dev paths don't apply in Docker)
# Update gladys-common path and install
RUN sed -i '/\[tool.uv.sources\]/,/^$/d' pyproject.toml && \
    sed -i 's/"gladys-common",/"gladys-common @ file:\/\/\/app\/common",/' pyproject.toml && \
    pip install --no-cache-dir -e ./common && \
    pip install --no-cache-dir -e .

# Copy proto files from project root and generate
COPY proto/ proto/
RUN python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=gladys_orchestrator/generated \
    --grpc_python_out=gladys_orchestrator/generated \
    proto/*.proto || true

# Copy application code
COPY src/orchestrator/gladys_orchestrator/ gladys_orchestrator/

# Create non-root user
RUN useradd -m gladys && chown -R gladys:gladys /app
USER gladys

# Default port
EXPOSE 50050

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; grpc.channel_ready_future(grpc.insecure_channel('localhost:50050')).result(timeout=5)" || exit 1

# Run the server
ENTRYPOINT ["python", "-m", "gladys_orchestrator"]
CMD ["start"]
