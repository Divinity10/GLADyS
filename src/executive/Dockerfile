# Executive stub Dockerfile (for integration testing)
# This is a test stub - the real Executive will be C#/.NET
#
# Build context is PROJECT ROOT so proto files are accessible.
# Generates proto stubs from shared proto directory

FROM python:3.13-slim

WORKDIR /app

# Install dependencies including grpc tools for proto generation
RUN pip install --no-cache-dir grpcio grpcio-tools grpcio-reflection aiohttp

# Copy proto files from project root
COPY proto/ proto/

# Create package structure for orchestrator and memory protos
RUN mkdir -p /app/gladys_orchestrator/generated && \
    mkdir -p /app/gladys_memory/generated && \
    touch /app/gladys_orchestrator/__init__.py && \
    touch /app/gladys_orchestrator/generated/__init__.py && \
    touch /app/gladys_memory/__init__.py && \
    touch /app/gladys_memory/generated/__init__.py

# Generate orchestrator proto stubs (executive.proto, common.proto, orchestrator.proto, types.proto)
RUN python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=gladys_orchestrator/generated \
    --grpc_python_out=gladys_orchestrator/generated \
    proto/executive.proto proto/common.proto proto/orchestrator.proto proto/types.proto || true

# Generate memory proto stubs
RUN python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=gladys_memory/generated \
    --grpc_python_out=gladys_memory/generated \
    proto/memory.proto proto/types.proto || true

# Fix relative imports in generated files (orchestrator)
RUN for f in gladys_orchestrator/generated/*_pb2*.py; do \
    if [ -f "$f" ]; then \
        sed -i 's/^import \([a-z_]*_pb2\)/from . import \1/g' "$f"; \
    fi; \
    done

# Fix relative imports in generated files (memory)
RUN for f in gladys_memory/generated/*_pb2*.py; do \
    if [ -f "$f" ]; then \
        sed -i 's/^import \([a-z_]*_pb2\)/from . import \1/g' "$f"; \
    fi; \
    done

# Copy the executive package (context is project root)
COPY src/executive/gladys_executive/ /app/gladys_executive/

# Create __init__.py if missing
RUN touch /app/gladys_executive/__init__.py

EXPOSE 50053

# Use standardized entry point
ENTRYPOINT ["python", "-m", "gladys_executive"]
CMD ["start"]
