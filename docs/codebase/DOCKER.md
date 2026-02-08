# Docker Build Requirements


**CRITICAL**: When adding dependencies or modifying code that uses shared packages, Docker builds will BREAK unless you follow these rules.

## 1. gladys_common Dependency Pattern

Any Python service using `gladys_common` (via `from gladys_common import ...`) MUST:

1. **Use project root as build context** in docker-compose.yml:
   ```yaml
   build:
     context: ../..  # Project root
     dockerfile: src/service/Dockerfile
   ```

2. **Copy gladys_common in Dockerfile**:
   ```dockerfile
   # Copy gladys-common first (dependency)
   COPY src/lib/gladys_common/pyproject.toml ./common/pyproject.toml
   COPY src/lib/gladys_common/gladys_common ./common/gladys_common
   ```

3. **Strip uv.sources and fix path** before installing:
   ```dockerfile
   RUN sed -i '/\[tool.uv.sources\]/,/^$/d' pyproject.toml && \
       sed -i 's/"gladys-common",/"gladys-common @ file:\/\/\/app\/common",/' pyproject.toml && \
       pip install -e ./common && \
       pip install -e .
   ```

**Services currently using gladys_common**:
- `src/services/orchestrator/` (router.py, __main__.py)
- `src/services/memory/` (grpc_server.py)

## 2. Local Path Dependencies in pyproject.toml

Files with `[tool.uv.sources]` sections that specify local paths:
- `src/services/orchestrator/pyproject.toml` -> `gladys-common = { path = "../common" }`
- `src/services/memory/pyproject.toml` -> `gladys-common = { path = "../../common" }`

These paths work locally but NOT in Docker unless handled as shown above.

## 3. Transitive Dependencies

Some packages may not install all their transitive dependencies correctly. Known examples:
- `huggingface-hub` and `sentence-transformers` require `requests` but it may not be auto-installed via uv
- **Fix**: Add explicit dependency in pyproject.toml: `"requests>=2.28"`

## 4. Verification After Changes

After modifying Dockerfiles or dependencies:
```bash
# Rebuild with no cache to catch issues
python cli/docker.py build <service> --no-cache

# Check packages in container
docker run --rm --entrypoint pip <image> freeze | grep <package>

# Run tests
python cli/docker.py test
```

## 5. Proto Files and Build Contexts

Proto files live at `proto/` (project root), but Dockerfiles have DIFFERENT build contexts:

| Service | Dockerfile | Build Context | Proto Access |
|---------|------------|---------------|--------------|
| memory-python | `src/services/memory/Dockerfile` | Project root | Uses pre-committed stubs |
| memory-rust | `src/services/salience/Dockerfile` | Project root | Needs `proto/` in context |
| orchestrator | `src/services/orchestrator/Dockerfile` | Project root | Needs `proto/` in context |
| executive | `src/services/executive/Dockerfile` | Project root | Needs `proto/` in context |

**Proto change problems:**
- Health RPCs return `UNIMPLEMENTED` -> Docker image has old proto stubs
- Services show "running (healthy)" but gRPC health fails -> Image needs rebuild

**Solution:**
```bash
docker compose -f docker/docker-compose.yml build --no-cache memory-rust
python cli/docker.py restart memory-rust
```

## 6. Python Services with Volume Mounts

memory-python and orchestrator have source mounted as volumes in `docker-compose.yml`:
```yaml
volumes:
  - ../memory/python/gladys_memory:/app/gladys_memory:ro
```

Python code changes are picked up WITHOUT rebuild. But:
- Proto stub changes still require rebuild (stubs are in generated/ dirs)
- `--force-recreate` recreates containers but doesn't rebuild images
