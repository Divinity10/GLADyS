# GLADyS Memory Storage - Python Service

FROM python:3.13-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies
RUN uv pip install --system -e .

# Copy source code
COPY gladys_memory ./gladys_memory

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV STORAGE_HOST=postgres
ENV STORAGE_PORT=5432

EXPOSE 50051

# Use standardized entry point
ENTRYPOINT ["python", "-m", "gladys_memory"]
CMD ["start"]
