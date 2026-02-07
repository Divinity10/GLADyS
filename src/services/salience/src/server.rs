//! gRPC server implementation for SalienceGateway
//!
//! This module implements the SalienceGateway service, which evaluates
//! salience for incoming events using heuristics and novelty detection.
//!
//! Architecture:
//! - Always queries Python storage for semantic heuristic matching
//! - Python uses embedding similarity for accurate semantic matching
//! - Rust caches matched heuristics for metadata/stats (not for re-matching)
//! - LRU cache stores recently used heuristics for quick stat updates

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::RwLock;
use tonic::{Request, Response, Status};
use tracing::{info, debug, warn};

use crate::logging::get_or_create_trace_id;

use crate::config::{SalienceConfig, ServerConfig, StorageConfig};
use crate::client::{ClientConfig, StorageClient};
use crate::proto::salience_gateway_server::SalienceGateway;
use crate::proto::{
    EvaluateSalienceRequest, EvaluateSalienceResponse, SalienceVector,
    FlushCacheRequest, FlushCacheResponse, EvictFromCacheRequest, EvictFromCacheResponse,
    GetCacheStatsRequest, GetCacheStatsResponse, ListCachedHeuristicsRequest,
    ListCachedHeuristicsResponse, CachedHeuristicInfo,
    NotifyHeuristicChangeRequest, NotifyHeuristicChangeResponse,
};
use crate::proto::gladys::types::{
    GetHealthRequest, GetHealthResponse, GetHealthDetailsRequest, GetHealthDetailsResponse,
    HealthStatus,
};
use crate::{CachedHeuristic, MemoryCache, SalienceScorer, ScoredMatch, ScoringError, StorageBackend};

/// Default implementation of StorageBackend using gRPC to Python Memory service.
pub struct GrpcStorageBackend {
    config: StorageConfig,
}

impl GrpcStorageBackend {
    pub fn new(config: StorageConfig) -> Self {
        Self { config }
    }
}

#[tonic::async_trait]
impl StorageBackend for GrpcStorageBackend {
    async fn query_matching_heuristics(
        &self,
        event_text: &str,
        min_confidence: f32,
        limit: i32,
        source_filter: Option<&str>,
        trace_id: Option<&str>,
    ) -> Result<Vec<CachedHeuristic>, String> {
        let client_config = ClientConfig {
            address: self.config.address.clone(),
            connect_timeout: self.config.connect_timeout(),
            request_timeout: self.config.request_timeout(),
        };

        debug!(address = %self.config.address, "Connecting to Python storage");

        match StorageClient::connect(client_config).await {
            Ok(client) => {
                let mut client = if let Some(tid) = trace_id {
                    client.with_trace_id(tid.to_string())
                } else {
                    client
                };
                match client.query_matching_heuristics(
                    event_text,
                    min_confidence,
                    limit,
                    source_filter,
                ).await {
                    Ok(matches) => {
                        debug!(count = matches.len(), "Python returned matches");
                        let heuristics: Vec<CachedHeuristic> = matches
                            .into_iter()
                            .filter_map(|m| {
                                if m.heuristic.is_none() {
                                    warn!(similarity = m.similarity, "Match missing heuristic field");
                                    return None;
                                }
                                let h = m.heuristic?;
                                let id = match uuid::Uuid::parse_str(&h.id) {
                                    Ok(uuid) => uuid,
                                    Err(e) => {
                                        warn!(id = %h.id, error = %e, "Failed to parse heuristic UUID");
                                        return None;
                                    }
                                };
                                let condition = serde_json::json!({ "text": h.condition_text });
                                let action: serde_json::Value = match serde_json::from_str(&h.effects_json) {
                                    Ok(v) => v,
                                    Err(e) => {
                                        warn!(id = %h.id, error = %e, "Failed to parse effects JSON");
                                        serde_json::json!({})
                                    }
                                };
                                let condition_embedding = if !h.condition_embedding.is_empty() {
                                    crate::client::bytes_to_embedding(&h.condition_embedding)
                                } else {
                                    Vec::new()
                                };

                                Some(CachedHeuristic {
                                    id,
                                    name: h.name,
                                    condition,
                                    action,
                                    confidence: h.confidence,
                                    condition_embedding,
                                    last_accessed_ms: 0,
                                    cached_at_ms: 0,
                                    hit_count: 0,
                                    last_hit_ms: 0,
                                })
                            })
                            .collect();
                        Ok(heuristics)
                    }
                    Err(e) => Err(format!("Failed to query storage for heuristics: {}", e)),
                }
            }
            Err(e) => Err(format!("Failed to connect to Python storage: {}", e)),
        }
    }

    async fn generate_embedding(
        &self,
        text: &str,
        trace_id: Option<&str>,
    ) -> Result<Vec<f32>, String> {
        let client_config = ClientConfig {
            address: self.config.address.clone(),
            connect_timeout: self.config.connect_timeout(),
            request_timeout: self.config.request_timeout(),
        };

        match StorageClient::connect(client_config).await {
            Ok(mut client) => {
                if let Some(tid) = trace_id {
                    client = client.with_trace_id(tid.to_string());
                }
                client.generate_embedding(text).await
                    .map_err(|e| format!("Failed to generate embedding: {}", e))
            }
            Err(e) => Err(format!("Failed to connect for embedding generation: {}", e)),
        }
    }
}

/// Current PoC 1 scorer — embedding + cosine similarity.
pub struct EmbeddingSimilarityScorer {
    cache: Arc<RwLock<MemoryCache>>,
    storage: Box<dyn StorageBackend>,
    min_similarity: f32,
    min_confidence: f32,
}

impl EmbeddingSimilarityScorer {
    pub fn new(
        cache: Arc<RwLock<MemoryCache>>,
        storage: Box<dyn StorageBackend>,
        min_similarity: f32,
        min_confidence: f32,
    ) -> Self {
        Self { cache, storage, min_similarity, min_confidence }
    }
}

#[tonic::async_trait]
impl SalienceScorer for EmbeddingSimilarityScorer {
    async fn score(
        &self,
        event_text: &str,
        _source: &str,
        trace_id: Option<&str>,
    ) -> Result<Vec<ScoredMatch>, ScoringError> {
        if event_text.is_empty() {
            return Ok(vec![]);
        }

        // Step 1: Generate embedding for the event text
        let embedding_result = self.storage.generate_embedding(event_text, trace_id).await;

        if let Ok(embedding) = embedding_result {
            // Step 2: Cache lookup using cosine similarity
            let cache = self.cache.read().await;
            let cache_matches = cache.find_matching_heuristics(
                &embedding,
                self.min_similarity,
                self.min_confidence,
                5,
            );
            drop(cache);

            if !cache_matches.is_empty() {
                let cache = self.cache.read().await;
                let results = cache_matches.into_iter().filter_map(|(h_id, sim)| {
                    cache.get_heuristic(&h_id).map(|h| ScoredMatch {
                        heuristic_id: h.id.to_string(),
                        similarity: sim,
                        confidence: h.confidence,
                        condition_text: h.condition.get("text").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                        suggested_action: h.action.get("message").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                        salience_boost: h.action.get("salience").cloned(),
                    })
                }).collect();
                return Ok(results);
            }
        } else if let Err(e) = embedding_result {
            warn!(trace_id = ?trace_id, error = %e, "Embedding failed, falling back to storage query");
        }

        // Step 3: Cache miss or embedding failure - fall back to storage
        debug!("Querying storage for heuristic matching");
        let heuristics = self.storage.query_matching_heuristics(
            event_text,
            self.min_confidence,
            10,
            None,
            trace_id
        ).await.map_err(|e| ScoringError::StorageError(e))?;

        // Cache warming: add results to cache so future lookups find them locally
        if !heuristics.is_empty() {
            let mut cache = self.cache.write().await;
            for h in &heuristics {
                cache.add_heuristic(h.clone());
            }
        }

        Ok(heuristics.into_iter().map(|h| ScoredMatch {
            heuristic_id: h.id.to_string(),
            similarity: 1.0, // Storage returns pre-filtered matches
            confidence: h.confidence,
            condition_text: h.condition.get("text").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            suggested_action: h.action.get("message").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            salience_boost: h.action.get("salience").cloned(),
        }).collect())
    }

    fn config(&self) -> serde_json::Value {
        serde_json::json!({
            "scorer": "embedding_similarity",
            "min_similarity": self.min_similarity,
            "min_confidence": self.min_confidence,
        })
    }
}

/// The SalienceGateway service implementation.
///
/// This is the "amygdala" - it evaluates how important/urgent an event is
/// by checking heuristics (learned rules) and novelty (is this new?).
pub struct SalienceService {
    /// Shared reference to the in-memory LRU cache.
    cache: Arc<RwLock<MemoryCache>>,
    /// Scoring algorithm implementation.
    scorer: Box<dyn SalienceScorer>,
    /// Configuration for salience evaluation
    config: SalienceConfig,
    /// When the service was started (for uptime tracking)
    started_at: Instant,
}

impl SalienceService {
    /// Create a new SalienceService with a scorer and config.
    pub fn with_scorer(
        cache: Arc<RwLock<MemoryCache>>,
        scorer: Box<dyn SalienceScorer>,
        config: SalienceConfig,
    ) -> Self {
        Self { cache, scorer, config, started_at: Instant::now() }
    }

    /// Apply salience boosts from a scored match.
    fn apply_salience_boost(salience: &mut SalienceVector, boost: &serde_json::Value) {
        if let Some(threat) = boost.get("threat").and_then(|v| v.as_f64()) {
            salience.threat = salience.threat.max(threat as f32);
        }
        if let Some(opportunity) = boost.get("opportunity").and_then(|v| v.as_f64()) {
            salience.opportunity = salience.opportunity.max(opportunity as f32);
        }
        if let Some(humor) = boost.get("humor").and_then(|v| v.as_f64()) {
            salience.humor = salience.humor.max(humor as f32);
        }
        if let Some(novelty) = boost.get("novelty").and_then(|v| v.as_f64()) {
            salience.novelty = salience.novelty.max(novelty as f32);
        }
        if let Some(goal_relevance) = boost.get("goal_relevance").and_then(|v| v.as_f64()) {
            salience.goal_relevance = salience.goal_relevance.max(goal_relevance as f32);
        }
        if let Some(social) = boost.get("social").and_then(|v| v.as_f64()) {
            salience.social = salience.social.max(social as f32);
        }
        if let Some(emotional) = boost.get("emotional").and_then(|v| v.as_f64()) {
            salience.emotional = salience.emotional.max(emotional as f32);
        }
        if let Some(actionability) = boost.get("actionability").and_then(|v| v.as_f64()) {
            salience.actionability = salience.actionability.max(actionability as f32);
        }
    }
}

/// Implement the gRPC SalienceGateway trait for our service.
///
/// The #[tonic::async_trait] macro handles the async trait complexity.
/// In Rust, async functions in traits require special handling.
#[tonic::async_trait]
impl SalienceGateway for SalienceService {
    /// Evaluate the salience of an incoming event.
    ///
    /// This is called by the Orchestrator for every event to determine
    /// whether it should be routed immediately (high salience) or
    /// accumulated into a "moment" (low salience).
    async fn evaluate_salience(
        &self,
        request: Request<EvaluateSalienceRequest>,
    ) -> Result<Response<EvaluateSalienceResponse>, Status> {
        let trace_id = get_or_create_trace_id(&request);
        let req = request.into_inner();
        info!(
            trace_id = %trace_id,
            event_id = %req.event_id,
            source = %req.source,
            "Evaluating salience"
        );

        // Start with default salience values (using config)
        let mut salience = SalienceVector {
            threat: 0.0,
            opportunity: 0.0,
            humor: 0.0,
            novelty: self.config.baseline_novelty,
            goal_relevance: 0.0,
            social: 0.0,
            emotional: 0.0,
            actionability: 0.0,
            habituation: 0.0,
        };

        let mut matched_heuristic_id = String::new();
        let mut heuristic_matched = false;

        // Delegate scoring to the strategy
        if !req.raw_text.is_empty() {
            match self.scorer.score(&req.raw_text, &req.source, Some(&trace_id)).await {
                Ok(matches) if !matches.is_empty() => {
                    // Use the first (best) match
                    let best = &matches[0];
                    matched_heuristic_id = best.heuristic_id.clone();
                    heuristic_matched = true;

                    info!(
                        trace_id = %trace_id,
                        heuristic_id = %best.heuristic_id,
                        similarity = %best.similarity,
                        "Heuristic matched"
                    );

                    // Apply salience boost
                    if let Some(boost) = &best.salience_boost {
                        Self::apply_salience_boost(&mut salience, boost);
                    }

                    // Cache bookkeeping:
                    // If similarity is 1.0, it was a storage match that we should add to cache.
                    // If similarity is < 1.0, it was likely a cache match (or we should check if it's in cache).
                    let h_uuid = uuid::Uuid::parse_str(&best.heuristic_id).ok();
                    if let Some(id) = h_uuid {
                        let mut cache = self.cache.write().await;
                        if best.similarity >= 1.0 {
                            // Storage match
                            cache.record_miss();
                            cache.touch_heuristic(&id);
                        } else {
                            // Cache match
                            cache.record_hit();
                            cache.touch_heuristic(&id);
                        }
                    }
                }
                Ok(_) => {
                    // No matches found
                    salience.novelty = salience.novelty.max(self.config.unmatched_novelty_boost);
                }
                Err(e) => {
                    warn!(trace_id = %trace_id, error = %e, "Scoring failed");
                    salience.novelty = salience.novelty.max(self.config.unmatched_novelty_boost);
                    
                    return Ok(Response::new(EvaluateSalienceResponse {
                        salience: Some(salience),
                        from_cache: false,
                        matched_heuristic_id: String::new(),
                        error: e.to_string(),
                        novelty_detection_skipped: true,
                    }));
                }
            }
        }

        // Novelty detection: If no heuristic matched, this is potentially novel
        if !heuristic_matched && !req.raw_text.is_empty() {
            salience.novelty = salience.novelty.max(self.config.unmatched_novelty_boost);
        }

        info!(
            trace_id = %trace_id,
            event_id = %req.event_id,
            threat = salience.threat,
            novelty = salience.novelty,
            matched = %matched_heuristic_id,
            "Salience evaluated"
        );

        Ok(Response::new(EvaluateSalienceResponse {
            salience: Some(salience),
            from_cache: heuristic_matched,
            matched_heuristic_id,
            error: String::new(),
            // Rust fast path never does novelty detection (no embedding model)
            novelty_detection_skipped: true,
        }))
    }

    /// Clear entire heuristic cache
    async fn flush_cache(
        &self,
        _request: Request<FlushCacheRequest>,
    ) -> Result<Response<FlushCacheResponse>, Status> {
        info!("Flushing heuristic cache");
        let mut cache = self.cache.write().await;
        let entries_flushed = cache.flush_heuristics() as i32;
        Ok(Response::new(FlushCacheResponse { entries_flushed }))
    }

    /// Remove single heuristic from cache
    async fn evict_from_cache(
        &self,
        request: Request<EvictFromCacheRequest>,
    ) -> Result<Response<EvictFromCacheResponse>, Status> {
        let req = request.into_inner();
        let id = uuid::Uuid::parse_str(&req.heuristic_id)
            .map_err(|e| Status::invalid_argument(format!("Invalid UUID: {}", e)))?;

        info!(heuristic_id = %id, "Evicting heuristic from cache");
        let mut cache = self.cache.write().await;
        let found = cache.remove_heuristic(&id);
        Ok(Response::new(EvictFromCacheResponse { found }))
    }

    /// Get cache performance statistics
    async fn get_cache_stats(
        &self,
        _request: Request<GetCacheStatsRequest>,
    ) -> Result<Response<GetCacheStatsResponse>, Status> {
        let cache = self.cache.read().await;
        let stats = cache.stats();
        Ok(Response::new(GetCacheStatsResponse {
            current_size: stats.heuristic_count as i32,
            max_capacity: stats.max_heuristics as i32,
            hit_rate: stats.hit_rate(),
            total_hits: stats.total_hits as i64,
            total_misses: stats.total_misses as i64,
        }))
    }

    /// List heuristics currently in cache
    async fn list_cached_heuristics(
        &self,
        request: Request<ListCachedHeuristicsRequest>,
    ) -> Result<Response<ListCachedHeuristicsResponse>, Status> {
        let req = request.into_inner();
        let cache = self.cache.read().await;
        let heuristics = cache.list_heuristics(req.limit as usize);

        let info = heuristics
            .into_iter()
            .map(|h| CachedHeuristicInfo {
                heuristic_id: h.id.to_string(),
                name: h.name.clone(),
                hit_count: h.hit_count as i32,
                cached_at_unix: h.cached_at_ms / 1000,
                last_hit_unix: h.last_hit_ms / 1000,
            })
            .collect();

        Ok(Response::new(ListCachedHeuristicsResponse {
            heuristics: info,
        }))
    }

    /// Handle heuristic change notification from Memory service.
    /// On "created"/"updated": evict stale entry so next request re-fetches from Python.
    /// On "deleted": evict from cache.
    async fn notify_heuristic_change(
        &self,
        request: Request<NotifyHeuristicChangeRequest>,
    ) -> Result<Response<NotifyHeuristicChangeResponse>, Status> {
        let req = request.into_inner();
        let change_type = req.change_type.as_str();

        info!(
            heuristic_id = %req.heuristic_id,
            change_type = %change_type,
            "Heuristic change notification received"
        );

        let id = uuid::Uuid::parse_str(&req.heuristic_id)
            .map_err(|e| Status::invalid_argument(format!("Invalid UUID: {}", e)))?;

        match change_type {
            "created" | "updated" => {
                // Evict stale entry; next evaluate_salience will re-fetch from Python
                let mut cache = self.cache.write().await;
                cache.remove_heuristic(&id);
            }
            "deleted" => {
                let mut cache = self.cache.write().await;
                cache.remove_heuristic(&id);
            }
            _ => {
                warn!(change_type = %change_type, "Unknown change type, evicting as safety measure");
                let mut cache = self.cache.write().await;
                cache.remove_heuristic(&id);
            }
        }

        Ok(Response::new(NotifyHeuristicChangeResponse { success: true }))
    }

    /// Basic health check
    async fn get_health(
        &self,
        _request: Request<GetHealthRequest>,
    ) -> Result<Response<GetHealthResponse>, Status> {
        Ok(Response::new(GetHealthResponse {
            status: HealthStatus::Healthy.into(),
            message: String::new(),
        }))
    }

    /// Detailed health check with uptime and metrics
    async fn get_health_details(
        &self,
        _request: Request<GetHealthDetailsRequest>,
    ) -> Result<Response<GetHealthDetailsResponse>, Status> {
        let cache = self.cache.read().await;
        let stats = cache.stats();
        let uptime = self.started_at.elapsed().as_secs() as i64;

        let mut details = HashMap::new();
        details.insert("cache_size".to_string(), stats.heuristic_count.to_string());
        details.insert("cache_capacity".to_string(), stats.max_heuristics.to_string());
        details.insert("cache_hit_rate".to_string(), format!("{:.2}", stats.hit_rate()));
        details.insert("total_hits".to_string(), stats.total_hits.to_string());
        details.insert("total_misses".to_string(), stats.total_misses.to_string());

        Ok(Response::new(GetHealthDetailsResponse {
            status: HealthStatus::Healthy.into(),
            uptime_seconds: uptime,
            details,
        }))
    }
}

// ServerConfig is defined in config module and re-exported from lib.rs

/// Start the gRPC server.
///
/// This function creates the tonic server, registers our SalienceGateway
/// service, and listens for incoming connections.
pub async fn run_server(
    server_config: ServerConfig,
    salience_config: SalienceConfig,
    scorer: Box<dyn SalienceScorer>,
    cache: Arc<RwLock<MemoryCache>>,
) -> Result<(), Box<dyn std::error::Error>> {
    use crate::proto::salience_gateway_server::SalienceGatewayServer;
    use tonic::transport::Server;

    let addr = format!("{}:{}", server_config.host, server_config.port).parse()?;
    let service = SalienceService::with_scorer(cache, scorer, salience_config);

    info!("Starting SalienceGateway gRPC server on {}", addr);

    Server::builder()
        .add_service(SalienceGatewayServer::new(service))
        .serve(addr)
        .await?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    struct MockStorageBackend {
        heuristics: Vec<CachedHeuristic>,
        embedding: Vec<f32>,
        should_fail_embedding: bool,
        should_fail_query: bool,
    }

    #[tonic::async_trait]
    impl StorageBackend for MockStorageBackend {
        async fn query_matching_heuristics(
            &self,
            _text: &str,
            _min_conf: f32,
            _limit: i32,
            _source: Option<&str>,
            _trace_id: Option<&str>,
        ) -> Result<Vec<CachedHeuristic>, String> {
            if self.should_fail_query {
                return Err("Mock query failure".into());
            }
            Ok(self.heuristics.clone())
        }

        async fn generate_embedding(
            &self,
            _text: &str,
            _trace_id: Option<&str>,
        ) -> Result<Vec<f32>, String> {
            if self.should_fail_embedding {
                return Err("Mock embedding failure".into());
            }
            Ok(self.embedding.clone())
        }
    }

    #[tokio::test]
    async fn test_scorer_empty_text() {
        let cache = Arc::new(RwLock::new(MemoryCache::new(crate::config::CacheConfig::default())));
        let mock_storage = Box::new(MockStorageBackend {
            heuristics: vec![],
            embedding: vec![],
            should_fail_embedding: false,
            should_fail_query: false,
        });
        let scorer = EmbeddingSimilarityScorer::new(cache, mock_storage, 0.7, 0.5);

        let results = scorer.score("", "test", None).await.unwrap();
        assert!(results.is_empty());
    }

    #[tokio::test]
    async fn test_scorer_cache_hit() {
        let cache_config = crate::config::CacheConfig::default();
        let cache = Arc::new(RwLock::new(MemoryCache::new(cache_config)));
        
        let h_id = Uuid::new_v4();
        let emb = vec![1.0; 384];
        {
            let mut c = cache.write().await;
            c.add_heuristic(CachedHeuristic {
                id: h_id,
                name: "test_heuristic".to_string(),
                condition: serde_json::json!({"text": "test condition"}),
                action: serde_json::json!({"message": "test action", "salience": {"threat": 0.5}}),
                confidence: 0.9,
                condition_embedding: emb.clone(),
                last_accessed_ms: 0,
                cached_at_ms: 0,
                hit_count: 0,
                last_hit_ms: 0,
            });
        }

        let mock_storage = Box::new(MockStorageBackend {
            heuristics: vec![],
            embedding: emb.clone(),
            should_fail_embedding: false,
            should_fail_query: false,
        });

        let scorer = EmbeddingSimilarityScorer::new(cache, mock_storage, 0.7, 0.5);
        let results = scorer.score("test event", "test", None).await.unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].heuristic_id, h_id.to_string());
        assert!(results[0].similarity > 0.99);
        assert_eq!(results[0].suggested_action, "test action");
    }

    #[tokio::test]
    async fn test_scorer_storage_fallback() {
        let cache = Arc::new(RwLock::new(MemoryCache::new(crate::config::CacheConfig::default())));
        
        let h_id = Uuid::new_v4();
        let emb = vec![1.0; 384];
        let storage_heuristic = CachedHeuristic {
            id: h_id,
            name: "storage_heuristic".to_string(),
            condition: serde_json::json!({"text": "storage condition"}),
            action: serde_json::json!({"message": "storage action"}),
            confidence: 0.8,
            condition_embedding: vec![],
            last_accessed_ms: 0,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        };

        let mock_storage = Box::new(MockStorageBackend {
            heuristics: vec![storage_heuristic],
            embedding: emb,
            should_fail_embedding: false,
            should_fail_query: false,
        });

        let scorer = EmbeddingSimilarityScorer::new(cache, mock_storage, 0.7, 0.5);
        let results = scorer.score("test event", "test", None).await.unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].heuristic_id, h_id.to_string());
        assert_eq!(results[0].similarity, 1.0); // Storage fallback uses 1.0
        assert_eq!(results[0].suggested_action, "storage action");
    }

    #[tokio::test]
    async fn test_storage_match_warms_cache() {
        let cache = Arc::new(RwLock::new(MemoryCache::new(crate::config::CacheConfig::default())));
        
        let h_id = Uuid::new_v4();
        let storage_heuristic = CachedHeuristic {
            id: h_id,
            name: "storage_heuristic".to_string(),
            condition: serde_json::json!({"text": "storage condition"}),
            action: serde_json::json!({"message": "storage action"}),
            confidence: 0.8,
            condition_embedding: vec![1.0; 384],
            last_accessed_ms: 0,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        };

        let mock_storage = Box::new(MockStorageBackend {
            heuristics: vec![storage_heuristic],
            embedding: vec![1.0; 384],
            should_fail_embedding: false,
            should_fail_query: false,
        });

        let scorer = EmbeddingSimilarityScorer::new(cache.clone(), mock_storage, 0.7, 0.5);
        
        // 1. Initial check: cache is empty
        {
            let c = cache.read().await;
            assert!(c.get_heuristic(&h_id).is_none());
        }

        // 2. Score (should hit storage and warm cache)
        let _ = scorer.score("test event", "test", None).await.unwrap();

        // 3. Verify cache is now warmed
        {
            let c = cache.read().await;
            assert!(c.get_heuristic(&h_id).is_some());
            assert_eq!(c.get_heuristic(&h_id).unwrap().name, "storage_heuristic");
        }
    }

    #[tokio::test]
    async fn test_embedding_failure_falls_back_to_storage() {
        let cache = Arc::new(RwLock::new(MemoryCache::new(crate::config::CacheConfig::default())));
        
        let h_id = Uuid::new_v4();
        let storage_heuristic = CachedHeuristic {
            id: h_id,
            name: "storage_heuristic".to_string(),
            condition: serde_json::json!({"text": "storage condition"}),
            action: serde_json::json!({"message": "storage action"}),
            confidence: 0.8,
            condition_embedding: vec![],
            last_accessed_ms: 0,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        };

        let mock_storage = Box::new(MockStorageBackend {
            heuristics: vec![storage_heuristic],
            embedding: vec![],
            should_fail_embedding: true, // Force embedding failure
            should_fail_query: false,
        });

        let scorer = EmbeddingSimilarityScorer::new(cache, mock_storage, 0.7, 0.5);
        
        // Should NOT return error, should fall back to storage
        let results = scorer.score("test event", "test", None).await.unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].heuristic_id, h_id.to_string());
        assert_eq!(results[0].similarity, 1.0);
    }

    #[test]
    fn test_apply_salience_boost() {
        let boost = serde_json::json!({
            "threat": 0.9,
            "opportunity": 0.3
        });

        let mut salience = SalienceVector {
            threat: 0.1,
            opportunity: 0.5, // Already higher than boost
            humor: 0.0,
            novelty: 0.0,
            goal_relevance: 0.0,
            social: 0.0,
            emotional: 0.0,
            actionability: 0.0,
            habituation: 0.0,
        };

        SalienceService::apply_salience_boost(&mut salience, &boost);

        // Threat should be boosted to 0.9
        assert!((salience.threat - 0.9).abs() < 0.001);
        // Opportunity should stay at 0.5 (was already higher)
        assert!((salience.opportunity - 0.5).abs() < 0.001);
    }

    #[tokio::test]
    async fn test_cache_management_rpcs() {
        let cache_config = crate::config::CacheConfig {
            max_events: 10,
            max_heuristics: 5,
            novelty_threshold: 0.9,
            heuristic_ttl_ms: 0,
        };
        let cache = Arc::new(RwLock::new(MemoryCache::new(cache_config)));
        
        let mock_storage = Box::new(MockStorageBackend {
            heuristics: vec![],
            embedding: vec![],
            should_fail_embedding: false,
            should_fail_query: false,
        });
        let scorer = Box::new(EmbeddingSimilarityScorer::new(cache.clone(), mock_storage, 0.7, 0.5));
        let service = SalienceService::with_scorer(cache.clone(), scorer, SalienceConfig::default());

        // 1. Add some heuristics to cache
        let id1 = uuid::Uuid::new_v4();
        let id2 = uuid::Uuid::new_v4();
        {
            let mut c = cache.write().await;
            c.add_heuristic(CachedHeuristic {
                id: id1,
                name: "h1".to_string(),
                condition: serde_json::json!({}),
                action: serde_json::json!({}),
                confidence: 0.9,
                condition_embedding: Vec::new(),
                last_accessed_ms: 1000,
                cached_at_ms: 1000,
                hit_count: 5,
                last_hit_ms: 1000,
            });
            c.add_heuristic(CachedHeuristic {
                id: id2,
                name: "h2".to_string(),
                condition: serde_json::json!({}),
                action: serde_json::json!({}),
                confidence: 0.8,
                condition_embedding: Vec::new(),
                last_accessed_ms: 2000,
                cached_at_ms: 2000,
                hit_count: 2,
                last_hit_ms: 2000,
            });
            c.record_hit();
            c.record_miss();
        }

        // 2. Test ListCachedHeuristics
        let list_req = Request::new(ListCachedHeuristicsRequest { limit: 0 });
        let list_resp = service.list_cached_heuristics(list_req).await.unwrap().into_inner();
        assert_eq!(list_resp.heuristics.len(), 2);
        
        // 3. Test GetCacheStats
        let stats_req = Request::new(GetCacheStatsRequest {});
        let stats_resp = service.get_cache_stats(stats_req).await.unwrap().into_inner();
        assert_eq!(stats_resp.current_size, 2);
        assert_eq!(stats_resp.total_hits, 1);
        assert_eq!(stats_resp.total_misses, 1);

        // 4. Test EvictFromCache
        let evict_req = Request::new(EvictFromCacheRequest { heuristic_id: id1.to_string() });
        let evict_resp = service.evict_from_cache(evict_req).await.unwrap().into_inner();
        assert!(evict_resp.found);
        
        {
            let c = cache.read().await;
            assert_eq!(c.stats().heuristic_count, 1);
            assert!(c.get_heuristic(&id1).is_none());
        }

        // 5. Test FlushCache
        let flush_req = Request::new(FlushCacheRequest {});
        let flush_resp = service.flush_cache(flush_req).await.unwrap().into_inner();
        assert_eq!(flush_resp.entries_flushed, 1);
        
        {
            let c = cache.read().await;
            assert_eq!(c.stats().heuristic_count, 0);
        }
    }
}
