//! Integration tests for Rust gRPC client.
//!
//! These tests require the Python storage server to be running:
//!   cd src/memory/python && uv run python -m gladys_memory.grpc_server
//!
//! Run with: cargo test --test integration_test

use gladys_memory::{
    client::{bytes_to_embedding, embedding_to_bytes},
    ClientConfig, EventBuilder, HeuristicBuilder, StorageClient,
};
use std::time::Duration;
use uuid::Uuid;

/// Helper to create a test client config pointing to local server.
fn test_config() -> ClientConfig {
    ClientConfig {
        address: "http://localhost:50051".to_string(),
        connect_timeout: Duration::from_secs(5),
        request_timeout: Duration::from_secs(30),
    }
}

/// Test that we can connect to the storage server.
#[tokio::test]
async fn test_connect() {
    let config = test_config();
    let client = match StorageClient::connect(config).await {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Skipping integration test - Python server not running: {}", e);
            return;
        }
    };

    assert_eq!(client.config().address, "http://localhost:50051");
}

/// Test generating embeddings via the server.
#[tokio::test]
async fn test_generate_embedding() {
    let config = test_config();
    let mut client = match StorageClient::connect(config).await {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Skipping test - server not running: {}", e);
            return;
        }
    };

    let embedding = client.generate_embedding("Hello, world!").await.unwrap();
    assert_eq!(embedding.len(), 384, "Expected 384-dim embedding");

    // Verify values are reasonable (not all zeros or NaN)
    let sum: f32 = embedding.iter().map(|x| x.abs()).sum();
    assert!(sum > 0.0, "Embedding should not be all zeros");
    assert!(!embedding.iter().any(|x| x.is_nan()), "No NaN values");
}

/// Test storing and querying an event.
#[tokio::test]
async fn test_store_and_query_event() {
    let config = test_config();
    let mut client = match StorageClient::connect(config).await {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Skipping test - server not running: {}", e);
            return;
        }
    };

    // Generate embedding for our test text
    let text = "Integration test event from Rust";
    let embedding = client.generate_embedding(text).await.unwrap();

    // Create and store event
    let event_id = Uuid::new_v4();
    let event = EventBuilder::new(event_id, "rust_integration_test", text)
        .embedding(&embedding)
        .structured_json(r#"{"test": "integration"}"#)
        .build();

    client.store_event(event).await.unwrap();

    // Query by similarity - should find our event
    let results = client
        .query_by_similarity(&embedding, 0.9, None, 10)
        .await
        .unwrap();

    // Find our event in results
    let found = results.iter().any(|e| e.id == event_id.to_string());
    assert!(found, "Should find stored event by similarity");
}

/// Test storing and querying heuristics (CBR schema).
#[tokio::test]
async fn test_store_and_query_heuristic() {
    let config = test_config();
    let mut client = match StorageClient::connect(config).await {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Skipping test - server not running: {}", e);
            return;
        }
    };

    // Create and store heuristic using CBR schema
    let h_id = Uuid::new_v4();
    let heuristic = HeuristicBuilder::new(h_id, "rust_test_heuristic")
        .condition_text("rust test integration event")
        .effects_json(r#"{"salience": {"novelty": 0.8}}"#)
        .confidence(0.85)
        .build();

    // generate_embedding=true to create embedding from condition_text
    client.store_heuristic(heuristic, true).await.unwrap();

    // Query heuristics - returns HeuristicMatch wrappers
    let results = client.query_heuristics(0.5, 10).await.unwrap();

    // Find our heuristic in the matches
    let found = results.iter().any(|m| {
        m.heuristic.as_ref().map_or(false, |h| h.id == h_id.to_string())
    });
    assert!(found, "Should find stored heuristic");
}

/// Test embedding conversion roundtrip.
#[test]
fn test_embedding_bytes_roundtrip() {
    let original: Vec<f32> = (0..384).map(|i| i as f32 * 0.01 - 1.92).collect();
    let bytes = embedding_to_bytes(&original);
    let recovered = bytes_to_embedding(&bytes);

    assert_eq!(original.len(), recovered.len());
    for (a, b) in original.iter().zip(recovered.iter()) {
        assert!((a - b).abs() < 1e-6, "Values should match: {} vs {}", a, b);
    }
}
