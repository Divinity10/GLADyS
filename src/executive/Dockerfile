# Executive stub Dockerfile (for integration testing)
# This is a test stub - the real Executive will be C#/.NET
#
# Build context should be src/ directory
# Generates proto stubs from shared proto directory

FROM python:3.13-slim

WORKDIR /app

# Install dependencies including grpc tools for proto generation
RUN pip install --no-cache-dir grpcio grpcio-tools grpcio-reflection aiohttp

# Copy proto files from orchestrator (context is src/)
COPY orchestrator/proto/ proto/

# Create package structure
RUN mkdir -p /app/gladys_orchestrator/generated && \
    touch /app/gladys_orchestrator/__init__.py && \
    touch /app/gladys_orchestrator/generated/__init__.py

# Generate proto stubs
RUN python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=gladys_orchestrator/generated \
    --grpc_python_out=gladys_orchestrator/generated \
    proto/*.proto || true

# Fix relative imports in generated files
RUN for f in gladys_orchestrator/generated/*_pb2*.py; do \
    if [ -f "$f" ]; then \
        sed -i 's/^import \([a-z_]*_pb2\)/from . import \1/g' "$f"; \
    fi; \
    done

# Copy the stub server (context is src/)
COPY executive/stub_server.py /app/

EXPOSE 50053

CMD ["python", "stub_server.py"]
