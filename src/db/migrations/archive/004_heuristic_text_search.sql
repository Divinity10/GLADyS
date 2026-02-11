-- Add text search capability to heuristics table
-- Enables efficient matching of event text against heuristic conditions

-- Add tsvector column for full-text search
ALTER TABLE heuristics ADD COLUMN IF NOT EXISTS condition_tsv tsvector;

-- Create GIN index for fast text search
CREATE INDEX IF NOT EXISTS idx_heuristics_condition_tsv
    ON heuristics USING GIN (condition_tsv);

-- Function to extract text from condition JSONB and generate tsvector
CREATE OR REPLACE FUNCTION heuristics_condition_tsv_trigger() RETURNS trigger AS $$
BEGIN
    -- Extract 'text' field from condition JSONB
    NEW.condition_tsv := to_tsvector('english', COALESCE(NEW.condition->>'text', ''));
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

-- Trigger to auto-update tsvector on insert/update
DROP TRIGGER IF EXISTS heuristics_condition_tsv_update ON heuristics;
CREATE TRIGGER heuristics_condition_tsv_update
    BEFORE INSERT OR UPDATE ON heuristics
    FOR EACH ROW
    EXECUTE FUNCTION heuristics_condition_tsv_trigger();

-- Backfill existing rows
UPDATE heuristics
SET condition_tsv = to_tsvector('english', COALESCE(condition->>'text', ''))
WHERE condition_tsv IS NULL;

-- Add index on fire_count and success_count for LRU eviction queries
CREATE INDEX IF NOT EXISTS idx_heuristics_performance
    ON heuristics (fire_count DESC, success_count DESC)
    WHERE frozen = FALSE;

-- Add last_accessed column for LRU tracking
ALTER TABLE heuristics ADD COLUMN IF NOT EXISTS last_accessed TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_heuristics_lru
    ON heuristics (last_accessed DESC NULLS LAST)
    WHERE frozen = FALSE;
