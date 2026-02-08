-- Add source column to heuristics for domain-based filtering (#99)
-- Source tracks which sensor domain a heuristic was learned from.
-- Strict filtering: when source_filter is specified, only exact matches returned.
-- NULL-source heuristics (pre-existing) excluded from filtered queries.

ALTER TABLE heuristics ADD COLUMN IF NOT EXISTS source TEXT;
CREATE INDEX IF NOT EXISTS idx_heuristics_source ON heuristics(source);
