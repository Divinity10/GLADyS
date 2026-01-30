# GLADyS Memory Fast Path - Rust Service
# Multi-stage build for smaller final image
#
# Build context is PROJECT ROOT so proto files are accessible.
# Set via docker-compose.yml

# Build stage
FROM rust:1.85-bookworm AS builder

# Install protobuf compiler
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy proto files from project root (needed for build)
COPY proto ./proto

# Copy Rust project from src/memory/rust/
COPY src/services/salience/Cargo.toml src/services/salience/Cargo.lock* ./
COPY src/services/salience/build.rs ./

# Create dummy source to build dependencies
RUN mkdir src && echo "fn main() {}" > src/main.rs && echo "" > src/lib.rs

# Build dependencies only (cached if Cargo.toml unchanged)
# Remove binary AND deps to force recompilation of actual source
RUN cargo build --release && rm -rf src target/release/deps/gladys* target/release/memory-fast-path

# Copy actual source code
COPY src/services/salience/src ./src

# Build the real binary (touch source to ensure Cargo sees it as changed)
RUN touch src/main.rs src/lib.rs && cargo build --release

# Runtime stage
FROM debian:bookworm-slim

# Install runtime dependencies (netcat-openbsd for healthcheck)
RUN apt-get update && apt-get install -y ca-certificates netcat-openbsd && rm -rf /var/lib/apt/lists/*

# Copy binary from builder
COPY --from=builder /app/target/release/memory-fast-path /usr/local/bin/

# Set environment variables
ENV RUST_LOG=info
ENV STORAGE_ADDRESS=http://python-storage:50051

EXPOSE 50052

CMD ["memory-fast-path"]
