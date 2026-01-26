//! Structured logging for GLADyS Rust services.
//!
//! Provides consistent, debuggable logging matching the Python services with:
//! - Structured output (JSON or human-readable)
//! - Trace ID propagation for request correlation
//! - File and console output
//! - Configurable log levels
//!
//! Configuration via environment variables:
//!   LOG_LEVEL: trace, debug, info, warn, error (default: info)
//!   LOG_FORMAT: human, json (default: human)
//!   LOG_FILE: Path to log file (optional)

use std::env;
use std::path::Path;
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::{
    fmt,
    layer::SubscriberExt,
    util::SubscriberInitExt,
    EnvFilter,
};

/// Guard for non-blocking file writer. Must be held for the lifetime of the application.
pub struct LogGuard {
    _file_guard: Option<WorkerGuard>,
}

/// Initialize logging for a GLADyS Rust service.
///
/// Returns a guard that must be held for the application lifetime to ensure
/// logs are flushed to file.
pub fn setup_logging(service_name: &str) -> LogGuard {
    let log_level = env::var("LOG_LEVEL").unwrap_or_else(|_| "info".to_string());
    let log_format = env::var("LOG_FORMAT").unwrap_or_else(|_| "human".to_string());
    let log_file = env::var("LOG_FILE").ok();

    // Build env filter - use LOG_LEVEL if RUST_LOG isn't set
    let filter = env::var("RUST_LOG").unwrap_or_else(|_| {
        format!("{}={}", env!("CARGO_PKG_NAME").replace("-", "_"), log_level)
    });
    let env_filter = EnvFilter::try_new(&filter).unwrap_or_else(|_| EnvFilter::new("info"));

    // Build subscriber based on format and file options
    // Using separate paths to avoid type mismatches between JSON and human formats
    let file_guard = match (log_format.as_str(), log_file) {
        ("json", Some(path)) => {
            let path = Path::new(&path);
            let dir = path.parent().unwrap_or(Path::new("."));
            let filename = path.file_name().and_then(|n| n.to_str()).unwrap_or("service.log");
            let file_appender = tracing_appender::rolling::never(dir, filename);
            let (non_blocking, guard) = tracing_appender::non_blocking(file_appender);

            tracing_subscriber::registry()
                .with(env_filter)
                .with(fmt::layer().json().with_target(false).with_file(false).with_line_number(false))
                .with(fmt::layer().json().with_writer(non_blocking).with_target(false).with_file(false).with_line_number(false))
                .init();
            Some(guard)
        }
        ("json", None) => {
            tracing_subscriber::registry()
                .with(env_filter)
                .with(fmt::layer().json().with_target(false).with_file(false).with_line_number(false))
                .init();
            None
        }
        (_, Some(path)) => {
            let path = Path::new(&path);
            let dir = path.parent().unwrap_or(Path::new("."));
            let filename = path.file_name().and_then(|n| n.to_str()).unwrap_or("service.log");
            let file_appender = tracing_appender::rolling::never(dir, filename);
            let (non_blocking, guard) = tracing_appender::non_blocking(file_appender);

            tracing_subscriber::registry()
                .with(env_filter)
                .with(fmt::layer().with_ansi(true).with_target(false).with_file(false).with_line_number(false))
                .with(fmt::layer().with_writer(non_blocking).with_ansi(false).with_target(false).with_file(false).with_line_number(false))
                .init();
            Some(guard)
        }
        (_, None) => {
            tracing_subscriber::registry()
                .with(env_filter)
                .with(fmt::layer().with_ansi(true).with_target(false).with_file(false).with_line_number(false))
                .init();
            None
        }
    };

    // Log startup info
    tracing::info!(service = service_name, "Logging initialized");

    LogGuard {
        _file_guard: file_guard,
    }
}

/// Generate a new trace ID (12 hex characters).
pub fn generate_trace_id() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    format!("{:012x}", now & 0xffffffffffff)
}

/// Header name for trace ID in gRPC metadata.
pub const TRACE_ID_HEADER: &str = "x-gladys-trace-id";

/// Extract trace ID from gRPC metadata.
pub fn extract_trace_id<T>(request: &tonic::Request<T>) -> Option<String> {
    request
        .metadata()
        .get(TRACE_ID_HEADER)
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string())
}

/// Get trace ID from request or generate a new one.
pub fn get_or_create_trace_id<T>(request: &tonic::Request<T>) -> String {
    extract_trace_id(request).unwrap_or_else(generate_trace_id)
}
