-- Add embedding column for semantic heuristic matching
-- Replaces word-overlap matching which produces false positives
-- when sentences share structural words but have different meanings

-- Add embedding column (same dimension as episodic_events: all-MiniLM-L6-v2 = 384)
ALTER TABLE heuristics
ADD COLUMN IF NOT EXISTS condition_embedding vector(384);

-- Create HNSW index for fast similarity search
-- Using same parameters as episodic_events for consistency
CREATE INDEX IF NOT EXISTS idx_heuristics_condition_embedding
    ON heuristics USING hnsw (condition_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Note: Backfill of existing heuristics should be done via Python
-- since embedding generation requires the embedding model.
-- Run: SELECT id, condition->>'text' FROM heuristics WHERE condition_embedding IS NULL;
-- Then generate embeddings and UPDATE each row.
