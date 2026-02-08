# Logging and Observability


## Trace ID Propagation
All services propagate trace IDs via gRPC metadata for request correlation:

```
Header: x-gladys-trace-id
Format: 12 hex characters (e.g., "abc123def456")
```

Flow: Orchestrator generates -> Rust receives and forwards -> Python receives and logs

## Log File Locations

| Environment | Location | Notes |
|-------------|----------|-------|
| Local | `~/.gladys/logs/<service>.log` | Auto-configured by local.py |
| Docker | Container stdout | Use `docker-compose logs` or UI Logs tab |

Local services automatically get `LOG_FILE` set with `LOG_FILE_LEVEL=DEBUG` for troubleshooting.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Minimum log level (DEBUG, INFO, WARN, ERROR) |
| `LOG_FORMAT` | `human` | Output format (`human` or `json`) |
| `LOG_FILE` | (auto for local) | Path to log file |
| `LOG_FILE_LEVEL` | `DEBUG` (local) | Level for file output |

## Logging Implementation

| Service | Module | Framework |
|---------|--------|-----------|
| Python services | `gladys_common.logging` | structlog |
| Rust services | `src/services/salience/src/logging.rs` | tracing |

See `docs/design/LOGGING_STANDARD.md` for full specification.
