//! gRPC server implementation for SalienceGateway
//!
//! This module implements the SalienceGateway service, which evaluates
//! salience for incoming events using heuristics and novelty detection.

use std::sync::Arc;
use tokio::sync::RwLock;
use tonic::{Request, Response, Status};
use tracing::info;

use crate::config::{SalienceConfig, ServerConfig};
use crate::proto::salience_gateway_server::SalienceGateway;
use crate::proto::{EvaluateSalienceRequest, EvaluateSalienceResponse, SalienceVector};
use crate::{CachedHeuristic, MemoryCache};

/// The SalienceGateway service implementation.
///
/// This is the "amygdala" - it evaluates how important/urgent an event is
/// by checking heuristics (learned rules) and novelty (is this new?).
pub struct SalienceService {
    /// Shared reference to the in-memory cache.
    /// Arc = shared ownership across async tasks
    /// RwLock = multiple readers OR one writer at a time
    cache: Arc<RwLock<MemoryCache>>,
    /// Configuration for salience evaluation
    config: SalienceConfig,
}

impl SalienceService {
    /// Create a new SalienceService with the given cache and config.
    pub fn new(cache: Arc<RwLock<MemoryCache>>) -> Self {
        Self::with_config(cache, SalienceConfig::default())
    }

    /// Create a new SalienceService with explicit config.
    pub fn with_config(cache: Arc<RwLock<MemoryCache>>, config: SalienceConfig) -> Self {
        Self { cache, config }
    }

    /// Check if a heuristic matches the request.
    ///
    /// CBR-style word overlap matching for MVP.
    /// True CBR would use embedding similarity.
    ///
    /// NOTE: This is a placeholder implementation using naive word matching.
    /// Production should use embedding similarity via Python service.
    fn heuristic_matches(
        heuristic: &CachedHeuristic,
        request: &EvaluateSalienceRequest,
        config: &SalienceConfig,
    ) -> bool {
        let condition = &heuristic.condition;

        // CBR format: match by text keywords (word overlap)
        if let Some(condition_text) = condition.get("text").and_then(|v| v.as_str()) {
            let condition_lower = condition_text.to_lowercase();
            let request_lower = request.raw_text.to_lowercase();

            // Split into words, strip punctuation, and find overlap
            let condition_words: std::collections::HashSet<String> = condition_lower
                .split_whitespace()
                .map(|w| w.trim_matches(|c: char| !c.is_alphanumeric()).to_string())
                .filter(|w| !w.is_empty())
                .collect();
            let request_words: std::collections::HashSet<String> = request_lower
                .split_whitespace()
                .map(|w| w.trim_matches(|c: char| !c.is_alphanumeric()).to_string())
                .filter(|w| !w.is_empty())
                .collect();

            let overlap: std::collections::HashSet<_> =
                condition_words.intersection(&request_words).collect();

            // Match if overlap meets configured thresholds
            let min_overlap = std::cmp::max(
                config.min_word_overlap,
                (condition_words.len() as f32 * config.word_overlap_ratio) as usize,
            );
            return overlap.len() >= min_overlap;
        }

        // Legacy format: match by source if specified
        if let Some(source) = condition.get("source").and_then(|v| v.as_str()) {
            if source != request.source {
                return false;
            }
        }

        // Legacy format: match by keywords in raw_text
        if let Some(keywords) = condition.get("keywords").and_then(|v| v.as_array()) {
            let text_lower = request.raw_text.to_lowercase();
            let has_match = keywords.iter().any(|kw| {
                if let Some(keyword) = kw.as_str() {
                    text_lower.contains(&keyword.to_lowercase())
                } else {
                    false
                }
            });
            if !has_match {
                return false;
            }
        }

        true
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
        let mut from_cache = false;

        // Step 1: Check for matching heuristics
        {
            // Acquire read lock on cache
            let cache = self.cache.read().await;

            // Get high-confidence heuristics (using config threshold)
            let heuristics = cache.get_heuristics_by_confidence(self.config.min_heuristic_confidence);

            for h in heuristics {
                if Self::heuristic_matches(h, &req, &self.config) {
                    info!(
                        heuristic_id = %h.id,
                        heuristic_name = %h.name,
                        "Heuristic matched"
                    );
                    matched_heuristic_id = h.id.to_string();
                    from_cache = true;
                    Self::apply_heuristic_salience(&mut salience, h);
                    break;
                }
            }

            // Step 2: Novelty detection
            // For now, we don't have embeddings in the request, so we use
            // a simplified check. In production, we'd:
            // 1. Generate embedding for raw_text (via Python service)
            // 2. Check cache.is_novel(&embedding)
            //
            // For MVP, we boost novelty if no similar text was recently seen
            // This is a placeholder - real novelty needs embeddings
            if !req.raw_text.is_empty() && !from_cache {
                // No heuristic matched = potentially novel situation
                salience.novelty = salience.novelty.max(self.config.unmatched_novelty_boost);
            }
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
            from_cache,
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
pub async fn run_server(
    server_config: ServerConfig,
    salience_config: SalienceConfig,
    cache: Arc<RwLock<MemoryCache>>,
) -> Result<(), Box<dyn std::error::Error>> {
    use crate::proto::salience_gateway_server::SalienceGatewayServer;
    use tonic::transport::Server;

    let addr = format!("{}:{}", server_config.host, server_config.port).parse()?;
    let service = SalienceService::with_config(cache, salience_config);

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

    #[test]
    fn test_heuristic_keyword_matching() {
        let config = SalienceConfig::default();
        let heuristic = CachedHeuristic {
            id: uuid::Uuid::new_v4(),
            name: "threat_detector".to_string(),
            condition: serde_json::json!({
                "source": "test",
                "keywords": ["danger", "threat", "attack"]
            }),
            action: serde_json::json!({
                "salience": {
                    "threat": 0.9
                }
            }),
            confidence: 0.95,
        };

        // Should match - contains "danger"
        let request = EvaluateSalienceRequest {
            event_id: "test-1".to_string(),
            source: "test".to_string(),
            raw_text: "DANGER! Enemy approaching!".to_string(),
            structured_json: String::new(),
            entity_ids: vec![],
        };
        assert!(SalienceService::heuristic_matches(&heuristic, &request, &config));

        // Should not match - wrong source
        let request2 = EvaluateSalienceRequest {
            event_id: "test-2".to_string(),
            source: "other".to_string(),
            raw_text: "DANGER! Enemy approaching!".to_string(),
            structured_json: String::new(),
            entity_ids: vec![],
        };
        assert!(!SalienceService::heuristic_matches(&heuristic, &request2, &config));

        // Should not match - no keywords
        let request3 = EvaluateSalienceRequest {
            event_id: "test-3".to_string(),
            source: "test".to_string(),
            raw_text: "Everything is fine.".to_string(),
            structured_json: String::new(),
            entity_ids: vec![],
        };
        assert!(!SalienceService::heuristic_matches(&heuristic, &request3, &config));
    }

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
