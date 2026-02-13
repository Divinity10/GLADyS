# Salience Scorer Trait Spec

**Status**: Proposed
**Date**: 2026-02-02 (updated 2026-02-06 with F-01)
**Implements**: Extensibility Review item #3
**Informed by**: Phase 1 finding F-01

## Purpose

Define a Rust trait for salience scoring so that Phase 2 can test alternative algorithms (TF-IDF, different distance metrics) without modifying the gRPC handler.

## Current State

`SalienceService` in `src/services/salience/src/server.rs` has inline scoring logic in `evaluate_salience()`:

1. Generate embedding via Python Memory service
2. Cosine similarity match against cached heuristics (`cache.find_matching_heuristics`)
3. Fallback to Python `QueryMatchingHeuristics` RPC on cache miss
4. Apply salience boosts via `apply_heuristic_salience`

Hardcoded elements:

- Distance metric: cosine similarity only
- Embedding source: Python Memory service
- Match thresholds: configurable via `SalienceConfig`, but algorithm is fixed

## Trait Definition

```rust
use async_trait::async_trait;

/// Result of scoring an event against known heuristics.
#[derive(Debug, Clone)]
pub struct ScoredMatch {
    pub heuristic_id: String,
    pub similarity: f32,
    pub confidence: f32,
    pub condition_text: String,
    pub suggested_action: String,
    pub salience_boost: Option<serde_json::Value>,
}

/// Error type for scoring operations.
#[derive(Debug, thiserror::Error)]
pub enum ScoringError {
    #[error("Embedding generation failed: {0}")]
    EmbeddingError(String),
    #[error("Storage query failed: {0}")]
    StorageError(String),
    #[error("No matches found")]
    NoMatches,
}

/// Interface for salience scoring algorithms.
#[async_trait]
pub trait SalienceScorer: Send + Sync {
    /// Score an event against known heuristics.
    ///
    /// Returns the best matching heuristic(s) with similarity scores.
    async fn score(
        &self,
        event_text: &str,
        source: &str,
        trace_id: Option<&str>,
    ) -> Result<Vec<ScoredMatch>, ScoringError>;

    /// Return scorer configuration for logging.
    fn config(&self) -> serde_json::Value;
}
```

### Source Filtering (F-01)

The `source` parameter enables domain-based heuristic filtering per F-01. Source filtering prevents cross-domain false matches (e.g., a Sudoku event matching a Melvor heuristic).

**Current implementation**: Source filtering is delegated to Python storage — `QueryMatchingHeuristics` filters by source before returning results. The `EmbeddingSimilarityScorer` passes `source` through to the storage backend's `query_matching_heuristics` call. The cache-hit path does not currently filter by source (cache entries are domain-mixed).

**Future**: A custom scorer could use source for local filtering (e.g., partitioning the cache by source, or applying source-specific similarity thresholds). The trait accepts `source` to support this without interface changes.

## Default Implementation: EmbeddingSimilarityScorer

```rust
/// Current Phase 1 scorer — embedding + cosine similarity.
pub struct EmbeddingSimilarityScorer {
    cache: Arc<RwLock<MemoryCache>>,
    storage_config: Option<StorageConfig>,
    min_similarity: f32,
    min_confidence: f32,
}

impl EmbeddingSimilarityScorer {
    pub fn new(
        cache: Arc<RwLock<MemoryCache>>,
        storage_config: Option<StorageConfig>,
        min_similarity: f32,
        min_confidence: f32,
    ) -> Self {
        Self { cache, storage_config, min_similarity, min_confidence }
    }

    async fn generate_embedding(&self, text: &str, trace_id: Option<&str>) -> Option<Vec<f32>> {
        // ... existing embedding generation logic
    }

    async fn query_storage(&self, text: &str, trace_id: Option<&str>) -> Result<Vec<CachedHeuristic>, String> {
        // ... existing storage query logic
    }
}

#[async_trait]
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

        // Step 1: Generate embedding
        let embedding = self.generate_embedding(event_text, trace_id).await
            .ok_or_else(|| ScoringError::EmbeddingError("Failed to generate embedding".into()))?;

        // Step 2: Cache lookup with cosine similarity
        let cache = self.cache.read().await;
        let cache_matches = cache.find_matching_heuristics(
            &embedding,
            self.min_similarity,
            self.min_confidence,
            5,
        );
        drop(cache);

        if !cache_matches.is_empty() {
            return Ok(cache_matches.into_iter().map(|(h, sim)| ScoredMatch {
                heuristic_id: h.id.clone(),
                similarity: sim,
                confidence: h.confidence,
                condition_text: h.condition.clone(),
                suggested_action: h.action.get("message")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                salience_boost: h.action.get("salience").cloned(),
            }).collect());
        }

        // Step 3: Fallback to Python storage
        let heuristics = self.query_storage(event_text, trace_id).await
            .map_err(|e| ScoringError::StorageError(e))?;

        Ok(heuristics.into_iter().map(|h| ScoredMatch {
            heuristic_id: h.id.clone(),
            similarity: 1.0, // Python returns pre-filtered matches
            confidence: h.confidence,
            condition_text: h.condition.clone(),
            suggested_action: h.action.get("message")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
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
```

## SalienceService Changes

`SalienceService` takes a scorer via constructor:

```rust
pub struct SalienceService {
    cache: Arc<RwLock<MemoryCache>>,
    scorer: Box<dyn SalienceScorer>,
    config: SalienceConfig,
    started_at: Instant,
}

impl SalienceService {
    pub fn with_scorer(
        cache: Arc<RwLock<MemoryCache>>,
        scorer: Box<dyn SalienceScorer>,
        config: SalienceConfig,
    ) -> Self {
        Self { cache, scorer, config, started_at: Instant::now() }
    }
}
```

`evaluate_salience` delegates to the scorer:

```rust
async fn evaluate_salience(&self, request: Request<EvaluateSalienceRequest>) -> Result<Response<EvaluateSalienceResponse>, Status> {
    let trace_id = get_or_create_trace_id(&request);
    let req = request.into_inner();

    let mut salience = SalienceVector {
        novelty: self.config.baseline_novelty,
        ..Default::default()
    };

    // Delegate scoring to the strategy
    match self.scorer.score(&req.raw_text, &req.source, Some(&trace_id)).await {
        Ok(matches) if !matches.is_empty() => {
            let best = &matches[0];
            // Apply salience boost from best match
            if let Some(boost) = &best.salience_boost {
                Self::apply_salience_boost(&mut salience, boost);
            }
            // ... set matched_heuristic_id, etc.
        }
        Ok(_) => {
            // No matches — use baseline novelty boost
            salience.novelty += self.config.unmatched_novelty_boost;
        }
        Err(e) => {
            warn!("Scoring failed: {}", e);
            salience.novelty += self.config.unmatched_novelty_boost;
        }
    }

    Ok(Response::new(EvaluateSalienceResponse { salience: Some(salience), .. }))
}
```

## Configuration

Add to `Config` struct in `config.rs`:

```rust
pub struct Config {
    pub server: ServerConfig,
    pub salience: SalienceConfig,
    pub storage: Option<StorageConfig>,
    pub scorer: String,  // NEW: "embedding" | "tfidf" (future)
}
```

Factory in `main.rs`:

```rust
fn create_scorer(
    config: &Config,
    cache: Arc<RwLock<MemoryCache>>,
) -> Box<dyn SalienceScorer> {
    match config.scorer.as_str() {
        "embedding" | "" => Box::new(EmbeddingSimilarityScorer::new(
            cache,
            config.storage.clone(),
            config.salience.min_heuristic_similarity,
            config.salience.min_heuristic_confidence,
        )),
        // Future: "tfidf" => Box::new(TfIdfScorer::new(...)),
        other => panic!("Unknown scorer: {}", other),
    }
}
```

## Storage Backend Trait (Optional)

For better testability, also extract `StorageBackend`:

```rust
#[async_trait]
pub trait StorageBackend: Send + Sync {
    async fn query_matching_heuristics(
        &self,
        event_text: &str,
        min_confidence: f32,
        limit: i32,
        source: Option<&str>,  // F-01: domain filtering
        trace_id: Option<&str>,
    ) -> Result<Vec<CachedHeuristic>, String>;

    async fn generate_embedding(
        &self,
        text: &str,
        trace_id: Option<&str>,
    ) -> Result<Vec<f32>, String>;
}

/// Default implementation using StorageClient (Python gRPC)
pub struct GrpcStorageBackend {
    config: StorageConfig,
}
```

This allows unit testing `EmbeddingSimilarityScorer` without a live gRPC server.

## File Changes

| File | Change |
|------|--------|
| `src/lib.rs` | Add `SalienceScorer` trait, `ScoredMatch`, `ScoringError` |
| `src/server.rs` | Add `EmbeddingSimilarityScorer`, refactor `SalienceService` to use trait |
| `src/config.rs` | Add `scorer` field to `Config` |
| `src/main.rs` | Add `create_scorer` factory |
| `src/lib.rs` | (Optional) Add `StorageBackend` trait for testability |

## Testing

- Unit test `EmbeddingSimilarityScorer` with mock `StorageBackend`
- Test cache hit path
- Test cache miss → storage fallback path
- Test empty text returns empty matches

## Out of Scope

- TF-IDF scorer — add in Phase 2 if needed
- Alternative embedding models — Python-side change
- Variable-length embedding support — requires cache schema changes
