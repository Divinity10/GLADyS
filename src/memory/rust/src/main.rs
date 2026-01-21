//! GLADyS Memory Fast Path Service
//!
//! Entry point for the Rust memory service.
//!
//! The fast path handles:
//! - L0 in-memory cache for recent events
//! - Novelty detection via embedding similarity
//! - Heuristic lookup for System 1 fast responses
//! - Communication with Python storage backend via gRPC

use gladys_memory::{CacheConfig, ClientConfig, MemoryCache, StorageClient};
use tracing::{info, warn};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize tracing
    tracing_subscriber::fmt::init();

    info!("Starting GLADyS Memory Fast Path");

    // Initialize cache with default config
    let cache = MemoryCache::new(CacheConfig::default());
    info!(
        max_events = cache.stats().max_events,
        "L0 cache initialized"
    );

    // Try to connect to Python storage backend
    let client_config = ClientConfig::default();
    info!(address = %client_config.address, "Connecting to storage backend");

    let storage_client = match StorageClient::connect(client_config).await {
        Ok(client) => {
            info!("Connected to Python storage backend");
            Some(client)
        }
        Err(e) => {
            warn!("Failed to connect to storage backend: {}. Running in cache-only mode.", e);
            None
        }
    };

    // Log initial state
    if storage_client.is_some() {
        info!("Memory Fast Path running with storage backend");
    } else {
        info!("Memory Fast Path running in standalone mode (no storage backend)");
    }

    // TODO: Start listening for requests from Orchestrator
    // The Orchestrator will send events to be processed through the fast path

    info!("Memory Fast Path ready");

    // Keep running until interrupted
    tokio::signal::ctrl_c().await?;
    info!("Shutting down Memory Fast Path");

    Ok(())
}
