//! GLADyS Memory Subsystem - Fast Path
//!
//! This crate implements the Rust fast path for the Memory subsystem.
//! It handles:
//! - L0 in-memory cache for recent events
//! - Novelty detection (embedding similarity)
//! - Heuristic lookup (System 1 fast rules)
//! - gRPC server for SalienceGateway service
//! - gRPC client to Python storage backend

use std::collections::HashMap;
use uuid::Uuid;

pub mod client;
pub mod config;
pub mod logging;
pub mod server;
/// Proto-generated types, organized by package.
///
/// The module hierarchy matches the proto package hierarchy:
/// - gladys.types -> proto::gladys::types
/// - gladys.memory -> proto::gladys::memory
pub mod proto {
    /// Container module matching the `gladys.*` proto packages
    pub mod gladys {
        /// Shared types from types.proto (package gladys.types)
        pub mod types {
            tonic::include_proto!("gladys.types");
        }
        /// Memory service from memory.proto (package gladys.memory)
        pub mod memory {
            tonic::include_proto!("gladys.memory");
        }
    }

    // Re-export commonly used types at proto level for convenience
    pub use gladys::types::SalienceVector;
    pub use gladys::memory::*;
}

// Re-export types from modules
pub use client::{ClientConfig, ClientError, StorageClient, EventBuilder, HeuristicBuilder};
pub use config::{Config, ServerConfig, StorageConfig, SalienceConfig};
pub use logging::{setup_logging, LogGuard, generate_trace_id, get_or_create_trace_id, TRACE_ID_HEADER};
pub use server::{SalienceService, run_server};

// Note: CacheConfig, MemoryCache, CachedEvent, CachedHeuristic, CacheStats are already
// defined as pub structs in this file, so they are automatically public exports.

/// L0 in-memory cache for recent events and heuristics
pub struct MemoryCache {
    /// Recent events indexed by ID
    events_by_id: HashMap<Uuid, CachedEvent>,
    /// Heuristics indexed by ID
    heuristics: HashMap<Uuid, CachedHeuristic>,
    /// Configuration
    config: CacheConfig,
    /// Statistics: total hits (found in cache)
    total_hits: u64,
    /// Statistics: total misses (not found in cache, requires storage query)
    total_misses: u64,
}

/// Cached event in L0
pub struct CachedEvent {
    pub id: Uuid,
    pub timestamp_ms: i64,
    pub source: String,
    pub raw_text: String,
    pub embedding: Vec<f32>,
    pub access_count: u32,
}

/// Cached heuristic for fast lookup (with LRU tracking)
pub struct CachedHeuristic {
    pub id: Uuid,
    pub name: String,
    pub condition: serde_json::Value,
    pub action: serde_json::Value,
    pub confidence: f32,
    /// Condition embedding for local cosine similarity matching (384-dim f32)
    pub condition_embedding: Vec<f32>,
    /// Last accessed time for LRU eviction
    pub last_accessed_ms: i64,
    /// Time when this heuristic was cached (for TTL-based invalidation)
    pub cached_at_ms: i64,
    /// Number of times this heuristic was matched
    pub hit_count: u64,
    /// Last time this heuristic was matched
    pub last_hit_ms: i64,
}

// Re-export CacheConfig from config module
pub use config::CacheConfig;

impl MemoryCache {
    pub fn new(config: CacheConfig) -> Self {
        Self {
            events_by_id: HashMap::new(),
            heuristics: HashMap::new(),
            config,
            total_hits: 0,
            total_misses: 0,
        }
    }

    /// Check if an event is novel (not similar to anything in cache)
    pub fn is_novel(&self, embedding: &[f32]) -> bool {
        for event in self.events_by_id.values() {
            let similarity = cosine_similarity(embedding, &event.embedding);
            if similarity >= self.config.novelty_threshold {
                return false; // Found similar event, not novel
            }
        }
        true // No similar events found
    }

    /// Find the most similar event in cache.
    /// Returns (event_id, similarity) if found above threshold.
    pub fn find_similar(&self, embedding: &[f32], threshold: f32) -> Option<(Uuid, f32)> {
        let mut best: Option<(Uuid, f32)> = None;

        for event in self.events_by_id.values() {
            let similarity = cosine_similarity(embedding, &event.embedding);
            if similarity >= threshold {
                match &best {
                    None => best = Some((event.id, similarity)),
                    Some((_, best_sim)) if similarity > *best_sim => {
                        best = Some((event.id, similarity));
                    }
                    _ => {}
                }
            }
        }

        best
    }

    /// Add an event to the cache.
    /// Evicts oldest events if cache is full.
    pub fn add_event(&mut self, event: CachedEvent) {
        // Evict if at capacity
        while self.events_by_id.len() >= self.config.max_events {
            // Find oldest event (lowest timestamp)
            if let Some(oldest_id) = self
                .events_by_id
                .values()
                .min_by_key(|e| e.timestamp_ms)
                .map(|e| e.id)
            {
                self.events_by_id.remove(&oldest_id);
            } else {
                break;
            }
        }

        self.events_by_id.insert(event.id, event);
    }

    /// Get an event from cache.
    pub fn get_event(&self, id: &Uuid) -> Option<&CachedEvent> {
        self.events_by_id.get(id)
    }

    /// Get a mutable event from cache (for updating access count).
    pub fn get_event_mut(&mut self, id: &Uuid) -> Option<&mut CachedEvent> {
        self.events_by_id.get_mut(id)
    }

    /// Record a cache hit.
    pub fn record_hit(&mut self) {
        self.total_hits += 1;
    }

    /// Record a cache miss.
    pub fn record_miss(&mut self) {
        self.total_misses += 1;
    }

    /// Add a heuristic to the cache with LRU eviction.
    /// Evicts least-recently-accessed heuristics if cache is full.
    pub fn add_heuristic(&mut self, mut heuristic: CachedHeuristic) {
        let now = current_time_ms();

        // Set last_accessed to now if not set
        if heuristic.last_accessed_ms == 0 {
            heuristic.last_accessed_ms = now;
        }

        // Set cached_at for TTL tracking
        if heuristic.cached_at_ms == 0 {
            heuristic.cached_at_ms = now;
        }

        // Evict if at capacity
        while self.heuristics.len() >= self.config.max_heuristics {
            // Find least recently accessed heuristic
            if let Some(oldest_id) = self
                .heuristics
                .values()
                .min_by_key(|h| h.last_accessed_ms)
                .map(|h| h.id)
            {
                self.heuristics.remove(&oldest_id);
            } else {
                break;
            }
        }

        self.heuristics.insert(heuristic.id, heuristic);
    }

    /// Touch a heuristic (update last_accessed for LRU and record a hit).
    pub fn touch_heuristic(&mut self, id: &Uuid) {
        if let Some(h) = self.heuristics.get_mut(id) {
            let now = current_time_ms();
            h.last_accessed_ms = now;
            h.last_hit_ms = now;
            h.hit_count += 1;
        }
    }

    /// Get a heuristic from cache.
    pub fn get_heuristic(&self, id: &Uuid) -> Option<&CachedHeuristic> {
        self.heuristics.get(id)
    }

    /// Remove a heuristic from cache.
    pub fn remove_heuristic(&mut self, id: &Uuid) -> bool {
        self.heuristics.remove(id).is_some()
    }

    /// Clear all heuristics from cache.
    pub fn flush_heuristics(&mut self) -> usize {
        let count = self.heuristics.len();
        self.heuristics.clear();
        count
    }

    /// Get all heuristics in cache.
    pub fn list_heuristics(&self, limit: usize) -> Vec<&CachedHeuristic> {
        let mut h: Vec<&CachedHeuristic> = self.heuristics.values().collect();
        h.sort_by_key(|h| -h.last_accessed_ms); // Most recent first
        if limit > 0 {
            h.into_iter().take(limit).collect()
        } else {
            h
        }
    }

    /// Get all heuristics above a confidence threshold that haven't expired.
    /// Heuristics are considered expired if they've been cached longer than heuristic_ttl_ms.
    pub fn get_heuristics_by_confidence(&self, min_confidence: f32) -> Vec<&CachedHeuristic> {
        let now = current_time_ms();
        let ttl = self.config.heuristic_ttl_ms;

        self.heuristics
            .values()
            .filter(|h| {
                h.confidence >= min_confidence
                    && (ttl <= 0 || (now - h.cached_at_ms) < ttl)
            })
            .collect()
    }

    /// Find heuristics matching a query embedding via cosine similarity.
    ///
    /// Returns (heuristic_id, similarity) pairs sorted by similarity descending.
    /// Filters by min_similarity, min_confidence, and TTL expiry.
    pub fn find_matching_heuristics(
        &self,
        query_embedding: &[f32],
        min_similarity: f32,
        min_confidence: f32,
        limit: usize,
    ) -> Vec<(Uuid, f32)> {
        if query_embedding.is_empty() {
            return Vec::new();
        }

        let now = current_time_ms();
        let ttl = self.config.heuristic_ttl_ms;

        let mut matches: Vec<(Uuid, f32)> = self.heuristics
            .values()
            .filter(|h| {
                // Skip expired
                if ttl > 0 && (now - h.cached_at_ms) >= ttl {
                    return false;
                }
                // Skip low confidence
                if h.confidence < min_confidence {
                    return false;
                }
                // Skip empty embeddings
                !h.condition_embedding.is_empty()
            })
            .filter_map(|h| {
                let sim = cosine_similarity(query_embedding, &h.condition_embedding);
                if sim >= min_similarity {
                    Some((h.id, sim))
                } else {
                    None
                }
            })
            .collect();

        matches.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        if limit > 0 && matches.len() > limit {
            matches.truncate(limit);
        }

        matches
    }

    /// Get cache statistics.
    pub fn stats(&self) -> CacheStats {
        CacheStats {
            event_count: self.events_by_id.len(),
            heuristic_count: self.heuristics.len(),
            max_events: self.config.max_events,
            max_heuristics: self.config.max_heuristics,
            total_hits: self.total_hits,
            total_misses: self.total_misses,
        }
    }
}

/// Cache statistics for monitoring.
#[derive(Debug, Clone)]
pub struct CacheStats {
    pub event_count: usize,
    pub heuristic_count: usize,
    pub max_events: usize,
    pub max_heuristics: usize,
    pub total_hits: u64,
    pub total_misses: u64,
}

impl CacheStats {
    pub fn hit_rate(&self) -> f32 {
        let total = self.total_hits + self.total_misses;
        if total == 0 {
            0.0
        } else {
            self.total_hits as f32 / total as f32
        }
    }
}

/// Get current time in milliseconds since Unix epoch.
fn current_time_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_millis() as i64
}

/// Compute cosine similarity between two vectors
fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() || a.is_empty() {
        return 0.0;
    }

    let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let norm_a: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let norm_b: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();

    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }

    dot / (norm_a * norm_b)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cosine_similarity_identical() {
        let a = vec![1.0, 0.0, 0.0];
        let b = vec![1.0, 0.0, 0.0];
        assert!((cosine_similarity(&a, &b) - 1.0).abs() < 0.0001);
    }

    #[test]
    fn test_cosine_similarity_orthogonal() {
        let a = vec![1.0, 0.0, 0.0];
        let b = vec![0.0, 1.0, 0.0];
        assert!((cosine_similarity(&a, &b)).abs() < 0.0001);
    }

    #[test]
    fn test_novelty_empty_cache() {
        let cache = MemoryCache::new(CacheConfig::default());
        let embedding = vec![0.1; 384];
        assert!(cache.is_novel(&embedding));
    }

    #[test]
    fn test_novelty_with_similar_event() {
        let mut cache = MemoryCache::new(CacheConfig {
            max_events: 100,
            max_heuristics: 50,
            novelty_threshold: 0.9,
            heuristic_ttl_ms: 5000,
        });

        let embedding = vec![1.0; 384];
        cache.add_event(CachedEvent {
            id: Uuid::new_v4(),
            timestamp_ms: 1000,
            source: "test".to_string(),
            raw_text: "test event".to_string(),
            embedding: embedding.clone(),
            access_count: 0,
        });

        // Identical embedding should not be novel
        assert!(!cache.is_novel(&embedding));

        // Very different embedding should be novel
        let different = vec![-1.0; 384];
        assert!(cache.is_novel(&different));
    }

    #[test]
    fn test_cache_eviction() {
        let mut cache = MemoryCache::new(CacheConfig {
            max_events: 3,
            max_heuristics: 50,
            novelty_threshold: 0.9,
            heuristic_ttl_ms: 5000,
        });

        // Add 4 events to trigger eviction
        for i in 0..4 {
            cache.add_event(CachedEvent {
                id: Uuid::new_v4(),
                timestamp_ms: i * 1000,
                source: "test".to_string(),
                raw_text: format!("event {}", i),
                embedding: vec![i as f32; 384],
                access_count: 0,
            });
        }

        // Should only have 3 events (oldest evicted)
        assert_eq!(cache.stats().event_count, 3);
    }

    #[test]
    fn test_find_similar() {
        let mut cache = MemoryCache::new(CacheConfig::default());

        let event_id = Uuid::new_v4();
        let embedding = vec![1.0; 384];
        cache.add_event(CachedEvent {
            id: event_id,
            timestamp_ms: 1000,
            source: "test".to_string(),
            raw_text: "test event".to_string(),
            embedding: embedding.clone(),
            access_count: 0,
        });

        // Should find the event with high similarity
        let result = cache.find_similar(&embedding, 0.9);
        assert!(result.is_some());
        let (found_id, similarity) = result.unwrap();
        assert_eq!(found_id, event_id);
        assert!(similarity > 0.99);

        // Should not find with very different embedding
        let different = vec![-1.0; 384];
        assert!(cache.find_similar(&different, 0.9).is_none());
    }

    #[test]
    fn test_heuristics_by_confidence() {
        let mut cache = MemoryCache::new(CacheConfig::default());

        cache.add_heuristic(CachedHeuristic {
            id: Uuid::new_v4(),
            name: "low_confidence".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: Vec::new(),
            confidence: 0.3,
            last_accessed_ms: 0,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        cache.add_heuristic(CachedHeuristic {
            id: Uuid::new_v4(),
            name: "high_confidence".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: Vec::new(),
            confidence: 0.9,
            last_accessed_ms: 0,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        let high_conf = cache.get_heuristics_by_confidence(0.5);
        assert_eq!(high_conf.len(), 1);
        assert_eq!(high_conf[0].name, "high_confidence");

        let all = cache.get_heuristics_by_confidence(0.0);
        assert_eq!(all.len(), 2);
    }

    #[test]
    fn test_heuristic_lru_eviction() {
        // Create cache with max_heuristics = 3
        let mut cache = MemoryCache::new(CacheConfig {
            max_events: 100,
            max_heuristics: 3,
            novelty_threshold: 0.9,
            heuristic_ttl_ms: 5000,
        });

        // Add 3 heuristics with different last_accessed times
        let id1 = Uuid::new_v4();
        let id2 = Uuid::new_v4();
        let id3 = Uuid::new_v4();

        cache.add_heuristic(CachedHeuristic {
            id: id1,
            name: "first".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: Vec::new(),
            confidence: 0.5,
            last_accessed_ms: 1000, // Oldest
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        cache.add_heuristic(CachedHeuristic {
            id: id2,
            name: "second".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: Vec::new(),
            confidence: 0.5,
            last_accessed_ms: 2000,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        cache.add_heuristic(CachedHeuristic {
            id: id3,
            name: "third".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: Vec::new(),
            confidence: 0.5,
            last_accessed_ms: 3000, // Newest
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        assert_eq!(cache.stats().heuristic_count, 3);

        // Add a 4th heuristic - should evict the oldest (id1)
        let id4 = Uuid::new_v4();
        cache.add_heuristic(CachedHeuristic {
            id: id4,
            name: "fourth".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: Vec::new(),
            confidence: 0.5,
            last_accessed_ms: 4000,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        assert_eq!(cache.stats().heuristic_count, 3);
        assert!(cache.get_heuristic(&id1).is_none()); // id1 should be evicted
        assert!(cache.get_heuristic(&id2).is_some());
        assert!(cache.get_heuristic(&id3).is_some());
        assert!(cache.get_heuristic(&id4).is_some());
    }

    #[test]
    fn test_heuristic_touch_updates_lru() {
        let mut cache = MemoryCache::new(CacheConfig {
            max_events: 100,
            max_heuristics: 3,
            novelty_threshold: 0.9,
            heuristic_ttl_ms: 5000,
        });

        let id1 = Uuid::new_v4();
        let id2 = Uuid::new_v4();
        let id3 = Uuid::new_v4();

        // Add heuristics with id1 being oldest
        cache.add_heuristic(CachedHeuristic {
            id: id1,
            name: "first".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: Vec::new(),
            confidence: 0.5,
            last_accessed_ms: 1000,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        cache.add_heuristic(CachedHeuristic {
            id: id2,
            name: "second".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: Vec::new(),
            confidence: 0.5,
            last_accessed_ms: 2000,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        cache.add_heuristic(CachedHeuristic {
            id: id3,
            name: "third".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: Vec::new(),
            confidence: 0.5,
            last_accessed_ms: 3000,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        // Touch id1 - should update its last_accessed to now
        cache.touch_heuristic(&id1);

        // Now id2 should be the oldest (since id1 was touched)
        // Add a 4th heuristic - should evict id2
        let id4 = Uuid::new_v4();
        cache.add_heuristic(CachedHeuristic {
            id: id4,
            name: "fourth".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: Vec::new(),
            confidence: 0.5,
            last_accessed_ms: 0, // Will be set by add_heuristic
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        assert!(cache.get_heuristic(&id1).is_some()); // id1 was touched, should survive
        assert!(cache.get_heuristic(&id2).is_none()); // id2 should be evicted (was oldest)
        assert!(cache.get_heuristic(&id3).is_some());
        assert!(cache.get_heuristic(&id4).is_some());
    }

    #[test]
    fn test_find_matching_heuristics_basic() {
        let mut cache = MemoryCache::new(CacheConfig {
            max_events: 100,
            max_heuristics: 50,
            novelty_threshold: 0.9,
            heuristic_ttl_ms: 300_000, // 5 min
        });

        // Create two heuristics with different embeddings
        let id1 = Uuid::new_v4();
        let id2 = Uuid::new_v4();

        // Embedding: mostly positive values
        let emb1: Vec<f32> = (0..384).map(|i| i as f32 / 384.0).collect();
        // Embedding: same direction, should be very similar
        let emb2: Vec<f32> = (0..384).map(|i| (i as f32 / 384.0) + 0.01).collect();

        cache.add_heuristic(CachedHeuristic {
            id: id1,
            name: "h1".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: emb1.clone(),
            confidence: 0.8,
            last_accessed_ms: 0,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        cache.add_heuristic(CachedHeuristic {
            id: id2,
            name: "h2".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: emb2,
            confidence: 0.3, // Below threshold
            last_accessed_ms: 0,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        // Query with emb1 — should match h1 (high confidence), not h2 (low confidence)
        let matches = cache.find_matching_heuristics(&emb1, 0.7, 0.5, 10);
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].0, id1);
        assert!(matches[0].1 > 0.99); // Self-similarity

        // Query with no minimum confidence — should match both
        let matches_all = cache.find_matching_heuristics(&emb1, 0.7, 0.0, 10);
        assert_eq!(matches_all.len(), 2);
        // Results should be sorted by similarity (h1 first = exact match)
        assert_eq!(matches_all[0].0, id1);
    }

    #[test]
    fn test_find_matching_heuristics_empty_embedding() {
        let cache = MemoryCache::new(CacheConfig::default());
        let matches = cache.find_matching_heuristics(&[], 0.7, 0.5, 10);
        assert!(matches.is_empty());
    }

    #[test]
    fn test_find_matching_heuristics_ttl_expiry() {
        let mut cache = MemoryCache::new(CacheConfig {
            max_events: 100,
            max_heuristics: 50,
            novelty_threshold: 0.9,
            heuristic_ttl_ms: 1, // 1ms TTL — will expire immediately
        });

        let emb: Vec<f32> = vec![1.0; 384];
        cache.add_heuristic(CachedHeuristic {
            id: Uuid::new_v4(),
            name: "expired".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: emb.clone(),
            confidence: 0.9,
            last_accessed_ms: 0,
            cached_at_ms: 1, // Very old
            hit_count: 0,
            last_hit_ms: 0,
        });

        // Wait a tiny bit for TTL to expire
        std::thread::sleep(std::time::Duration::from_millis(2));

        let matches = cache.find_matching_heuristics(&emb, 0.5, 0.0, 10);
        assert!(matches.is_empty(), "Expired heuristic should not match");
    }

    #[test]
    fn test_cache_invalidation_removes_heuristic() {
        let mut cache = MemoryCache::new(CacheConfig::default());

        let id = Uuid::new_v4();
        cache.add_heuristic(CachedHeuristic {
            id,
            name: "to_remove".to_string(),
            condition: serde_json::json!({}),
            action: serde_json::json!({}),
            condition_embedding: vec![1.0; 384],
            confidence: 0.9,
            last_accessed_ms: 0,
            cached_at_ms: 0,
            hit_count: 0,
            last_hit_ms: 0,
        });

        assert!(cache.get_heuristic(&id).is_some());
        assert!(cache.remove_heuristic(&id));
        assert!(cache.get_heuristic(&id).is_none());

        // Subsequent queries should not find it
        let emb = vec![1.0; 384];
        let matches = cache.find_matching_heuristics(&emb, 0.5, 0.0, 10);
        assert!(matches.is_empty());
    }
}
