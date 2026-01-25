-- Add origin tracking to heuristics table
-- Allows filtering by source: built_in, pack, learned, user
-- Per gemini_memory.md: Schema gap identified during integration testing

-- Add origin column (how the heuristic was created)
ALTER TABLE heuristics
ADD COLUMN IF NOT EXISTS origin TEXT DEFAULT 'learned';

-- Add origin_id column (pack ID, reasoning trace ID, etc.)
ALTER TABLE heuristics
ADD COLUMN IF NOT EXISTS origin_id TEXT;

-- Add index for filtering by origin (common query pattern)
CREATE INDEX IF NOT EXISTS idx_heuristics_origin
    ON heuristics (origin);

-- Add comments
COMMENT ON COLUMN heuristics.origin IS
    'How this heuristic was created: built_in, pack, learned, user';

COMMENT ON COLUMN heuristics.origin_id IS
    'Reference to origin source: pack ID, reasoning trace ID, user ID, etc.';
