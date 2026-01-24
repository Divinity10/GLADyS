//! Configuration for GLADyS Memory Fast Path.
//!
//! All configuration values can be set via environment variables.
//! This mirrors the Python config pattern using pydantic Settings.

use std::env;
use std::time::Duration;

/// Server configuration for the gRPC service.
#[derive(Debug, Clone)]
pub struct ServerConfig {
    /// Host to bind to (default: 0.0.0.0)
    pub host: String,
    /// Port to listen on (default: 50052)
    pub port: u16,
}

impl Default for ServerConfig {
    fn default() -> Self {
        Self {
            host: env::var("GRPC_HOST").unwrap_or_else(|_| "0.0.0.0".to_string()),
            port: env::var("GRPC_PORT")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(50052),
        }
    }
}

/// Storage client configuration for connecting to Python backend.
#[derive(Debug, Clone)]
pub struct StorageConfig {
    /// Address of the Python storage service (default: http://localhost:50051)
    pub address: String,
    /// Connection timeout in seconds (default: 5)
    pub connect_timeout_secs: u64,
    /// Request timeout in seconds (default: 30)
    pub request_timeout_secs: u64,
}

impl Default for StorageConfig {
    fn default() -> Self {
        Self {
            address: env::var("STORAGE_ADDRESS")
                .unwrap_or_else(|_| "http://localhost:50051".to_string()),
            connect_timeout_secs: env::var("STORAGE_CONNECT_TIMEOUT_SECS")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(5),
            request_timeout_secs: env::var("STORAGE_REQUEST_TIMEOUT_SECS")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(30),
        }
    }
}

impl StorageConfig {
    pub fn connect_timeout(&self) -> Duration {
        Duration::from_secs(self.connect_timeout_secs)
    }

    pub fn request_timeout(&self) -> Duration {
        Duration::from_secs(self.request_timeout_secs)
    }
}

/// Cache configuration for the L0 in-memory cache.
#[derive(Debug, Clone)]
pub struct CacheConfig {
    /// Maximum number of events to store (default: 1000)
    pub max_events: usize,
    /// Maximum number of heuristics to cache (LRU eviction, default: 50)
    pub max_heuristics: usize,
    /// Novelty threshold - similarity below this = novel (default: 0.7)
    pub novelty_threshold: f32,
}

impl Default for CacheConfig {
    fn default() -> Self {
        Self {
            max_events: env::var("CACHE_MAX_EVENTS")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(1000),
            max_heuristics: env::var("CACHE_MAX_HEURISTICS")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(50),
            novelty_threshold: env::var("CACHE_NOVELTY_THRESHOLD")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(0.7),
        }
    }
}

/// Salience evaluation configuration.
#[derive(Debug, Clone)]
pub struct SalienceConfig {
    /// Minimum confidence for heuristic matching (default: 0.5)
    pub min_heuristic_confidence: f32,
    /// Baseline novelty for all events (default: 0.1)
    pub baseline_novelty: f32,
    /// Novelty boost when no heuristic matches (default: 0.4)
    pub unmatched_novelty_boost: f32,
    /// Minimum word overlap ratio for heuristic matching (default: 0.3)
    pub word_overlap_ratio: f32,
    /// Minimum word overlap count (default: 2)
    pub min_word_overlap: usize,
}

impl Default for SalienceConfig {
    fn default() -> Self {
        Self {
            min_heuristic_confidence: env::var("SALIENCE_MIN_HEURISTIC_CONFIDENCE")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(0.5),
            baseline_novelty: env::var("SALIENCE_BASELINE_NOVELTY")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(0.1),
            unmatched_novelty_boost: env::var("SALIENCE_UNMATCHED_NOVELTY_BOOST")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(0.4),
            word_overlap_ratio: env::var("SALIENCE_WORD_OVERLAP_RATIO")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(0.3),
            min_word_overlap: env::var("SALIENCE_MIN_WORD_OVERLAP")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(2),
        }
    }
}

/// Heuristic refresh configuration.
#[derive(Debug, Clone)]
pub struct RefreshConfig {
    /// Interval between heuristic refreshes in seconds (default: 5)
    pub interval_secs: u64,
    /// Maximum heuristics to load per refresh (default: 100)
    pub max_heuristics: i32,
}

impl Default for RefreshConfig {
    fn default() -> Self {
        Self {
            interval_secs: env::var("REFRESH_INTERVAL_SECS")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(5),
            max_heuristics: env::var("REFRESH_MAX_HEURISTICS")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(100),
        }
    }
}

impl RefreshConfig {
    pub fn interval(&self) -> Duration {
        Duration::from_secs(self.interval_secs)
    }
}

/// Root configuration that aggregates all config sections.
#[derive(Debug, Clone, Default)]
pub struct Config {
    pub server: ServerConfig,
    pub storage: StorageConfig,
    pub cache: CacheConfig,
    pub salience: SalienceConfig,
    pub refresh: RefreshConfig,
}

impl Config {
    /// Load configuration from environment variables.
    pub fn from_env() -> Self {
        Self::default()
    }

    /// Log current configuration values.
    pub fn log_config(&self) {
        tracing::info!(
            server_host = %self.server.host,
            server_port = self.server.port,
            storage_address = %self.storage.address,
            cache_max_events = self.cache.max_events,
            novelty_threshold = self.cache.novelty_threshold,
            min_heuristic_confidence = self.salience.min_heuristic_confidence,
            refresh_interval_secs = self.refresh.interval_secs,
            "Configuration loaded"
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = Config::default();
        assert_eq!(config.server.port, 50052);
        assert_eq!(config.cache.max_events, 1000);
        assert!((config.cache.novelty_threshold - 0.7).abs() < 0.001);
    }
}
