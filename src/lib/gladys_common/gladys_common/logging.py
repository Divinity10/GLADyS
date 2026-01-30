"""Structured logging for GLADyS services.

Provides consistent, debuggable logging across all services with:
- Structured output (JSON or human-readable)
- Trace ID propagation for request correlation
- File and console output
- Configurable log levels

Usage:
    from gladys_common import setup_logging, get_logger, bind_trace_id

    # At service startup
    setup_logging("memory-python")

    # In request handlers
    logger = get_logger()
    bind_trace_id(trace_id)  # From gRPC metadata or generate new
    logger.info("Processing request", request_id=req.id)

Configuration via environment variables:
    LOG_LEVEL: DEBUG, INFO, WARN, ERROR (default: INFO)
    LOG_FORMAT: human, json (default: human)
    LOG_FILE: Path to log file (optional)
    LOG_FILE_LEVEL: Level for file output (default: same as LOG_LEVEL)
"""

import logging
import os
import secrets
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

# Constants
TRACE_ID_HEADER = "x-gladys-trace-id"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "human"
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_FILE_BACKUP_COUNT = 5


def generate_trace_id() -> str:
    """Generate a new trace ID (12 hex characters)."""
    return secrets.token_hex(6)


def _get_log_level(level_str: str) -> int:
    """Convert string log level to logging constant."""
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    return levels.get(level_str.upper(), logging.INFO)


def _create_file_handler(log_file: str, level: int) -> RotatingFileHandler:
    """Create a rotating file handler."""
    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    return handler


def setup_logging(service_name: str) -> None:
    """Configure logging for a GLADyS service.

    Args:
        service_name: Name of the service (e.g., "memory-python", "orchestrator")
    """
    level_str = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL)
    log_format = os.environ.get("LOG_FORMAT", DEFAULT_LOG_FORMAT)
    log_file = os.environ.get("LOG_FILE")
    file_level_str = os.environ.get("LOG_FILE_LEVEL", level_str)

    level = _get_log_level(level_str)
    file_level = _get_log_level(file_level_str)

    # Configure standard logging (structlog will use this)
    root_logger = logging.getLogger()
    root_logger.setLevel(min(level, file_level))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    # File handler (if configured)
    if log_file:
        file_handler = _create_file_handler(log_file, file_level)
        root_logger.addHandler(file_handler)

    # Configure structlog to use stdlib logging (so file handlers work)
    # Pre-chain processors run before passing to stdlib
    pre_chain = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]

    if log_format == "json":
        # JSON formatter for stdlib handler
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=pre_chain,
        )
    else:
        # Human-readable formatter for stdlib handler
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            foreign_pre_chain=pre_chain,
        )

    # Apply formatter to all handlers
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)

    # Configure structlog to use stdlib
    structlog.configure(
        processors=pre_chain + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bind service name to all logs
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a configured logger.

    Args:
        name: Optional logger name. If not provided, uses root logger.

    Returns:
        A structlog BoundLogger with service context already bound.
    """
    return structlog.get_logger(name)


def bind_trace_id(trace_id: str) -> None:
    """Bind a trace ID to the current context.

    Call this at the start of each request to enable request correlation
    across service boundaries.

    Args:
        trace_id: The trace ID (usually from gRPC metadata or generated)
    """
    structlog.contextvars.bind_contextvars(trace_id=trace_id)


def unbind_trace_id() -> None:
    """Remove the trace ID from the current context.

    Call this at the end of a request if the context will be reused.
    """
    structlog.contextvars.unbind_contextvars("trace_id")


def extract_trace_id_from_metadata(metadata: Any) -> str | None:
    """Extract trace ID from gRPC metadata.

    Args:
        metadata: gRPC invocation metadata (dict-like)

    Returns:
        The trace ID if present, None otherwise.
    """
    if hasattr(metadata, "get"):
        return metadata.get(TRACE_ID_HEADER)
    # Handle list of tuples format
    if isinstance(metadata, (list, tuple)):
        for key, value in metadata:
            if key == TRACE_ID_HEADER:
                return value
    return None


def get_or_create_trace_id(metadata: Any) -> str:
    """Get trace ID from metadata or generate a new one.

    Args:
        metadata: gRPC invocation metadata

    Returns:
        Existing trace ID from metadata, or a newly generated one.
    """
    trace_id = extract_trace_id_from_metadata(metadata)
    if not trace_id:
        trace_id = generate_trace_id()
    return trace_id
