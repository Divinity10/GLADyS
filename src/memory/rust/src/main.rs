//! GLADyS Memory Fast Path Service
//!
//! Entry point for the Rust memory service.
//!
//! The fast path handles:
//! - L0 in-memory LRU cache for recently matched heuristics
//! - Novelty detection via embedding similarity
//! - Heuristic lookup for System 1 fast responses
//! - gRPC server for SalienceGateway service
//!
//! On cache miss, queries Python storage via QueryMatchingHeuristics RPC.
//!
//! Configuration is loaded from environment variables.
//! See config module for available settings.

use std::sync::Arc;
use tokio::sync::RwLock;

use gladys_memory::{CacheConfig, Config, MemoryCache, run_server, setup_logging};
use tracing::info;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize structured logging (must hold guard for app lifetime)
    let _log_guard = setup_logging("memory-rust");

    info!("Starting GLADyS Memory Fast Path");

    // Load configuration from environment variables
    let config = Config::from_env();
    config.log_config();

    // Initialize empty LRU cache - heuristics are loaded on-demand from storage
    let cache = MemoryCache::new(CacheConfig {
        max_events: config.cache.max_events,
        max_heuristics: config.cache.max_heuristics,
        novelty_threshold: config.cache.novelty_threshold,
        heuristic_ttl_ms: config.cache.heuristic_ttl_ms,
    });
    info!(
        max_events = cache.stats().max_events,
        max_heuristics = config.cache.max_heuristics,
        "L0 cache initialized (empty - heuristics loaded on demand)"
    );

    // Wrap cache in Arc<RwLock> for shared access across async tasks
    let cache = Arc::new(RwLock::new(cache));

    info!(
        storage_address = %config.storage.address,
        "Storage backend configured for cache-miss queries"
    );

    // Start the gRPC server
    info!(
        host = %config.server.host,
        port = config.server.port,
        "Starting gRPC server"
    );

    // This runs until the server is shut down (Ctrl+C)
    // On cache miss, the server queries Python storage for matching heuristics
    run_server(config.server, config.salience, config.storage, cache).await?;

    info!("Memory Fast Path shutdown complete");
    Ok(())
}
