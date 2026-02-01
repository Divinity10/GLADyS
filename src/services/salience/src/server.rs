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
use crate::{CachedHeuristic, MemoryCache};

/// The SalienceGateway service implementation.
///
/// This is the "amygdala" - it evaluates how important/urgent an event is
/// by checking heuristics (learned rules) and novelty (is this new?).
///
/// On cache miss, queries Python storage for matching heuristics.
pub struct SalienceService {
    /// Shared reference to the in-memory LRU cache.
    cache: Arc<RwLock<MemoryCache>>,
    /// Configuration for salience evaluation
    config: SalienceConfig,
    /// Storage configuration for querying Python on cache miss
    storage_config: Option<StorageConfig>,
    /// When the service was started (for uptime tracking)
    started_at: Instant,
}

impl SalienceService {
    /// Create a new SalienceService with the given cache and config.
    pub fn new(cache: Arc<RwLock<MemoryCache>>) -> Self {
        Self::with_config(cache, SalienceConfig::default(), None)
    }

    /// Create a new SalienceService with explicit config.
    pub fn with_config(
        cache: Arc<RwLock<MemoryCache>>,
        config: SalienceConfig,
        storage_config: Option<StorageConfig>,
    ) -> Self {
        Self { cache, config, storage_config, started_at: Instant::now() }
    }

    /// Query Python storage for matching heuristics.
    /// Returns a Result containing a vector of heuristics (empty if none found),
    /// or an error message if the query failed.
    async fn query_storage_for_heuristics(
        &self,
        event_text: &str,
        source_filter: Option<&str>,
        trace_id: Option<&str>,
    ) -> Result<Vec<CachedHeuristic>, String> {
        let storage_config = match self.storage_config.as_ref() {
            Some(cfg) => cfg,
            None => {
                warn!("No storage_config - cannot query Python for heuristics");
                return Err("No storage config".to_string());
            }
        };

        let client_config = ClientConfig {
            address: storage_config.address.clone(),
            connect_timeout: storage_config.connect_timeout(),
            request_timeout: storage_config.request_timeout(),
        };

        debug!(address = %storage_config.address, "Connecting to Python storage");

        let connect_result = StorageClient::connect(client_config).await;
        match connect_result {
            Ok(client) => {
                // Add trace ID for request correlation
                let mut client = if let Some(tid) = trace_id {
                    client.with_trace_id(tid.to_string())
                } else {
                    client
                };
                match client.query_matching_heuristics(
                    event_text,
                    self.config.min_heuristic_confidence,
                    10, // limit
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
                                // Parse condition_embedding from proto bytes
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
                                    cached_at_ms: 0, // Will be set by add_heuristic
                                    hit_count: 0,
                                    last_hit_ms: 0,
                                })
                            })
                            .collect();
                        debug!(count = heuristics.len(), "Heuristics after conversion");
                        Ok(heuristics)
                    }
                    Err(e) => {
                        let err_msg = format!("Failed to query storage for heuristics: {}", e);
                        warn!("{}", err_msg);
                        Err(err_msg)
                    }
                }
            }
            Err(e) => {
                let err_msg = format!("Failed to connect to Python storage: {}", e);
                warn!("{}", err_msg);
                Err(err_msg)
            }
        }
    }

    /// Generate an embedding for event text by calling Python's GenerateEmbedding RPC.
    /// Returns None if generation fails (graceful degradation → falls back to Python matching).
    async fn generate_event_embedding(
        &self,
        text: &str,
        trace_id: Option<&str>,
    ) -> Option<Vec<f32>> {
        let storage_config = self.storage_config.as_ref()?;

        let client_config = ClientConfig {
            address: storage_config.address.clone(),
            connect_timeout: storage_config.connect_timeout(),
            request_timeout: storage_config.request_timeout(),
        };

        match StorageClient::connect(client_config).await {
            Ok(mut client) => {
                if let Some(tid) = trace_id {
                    client = client.with_trace_id(tid.to_string());
                }
                match client.generate_embedding(text).await {
                    Ok(embedding) => {
                        debug!(dims = embedding.len(), "Generated event embedding");
                        Some(embedding)
                    }
                    Err(e) => {
                        warn!("Failed to generate embedding: {}", e);
                        None
                    }
                }
            }
            Err(e) => {
                warn!("Failed to connect for embedding generation: {}", e);
                None
            }
        }
    }

    /// Apply salience boosts from a matched heuristic.
    fn apply_heuristic_salience(salience: &mut SalienceVector, heuristic: &CachedHeuristic) {
        if let Some(salience_boost) = heuristic.action.get("salience") {
            if let Some(threat) = salience_boost.get("threat").and_then(|v| v.as_f64()) {
                salience.threat = salience.threat.max(threat as f32);
            }
            if let Some(opportunity) = salience_boost.get("opportunity").and_then(|v| v.as_f64()) {
                salience.opportunity = salience.opportunity.max(opportunity as f32);
            }
            if let Some(humor) = salience_boost.get("humor").and_then(|v| v.as_f64()) {
                salience.humor = salience.humor.max(humor as f32);
            }
            if let Some(novelty) = salience_boost.get("novelty").and_then(|v| v.as_f64()) {
                salience.novelty = salience.novelty.max(novelty as f32);
            }
            if let Some(goal_relevance) = salience_boost.get("goal_relevance").and_then(|v| v.as_f64()) {
                salience.goal_relevance = salience.goal_relevance.max(goal_relevance as f32);
            }
            if let Some(social) = salience_boost.get("social").and_then(|v| v.as_f64()) {
                salience.social = salience.social.max(social as f32);
            }
            if let Some(emotional) = salience_boost.get("emotional").and_then(|v| v.as_f64()) {
                salience.emotional = salience.emotional.max(emotional as f32);
            }
            if let Some(actionability) = salience_boost.get("actionability").and_then(|v| v.as_f64()) {
                salience.actionability = salience.actionability.max(actionability as f32);
            }
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
        let mut from_cache = false;

        // Cache-first heuristic matching:
        // 1. Generate embedding for event text (via Python)
        // 2. Check local cache using cosine similarity
        // 3. On cache miss, fall back to Python QueryMatchingHeuristics
        if !req.raw_text.is_empty() {
            // Step 1: Generate embedding for the event text
            let query_embedding = self.generate_event_embedding(&req.raw_text, Some(&trace_id)).await;

            // Step 2: Check cache if we have an embedding
            if let Some(ref embedding) = query_embedding {
                let cache = self.cache.read().await;
                let cache_matches = cache.find_matching_heuristics(
                    embedding,
                    self.config.min_heuristic_similarity,
                    self.config.min_heuristic_confidence,
                    1, // Only need best match
                );
                drop(cache);

                if let Some((h_id, similarity)) = cache_matches.first() {
                    // Cache hit - use cached heuristic
                    let mut cache = self.cache.write().await;
                    cache.record_hit();
                    cache.touch_heuristic(h_id);

                    if let Some(cached_h) = cache.get_heuristic(h_id) {
                        info!(
                            trace_id = %trace_id,
                            heuristic_id = %h_id,
                            heuristic_name = %cached_h.name,
                            similarity = %similarity,
                            "Heuristic matched (cache hit)"
                        );
                        matched_heuristic_id = h_id.to_string();
                        from_cache = true;
                        Self::apply_heuristic_salience(&mut salience, cached_h);
                    }
                }
            }

            // Step 3: Cache miss - fall back to Python storage
            if !from_cache {
                debug!("Cache miss, querying Python storage for heuristic matching");
                match self.query_storage_for_heuristics(&req.raw_text, None, Some(&trace_id)).await {
                    Ok(heuristics_from_storage) => {
                        let mut cache = self.cache.write().await;
                        cache.record_miss();

                        for h in heuristics_from_storage {
                            let h_id = h.id;
                            let h_name = h.name.clone();

                            // Add/update cache
                            if cache.get_heuristic(&h_id).is_some() {
                                cache.touch_heuristic(&h_id);
                            } else {
                                cache.add_heuristic(h);
                            }

                            // Use the first (best) match
                            if matched_heuristic_id.is_empty() {
                                if let Some(cached_h) = cache.get_heuristic(&h_id) {
                                    info!(
                                        trace_id = %trace_id,
                                        heuristic_id = %h_id,
                                        heuristic_name = %h_name,
                                        "Heuristic matched (storage fallback)"
                                    );
                                    matched_heuristic_id = h_id.to_string();
                                    from_cache = true; // Matched from storage, now cached
                                    Self::apply_heuristic_salience(&mut salience, cached_h);
                                }
                            }
                        }
                    },
                    Err(e) => {
                        return Ok(Response::new(EvaluateSalienceResponse {
                            salience: Some(salience),
                            from_cache: false,
                            matched_heuristic_id: String::new(),
                            error: e,
                            novelty_detection_skipped: true,
                        }));
                    }
                }
            }
        }

        // Novelty detection: If no heuristic matched, this is potentially novel
        if !from_cache && !req.raw_text.is_empty() {
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
            from_cache, // Heuristic match found (cache or storage fallback)
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
///
/// The storage_config is used for cache-miss queries to Python storage.
pub async fn run_server(
    server_config: ServerConfig,
    salience_config: SalienceConfig,
    storage_config: StorageConfig,
    cache: Arc<RwLock<MemoryCache>>,
) -> Result<(), Box<dyn std::error::Error>> {
    use crate::proto::salience_gateway_server::SalienceGatewayServer;
    use tonic::transport::Server;

    let addr = format!("{}:{}", server_config.host, server_config.port).parse()?;
    let service = SalienceService::with_config(cache, salience_config, Some(storage_config));

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

    // NOTE: test_heuristic_keyword_matching was removed because
    // heuristic matching is now done via Python's semantic similarity.
    // Word overlap matching has been deprecated due to false positives.

    #[test]
    fn test_apply_heuristic_salience() {
        let heuristic = CachedHeuristic {
            id: uuid::Uuid::new_v4(),
            name: "threat_detector".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({
                "salience": {
                    "threat": 0.9,
                    "opportunity": 0.3
                }
            }),
            confidence: 0.95,
            condition_embedding: Vec::new(),
            last_accessed_ms: 0,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        };

        let mut salience = SalienceVector {
            threat: 0.1,
            opportunity: 0.5, // Already higher than heuristic
            humor: 0.0,
            novelty: 0.0,
            goal_relevance: 0.0,
            social: 0.0,
            emotional: 0.0,
            actionability: 0.0,
            habituation: 0.0,
        };

        SalienceService::apply_heuristic_salience(&mut salience, &heuristic);

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
        let service = SalienceService::new(cache.clone());

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
