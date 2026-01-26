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

use std::sync::Arc;
use tokio::sync::RwLock;
use tonic::{Request, Response, Status};
use tracing::{info, debug, warn};

use crate::config::{SalienceConfig, ServerConfig, StorageConfig};
use crate::client::{ClientConfig, StorageClient};
use crate::proto::salience_gateway_server::SalienceGateway;
use crate::proto::{EvaluateSalienceRequest, EvaluateSalienceResponse, SalienceVector};
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
        Self { cache, config, storage_config }
    }

    /// Query Python storage for matching heuristics.
    /// Returns matched heuristics if found.
    async fn query_storage_for_heuristics(
        &self,
        event_text: &str,
        source_filter: Option<&str>,
    ) -> Option<Vec<CachedHeuristic>> {
        let storage_config = self.storage_config.as_ref()?;

        let client_config = ClientConfig {
            address: storage_config.address.clone(),
            connect_timeout: storage_config.connect_timeout(),
            request_timeout: storage_config.request_timeout(),
        };

        match StorageClient::connect(client_config).await {
            Ok(mut client) => {
                match client.query_matching_heuristics(
                    event_text,
                    self.config.min_heuristic_confidence,
                    10, // limit
                    source_filter,
                ).await {
                    Ok(matches) => {
                        let heuristics: Vec<CachedHeuristic> = matches
                            .into_iter()
                            .filter_map(|m| {
                                let h = m.heuristic?;
                                let id = uuid::Uuid::parse_str(&h.id).ok()?;
                                let condition = serde_json::json!({ "text": h.condition_text });
                                let action: serde_json::Value = serde_json::from_str(&h.effects_json)
                                    .unwrap_or(serde_json::json!({}));
                                Some(CachedHeuristic {
                                    id,
                                    name: h.name,
                                    condition,
                                    action,
                                    confidence: h.confidence,
                                    last_accessed_ms: 0,
                                    cached_at_ms: 0, // Will be set by add_heuristic
                                })
                            })
                            .collect();
                        if heuristics.is_empty() {
                            None
                        } else {
                            debug!(count = heuristics.len(), "Found heuristics from storage");
                            Some(heuristics)
                        }
                    }
                    Err(e) => {
                        warn!("Failed to query storage for heuristics: {}", e);
                        None
                    }
                }
            }
            Err(e) => {
                warn!("Failed to connect to storage: {}", e);
                None
            }
        }
    }

    // NOTE: Word overlap matching has been removed.
    // All heuristic matching is now done via Python's semantic similarity
    // using embeddings. This is more accurate and avoids false positives
    // from sentences that share structural words but have different meanings.
    // Example: "email about killing neighbor" should NOT match "email about meeting"
    // even though they share words like "email", "about", etc.

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
        let req = request.into_inner();
        info!(
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
        let mut from_storage = false;

        // Always query Python storage for semantic heuristic matching.
        // Python uses embedding similarity which is more accurate than word overlap.
        // The local cache is only used for storing heuristics for metadata/stats.
        if !req.raw_text.is_empty() {
            debug!("Querying Python storage for semantic heuristic matching");
            let source_filter = if req.source.is_empty() { None } else { Some(req.source.as_str()) };
            if let Some(heuristics_from_storage) = self.query_storage_for_heuristics(&req.raw_text, source_filter).await {
                // Add to local cache for stats tracking
                let mut cache = self.cache.write().await;
                for h in heuristics_from_storage {
                    let h_id = h.id;
                    let h_name = h.name.clone();
                    cache.add_heuristic(h);

                    // Use the first (best) match from storage
                    // Python returns results ordered by semantic similarity
                    if matched_heuristic_id.is_empty() {
                        if let Some(cached_h) = cache.get_heuristic(&h_id) {
                            info!(
                                heuristic_id = %h_id,
                                heuristic_name = %h_name,
                                "Heuristic matched (semantic similarity)"
                            );
                            matched_heuristic_id = h_id.to_string();
                            from_storage = true;
                            Self::apply_heuristic_salience(&mut salience, cached_h);
                        }
                    }
                }
            }
        }

        // Novelty detection: If no heuristic matched, this is potentially novel
        if !from_storage && !req.raw_text.is_empty() {
            salience.novelty = salience.novelty.max(self.config.unmatched_novelty_boost);
        }

        info!(
            event_id = %req.event_id,
            threat = salience.threat,
            novelty = salience.novelty,
            matched = %matched_heuristic_id,
            "Salience evaluated"
        );

        Ok(Response::new(EvaluateSalienceResponse {
            salience: Some(salience),
            from_cache: from_storage, // Semantic match found from storage
            matched_heuristic_id,
            error: String::new(),
            // Rust fast path never does novelty detection (no embedding model)
            novelty_detection_skipped: true,
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
            last_accessed_ms: 0,
            cached_at_ms: 0,
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
}
