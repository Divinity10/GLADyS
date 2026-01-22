# GLADyS Orchestrator Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first (better caching)
COPY pyproject.toml .

# Install dependencies
RUN pip install --no-cache-dir -e .

# Copy proto files and generate
COPY proto/ proto/
RUN python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=gladys_orchestrator/generated \
    --grpc_python_out=gladys_orchestrator/generated \
    proto/*.proto || true

# Copy application code
COPY gladys_orchestrator/ gladys_orchestrator/
COPY run.py .

# Create non-root user
RUN useradd -m gladys && chown -R gladys:gladys /app
USER gladys

# Default port
EXPOSE 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; grpc.channel_ready_future(grpc.insecure_channel('localhost:50051')).result(timeout=5)" || exit 1

# Run the server
ENTRYPOINT ["python", "run.py"]
CMD ["start"]
