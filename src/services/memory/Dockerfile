# GLADyS Memory Storage - Python Service
#
# Build context is PROJECT ROOT so gladys-common is accessible.
# Set via docker-compose.yml

FROM python:3.13-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy gladys-common first (dependency)
COPY src/lib/gladys_common/pyproject.toml ./common/pyproject.toml
COPY src/lib/gladys_common/gladys_common ./common/gladys_common

# Copy memory dependency files
COPY src/services/memory/pyproject.toml ./

# Remove uv.sources (local dev paths don't apply in Docker) and fix path
# Then install gladys-common and memory-python
RUN sed -i '/\[tool.uv.sources\]/,/^$/d' pyproject.toml && \
    sed -i 's/"gladys-common",/"gladys-common @ file:\/\/\/app\/common",/' pyproject.toml && \
    uv pip install --system -e ./common && \
    uv pip install --system -e .

# Copy source code
COPY src/services/memory/gladys_memory ./gladys_memory

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV STORAGE_HOST=postgres
ENV STORAGE_PORT=5432

EXPOSE 50051

# Use standardized entry point
ENTRYPOINT ["python", "-m", "gladys_memory"]
CMD ["start"]
