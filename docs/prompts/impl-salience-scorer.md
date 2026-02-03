# Implementation: Salience Scorer Trait

**Read `CLAUDE.md` first, then `docs/design/SALIENCE_SCORER.md` (the spec), then this prompt.**

## Task

Extract a `SalienceScorer` trait from the Rust salience service's inline scoring logic. This creates an abstraction layer so PoC 2 can test alternative scoring algorithms (e.g., TF-IDF).

## Branch

```bash
git checkout main && git pull
git checkout -b refactor/salience-scorer
```

## What to Implement

Follow `docs/design/SALIENCE_SCORER.md` exactly. Summary:

1. **Add trait and types** to `src/services/salience/src/lib.rs`:
   ```rust
   #[derive(Debug, Clone)]
   pub struct ScoredMatch {
       pub heuristic_id: String,
       pub similarity: f32,
       pub confidence: f32,
       pub condition_text: String,
       pub suggested_action: String,
       pub salience_boost: Option<serde_json::Value>,
   }

   #[derive(Debug, thiserror::Error)]
   pub enum ScoringError {
       #[error("Embedding generation failed: {0}")]
       EmbeddingError(String),
       #[error("Storage query failed: {0}")]
       StorageError(String),
       #[error("No matches found")]
       NoMatches,
   }

   #[async_trait]
   pub trait SalienceScorer: Send + Sync {
       async fn score(
           &self,
           event_text: &str,
           source: &str,
           trace_id: Option<&str>,
       ) -> Result<Vec<ScoredMatch>, ScoringError>;

       fn config(&self) -> serde_json::Value;
   }
   ```

2. **Create `EmbeddingSimilarityScorer`** struct:
   - Implements the trait
   - Move scoring logic from `SalienceService.evaluate_salience()`:
     - Embedding generation via Python
     - Cache lookup with cosine similarity
     - Fallback to Python storage query
   - Takes `cache`, `storage_config`, `min_similarity`, `min_confidence` as constructor params

3. **Refactor `SalienceService`**:
   - Constructor takes `scorer: Box<dyn SalienceScorer>`
   - `evaluate_salience()` delegates to `self.scorer.score()`
   - Keep salience boost application in the service (not the scorer)

4. **Add config field** to `Config` struct in `config.rs`:
   ```rust
   pub scorer: String,  // "embedding" (default)
   ```

5. **Add factory** in `main.rs`:
   ```rust
   fn create_scorer(config: &Config, cache: Arc<RwLock<MemoryCache>>) -> Box<dyn SalienceScorer>
   ```

## Optional: StorageBackend Trait

For better testability, also extract a `StorageBackend` trait:

```rust
#[async_trait]
pub trait StorageBackend: Send + Sync {
    async fn query_matching_heuristics(...) -> Result<Vec<CachedHeuristic>, String>;
    async fn generate_embedding(...) -> Result<Vec<f32>, String>;
}
```

This allows unit testing `EmbeddingSimilarityScorer` without a live gRPC server. Implement `GrpcStorageBackend` as the default.

## Constraints

- Keep the same external behavior — gRPC responses must be identical.
- The scorer returns `ScoredMatch` structs; the service applies salience boosts and builds the proto response.
- Don't change the cache or Python client APIs.

## Testing

- Add unit tests for `EmbeddingSimilarityScorer`:
  - Test with mock `StorageBackend` (if extracted)
  - Test cache hit path
  - Test cache miss → storage fallback
  - Test empty text returns empty matches
- Tests go in `src/services/salience/src/scorer_test.rs` (or inline with `#[cfg(test)]`)

## Files to Change

| File | Change |
|------|--------|
| `src/lib.rs` | Add trait, error type, `ScoredMatch` struct |
| `src/server.rs` | Add `EmbeddingSimilarityScorer`, refactor `SalienceService` |
| `src/config.rs` | Add `scorer` field |
| `src/main.rs` | Add `create_scorer` factory |
| (optional) `src/lib.rs` | Add `StorageBackend` trait |

## Definition of Done

- [ ] `SalienceScorer` trait exists with correct signature
- [ ] `EmbeddingSimilarityScorer` implements it
- [ ] `SalienceService` delegates to scorer
- [ ] Config field and factory work
- [ ] `cargo test` passes
- [ ] `cargo build --release` succeeds
- [ ] Manual test: salience evaluation returns same results

## Working Memory

Use `claude_memory.md` (gitignored) as your working scratchpad.
