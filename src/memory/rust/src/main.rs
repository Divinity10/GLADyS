//! GLADyS Memory Fast Path Service
//!
//! Entry point for the Rust memory service.
//!
//! The fast path handles:
//! - L0 in-memory cache for recent events
//! - Novelty detection via embedding similarity
//! - Heuristic lookup for System 1 fast responses
//! - gRPC server for SalienceGateway service
//! - Communication with Python storage backend via gRPC
//!
//! Configuration is loaded from environment variables.
//! See config module for available settings.

use std::sync::Arc;
use tokio::sync::RwLock;

use gladys_memory::{
    CacheConfig, ClientConfig, Config, MemoryCache, RefreshConfig, StorageClient, run_server,
};
use tracing::{info, warn, debug};

/// Load heuristics from Python storage into the cache.
async fn load_heuristics(
    storage_config: &gladys_memory::StorageConfig,
    refresh_config: &RefreshConfig,
    cache: &Arc<RwLock<MemoryCache>>,
) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
    let client_config = ClientConfig {
        address: storage_config.address.clone(),
        connect_timeout: storage_config.connect_timeout(),
        request_timeout: storage_config.request_timeout(),
    };

    let mut client = StorageClient::connect(client_config).await?;
    let matches = client.query_heuristics(0.0, refresh_config.max_heuristics).await?;

    let mut cache_write = cache.write().await;
    let mut count = 0;
    for m in matches {
        let h = match m.heuristic {
            Some(h) => h,
            None => continue,
        };
        let id = uuid::Uuid::parse_str(&h.id).unwrap_or_else(|_| uuid::Uuid::new_v4());
        // Build condition from condition_text (CBR schema)
        let condition = serde_json::json!({
            "text": h.condition_text
        });
        // Parse effects_json (CBR schema)
        let action: serde_json::Value = serde_json::from_str(&h.effects_json)
            .unwrap_or(serde_json::json!({}));

        cache_write.add_heuristic(gladys_memory::CachedHeuristic {
            id,
            name: h.name,
            condition,
            action,
            confidence: h.confidence,
        });
        count += 1;
    }
    Ok(count)
}

/// Background task to periodically refresh heuristics from storage.
async fn heuristic_refresh_loop(
    storage_config: gladys_memory::StorageConfig,
    refresh_config: RefreshConfig,
    cache: Arc<RwLock<MemoryCache>>,
) {
    loop {
        tokio::time::sleep(refresh_config.interval()).await;
        match load_heuristics(&storage_config, &refresh_config, &cache).await {
            Ok(count) => {
                debug!(heuristics = count, "Refreshed heuristics from storage");
            }
            Err(e) => {
                debug!("Failed to refresh heuristics: {}", e);
            }
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Debug output before tracing (to diagnose silent exits)
    eprintln!("=== GLADyS Memory Fast Path starting ===");
    eprintln!("STORAGE_ADDRESS: {:?}", std::env::var("STORAGE_ADDRESS"));
    eprintln!("RUST_LOG: {:?}", std::env::var("RUST_LOG"));

    // Initialize tracing (logging)
    tracing_subscriber::fmt::init();

    info!("Starting GLADyS Memory Fast Path");

    // Load configuration from environment variables
    let config = Config::from_env();
    config.log_config();

    // Initialize cache with config
    let cache = MemoryCache::new(CacheConfig {
        max_events: config.cache.max_events,
        novelty_threshold: config.cache.novelty_threshold,
    });
    info!(
        max_events = cache.stats().max_events,
        "L0 cache initialized"
    );

    // Wrap cache in Arc<RwLock> for shared access across async tasks
    let cache = Arc::new(RwLock::new(cache));

    info!(address = %config.storage.address, "Connecting to storage backend");

    // Try initial heuristic load
    match load_heuristics(&config.storage, &config.refresh, &cache).await {
        Ok(count) => {
            info!(heuristics_loaded = count, "Loaded heuristics from storage");
        }
        Err(e) => {
            warn!("Failed to connect to storage backend: {}. Running standalone.", e);
        }
    }

    // Start background heuristic refresh
    let cache_clone = Arc::clone(&cache);
    let storage_config = config.storage.clone();
    let refresh_config = config.refresh.clone();
    tokio::spawn(async move {
        heuristic_refresh_loop(storage_config, refresh_config, cache_clone).await;
    });

    // Start the gRPC server
    info!(
        host = %config.server.host,
        port = config.server.port,
        "Starting gRPC server"
    );

    // This runs until the server is shut down (Ctrl+C)
    run_server(config.server, config.salience, cache).await?;

    info!("Memory Fast Path shutdown complete");
    Ok(())
}
