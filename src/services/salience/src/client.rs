//! gRPC client for Python storage backend.
//!
//! This module provides a Rust client to communicate with the Python
//! MemoryStorage gRPC service for persistent storage operations.

use std::time::Duration;
use thiserror::Error;
use tonic::transport::{Channel, Endpoint};
use tonic::Request;
use tracing::{debug, instrument};
use uuid::Uuid;

use crate::logging::TRACE_ID_HEADER;

use crate::proto::{
    memory_storage_client::MemoryStorageClient, EpisodicEvent, GenerateEmbeddingRequest,
    Heuristic, HeuristicMatch, QueryByTimeRequest, QueryBySimilarityRequest, QueryHeuristicsRequest,
    QueryMatchingHeuristicsRequest, SalienceVector, StoreEventRequest, StoreHeuristicRequest,
};

/// Errors from the storage client.
#[derive(Error, Debug)]
pub enum ClientError {
    #[error("Failed to connect to storage service: {0}")]
    ConnectionFailed(#[from] tonic::transport::Error),

    #[error("RPC failed: {0}")]
    RpcFailed(#[from] tonic::Status),

    #[error("Storage service returned error: {0}")]
    StorageError(String),

    #[error("Invalid response from storage service")]
    InvalidResponse,
}

/// Configuration for the storage client.
#[derive(Clone, Debug)]
pub struct ClientConfig {
    /// Address of the Python storage service (e.g., "http://localhost:50051")
    pub address: String,
    /// Connection timeout
    pub connect_timeout: Duration,
    /// Request timeout
    pub request_timeout: Duration,
}

impl Default for ClientConfig {
    fn default() -> Self {
        Self {
            address: "http://localhost:50051".to_string(),
            connect_timeout: Duration::from_secs(5),
            request_timeout: Duration::from_secs(30),
        }
    }
}

/// Client for the Python storage backend.
pub struct StorageClient {
    client: MemoryStorageClient<Channel>,
    config: ClientConfig,
    /// Trace ID to propagate on outgoing requests
    trace_id: Option<String>,
}

impl StorageClient {
    /// Connect to the storage service.
    #[instrument(skip_all, fields(address = %config.address))]
    pub async fn connect(config: ClientConfig) -> Result<Self, ClientError> {
        debug!("Connecting to storage service");

        let endpoint = Endpoint::from_shared(config.address.clone())?
            .connect_timeout(config.connect_timeout)
            .timeout(config.request_timeout);

        let channel = endpoint.connect().await?;
        let client = MemoryStorageClient::new(channel);

        debug!("Connected to storage service");
        Ok(Self { client, config, trace_id: None })
    }

    /// Set the trace ID for request correlation.
    /// The trace ID will be included in the metadata of all subsequent requests.
    pub fn with_trace_id(mut self, trace_id: String) -> Self {
        self.trace_id = Some(trace_id);
        self
    }

    /// Add trace ID header to a request if one is set.
    fn add_trace_header<T>(&self, mut request: Request<T>) -> Request<T> {
        if let Some(ref trace_id) = self.trace_id {
            if let Ok(value) = trace_id.parse() {
                request.metadata_mut().insert(TRACE_ID_HEADER, value);
            }
        }
        request
    }

    /// Store an episodic event.
    #[instrument(skip(self, event), fields(event_id = %event.id))]
    pub async fn store_event(&mut self, event: EpisodicEvent) -> Result<(), ClientError> {
        debug!("Storing event");

        let request = StoreEventRequest { event: Some(event) };
        let response = self.client.store_event(request).await?.into_inner();

        if !response.success {
            return Err(ClientError::StorageError(response.error));
        }

        debug!("Event stored successfully");
        Ok(())
    }

    /// Query events by time range.
    #[instrument(skip(self))]
    pub async fn query_by_time(
        &mut self,
        start_ms: i64,
        end_ms: i64,
        source_filter: Option<&str>,
        limit: i32,
    ) -> Result<Vec<EpisodicEvent>, ClientError> {
        debug!("Querying events by time");

        let request = QueryByTimeRequest {
            start_ms,
            end_ms,
            source_filter: source_filter.unwrap_or("").to_string(),
            limit,
        };

        let response = self.client.query_by_time(request).await?.into_inner();

        if !response.error.is_empty() {
            return Err(ClientError::StorageError(response.error));
        }

        debug!(count = response.events.len(), "Retrieved events");
        Ok(response.events)
    }

    /// Query events by embedding similarity.
    #[instrument(skip(self, query_embedding))]
    pub async fn query_by_similarity(
        &mut self,
        query_embedding: &[f32],
        similarity_threshold: f32,
        time_filter_hours: Option<i64>,
        limit: i32,
    ) -> Result<Vec<EpisodicEvent>, ClientError> {
        debug!("Querying events by similarity");

        let embedding_bytes = embedding_to_bytes(query_embedding);

        let request = QueryBySimilarityRequest {
            query_embedding: embedding_bytes,
            similarity_threshold,
            time_filter_hours: time_filter_hours.unwrap_or(0),
            limit,
        };

        let response = self.client.query_by_similarity(request).await?.into_inner();

        if !response.error.is_empty() {
            return Err(ClientError::StorageError(response.error));
        }

        debug!(count = response.events.len(), "Retrieved similar events");
        Ok(response.events)
    }

    /// Generate embedding for text.
    #[instrument(skip(self, text))]
    pub async fn generate_embedding(&mut self, text: &str) -> Result<Vec<f32>, ClientError> {
        debug!("Generating embedding");

        let request = GenerateEmbeddingRequest {
            text: text.to_string(),
        };

        let response = self.client.generate_embedding(request).await?.into_inner();

        if !response.error.is_empty() {
            return Err(ClientError::StorageError(response.error));
        }

        let embedding = bytes_to_embedding(&response.embedding);
        debug!(dims = embedding.len(), "Generated embedding");
        Ok(embedding)
    }

    /// Store a heuristic.
    /// If generate_embedding is true, the storage service will generate an embedding
    /// from condition_text (requires the heuristic to have condition_text set).
    #[instrument(skip(self, heuristic), fields(heuristic_id = %heuristic.id))]
    pub async fn store_heuristic(&mut self, heuristic: Heuristic, generate_embedding: bool) -> Result<(), ClientError> {
        debug!("Storing heuristic");

        let request = StoreHeuristicRequest {
            heuristic: Some(heuristic),
            generate_embedding,
        };

        let response = self.client.store_heuristic(request).await?.into_inner();

        if !response.success {
            return Err(ClientError::StorageError(response.error));
        }

        debug!("Heuristic stored successfully");
        Ok(())
    }

    /// Query heuristics above a confidence threshold.
    /// Returns HeuristicMatch which includes similarity scores (CBR schema).
    #[instrument(skip(self))]
    pub async fn query_heuristics(
        &mut self,
        min_confidence: f32,
        limit: i32,
    ) -> Result<Vec<HeuristicMatch>, ClientError> {
        debug!("Querying heuristics");

        let request = QueryHeuristicsRequest {
            query_text: String::new(),      // Empty = get all
            query_embedding: Vec::new(),
            min_similarity: 0.0,
            min_confidence,
            limit,
        };

        let response = self.client.query_heuristics(request).await?.into_inner();

        if !response.error.is_empty() {
            return Err(ClientError::StorageError(response.error));
        }

        debug!(count = response.matches.len(), "Retrieved heuristics");
        Ok(response.matches)
    }

    /// Query heuristics matching event text using PostgreSQL full-text search.
    /// Used for cache-miss lookups - faster than embedding similarity.
    #[instrument(skip(self, event_text))]
    pub async fn query_matching_heuristics(
        &mut self,
        event_text: &str,
        min_confidence: f32,
        limit: i32,
        source_filter: Option<&str>,
    ) -> Result<Vec<HeuristicMatch>, ClientError> {
        debug!("Querying matching heuristics via text search");

        let request = QueryMatchingHeuristicsRequest {
            event_text: event_text.to_string(),
            min_confidence,
            limit,
            source_filter: source_filter.unwrap_or("").to_string(),
        };

        let request = self.add_trace_header(Request::new(request));
        let response = self.client.query_matching_heuristics(request).await?.into_inner();

        if !response.error.is_empty() {
            return Err(ClientError::StorageError(response.error));
        }

        debug!(count = response.matches.len(), "Retrieved matching heuristics");
        Ok(response.matches)
    }

    /// Get the client configuration.
    pub fn config(&self) -> &ClientConfig {
        &self.config
    }
}

// ============================================================================
// Embedding conversion utilities
// ============================================================================

/// Convert f32 slice to bytes (little-endian).
pub fn embedding_to_bytes(embedding: &[f32]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(embedding.len() * 4);
    for &value in embedding {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    bytes
}

/// Convert bytes to f32 vector (little-endian).
pub fn bytes_to_embedding(bytes: &[u8]) -> Vec<f32> {
    bytes
        .chunks_exact(4)
        .map(|chunk| {
            let arr: [u8; 4] = chunk.try_into().unwrap();
            f32::from_le_bytes(arr)
        })
        .collect()
}

// ============================================================================
// Builder helpers for protobuf messages
// ============================================================================

/// Builder for creating EpisodicEvent messages.
pub struct EventBuilder {
    event: EpisodicEvent,
}

impl EventBuilder {
    pub fn new(id: Uuid, source: &str, raw_text: &str) -> Self {
        Self {
            event: EpisodicEvent {
                id: id.to_string(),
                timestamp_ms: chrono_now_ms(),
                source: source.to_string(),
                raw_text: raw_text.to_string(),
                embedding: Vec::new(),
                salience: None,
                structured_json: "{}".to_string(),
                entity_ids: Vec::new(),
                // Prediction instrumentation (§27) - defaults to 0.0/empty
                predicted_success: 0.0,
                prediction_confidence: 0.0,
                response_id: String::new(),
                response_text: String::new(),
                matched_heuristic_id: String::new(),
            },
        }
    }

    pub fn timestamp_ms(mut self, ts: i64) -> Self {
        self.event.timestamp_ms = ts;
        self
    }

    pub fn embedding(mut self, embedding: &[f32]) -> Self {
        self.event.embedding = embedding_to_bytes(embedding);
        self
    }

    pub fn salience(mut self, salience: SalienceVector) -> Self {
        self.event.salience = Some(salience);
        self
    }

    pub fn structured_json(mut self, json: &str) -> Self {
        self.event.structured_json = json.to_string();
        self
    }

    pub fn entity_ids(mut self, ids: Vec<Uuid>) -> Self {
        self.event.entity_ids = ids.into_iter().map(|id| id.to_string()).collect();
        self
    }

    pub fn build(self) -> EpisodicEvent {
        self.event
    }
}

/// Builder for creating Heuristic messages (CBR schema).
pub struct HeuristicBuilder {
    heuristic: Heuristic,
}

impl HeuristicBuilder {
    pub fn new(id: Uuid, name: &str) -> Self {
        Self {
            heuristic: Heuristic {
                id: id.to_string(),
                name: name.to_string(),
                condition_text: String::new(),
                condition_embedding: Vec::new(),
                similarity_threshold: 0.7,
                effects_json: "{}".to_string(),
                confidence: 0.5,
                learning_rate: 0.1,
                origin: "user".to_string(),
                origin_id: String::new(),
                next_heuristic_ids: Vec::new(),
                is_terminal: true,
                last_fired_ms: 0,
                fire_count: 0,
                success_count: 0,
                created_at_ms: chrono_now_ms(),
                updated_at_ms: chrono_now_ms(),
            },
        }
    }

    pub fn condition_text(mut self, text: &str) -> Self {
        self.heuristic.condition_text = text.to_string();
        self
    }

    pub fn effects_json(mut self, json: &str) -> Self {
        self.heuristic.effects_json = json.to_string();
        self
    }

    pub fn confidence(mut self, confidence: f32) -> Self {
        self.heuristic.confidence = confidence;
        self
    }

    pub fn origin(mut self, origin: &str) -> Self {
        self.heuristic.origin = origin.to_string();
        self
    }

    pub fn build(self) -> Heuristic {
        self.heuristic
    }
}

/// Get current time as milliseconds since Unix epoch.
fn chrono_now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_millis() as i64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_embedding_roundtrip() {
        let original: Vec<f32> = (0..384).map(|i| i as f32 * 0.001).collect();
        let bytes = embedding_to_bytes(&original);
        let recovered = bytes_to_embedding(&bytes);
        assert_eq!(original.len(), recovered.len());
        for (a, b) in original.iter().zip(recovered.iter()) {
            assert!((a - b).abs() < 1e-6);
        }
    }

    #[test]
    fn test_event_builder() {
        let id = Uuid::new_v4();
        let event = EventBuilder::new(id, "test_sensor", "Something happened")
            .embedding(&[0.1, 0.2, 0.3])
            .structured_json(r#"{"key": "value"}"#)
            .build();

        assert_eq!(event.id, id.to_string());
        assert_eq!(event.source, "test_sensor");
        assert_eq!(event.raw_text, "Something happened");
        assert!(!event.embedding.is_empty());
    }

    #[test]
    fn test_heuristic_builder() {
        let id = Uuid::new_v4();
        let heuristic = HeuristicBuilder::new(id, "greet_user")
            .condition_text("user entered the room")
            .effects_json(r#"{"salience": {"social": 0.7}}"#)
            .confidence(0.9)
            .origin("test")
            .build();

        assert_eq!(heuristic.id, id.to_string());
        assert_eq!(heuristic.name, "greet_user");
        assert_eq!(heuristic.confidence, 0.9);
        assert_eq!(heuristic.condition_text, "user entered the room");
    }
}
