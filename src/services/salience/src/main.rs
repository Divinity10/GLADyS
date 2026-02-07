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

use gladys_memory::{
    CacheConfig, Config, MemoryCache, run_server, setup_logging,
    SalienceScorer, EmbeddingSimilarityScorer, GrpcStorageBackend
};
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

    // Create the scoring strategy
    let scorer = create_scorer(&config, cache.clone());

    info!(
        storage_address = %config.storage.address,
        scorer = %config.scorer,
        "Storage backend and scorer configured"
    );

    // Start the gRPC server
    info!(
        host = %config.server.host,
        port = config.server.port,
        "Starting gRPC server"
    );

    // This runs until the server is shut down (Ctrl+C)
    // The scorer handles heuristic matching (with cache-first logic)
    run_server(config.server, config.salience, scorer, cache).await?;

    info!("Memory Fast Path shutdown complete");
    Ok(())
}

/// Factory function to create the requested salience scorer.
fn create_scorer(
    config: &Config,
    cache: Arc<RwLock<MemoryCache>>,
) -> Box<dyn SalienceScorer> {
    match config.scorer.as_str() {
        "embedding" | "" => {
            let backend = Box::new(GrpcStorageBackend::new(config.storage.clone()));
            Box::new(EmbeddingSimilarityScorer::new(
                cache,
                backend,
                config.salience.min_heuristic_similarity,
                config.salience.min_heuristic_confidence,
            ))
        }
        other => panic!("Unknown scorer implementation: {}", other),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use gladys_memory::CacheConfig;

    #[test]
    fn test_create_scorer_default() {
        let config = Config::default();
        let cache = Arc::new(RwLock::new(MemoryCache::new(CacheConfig::default())));
        let scorer = create_scorer(&config, cache);
        assert_eq!(scorer.config()["scorer"], "embedding_similarity");
    }
}
