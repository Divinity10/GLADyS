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

use std::sync::Arc;
use tokio::sync::RwLock;

use gladys_memory::{
    CacheConfig, ClientConfig, MemoryCache, ServerConfig, StorageClient, run_server,
};
use tracing::{info, warn};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize tracing (logging)
    tracing_subscriber::fmt::init();

    info!("Starting GLADyS Memory Fast Path");

    // Initialize cache with default config
    let cache = MemoryCache::new(CacheConfig::default());
    info!(
        max_events = cache.stats().max_events,
        "L0 cache initialized"
    );

    // Wrap cache in Arc<RwLock> for shared access across async tasks
    let cache = Arc::new(RwLock::new(cache));

    // Try to connect to Python storage backend (for loading heuristics, etc.)
    let client_config = ClientConfig::default();
    info!(address = %client_config.address, "Connecting to storage backend");

    let _storage_client = match StorageClient::connect(client_config).await {
        Ok(client) => {
            info!("Connected to Python storage backend");
            Some(client)
        }
        Err(e) => {
            warn!("Failed to connect to storage backend: {}. Running standalone.", e);
            None
        }
    };

    // TODO: Load heuristics from storage into cache on startup
    // This would populate the cache with learned rules from the database

    // Start the gRPC server
    let server_config = ServerConfig::default(); // Listens on 0.0.0.0:50052
    info!(
        host = %server_config.host,
        port = server_config.port,
        "Starting gRPC server"
    );

    // This runs until the server is shut down (Ctrl+C)
    run_server(server_config, cache).await?;

    info!("Memory Fast Path shutdown complete");
    Ok(())
}
