-- Migrate origin from condition JSONB to dedicated column
-- Previously, origin was stored in condition->>'origin'
-- Now it should be in the 'origin' column

-- Copy origin from condition JSONB to column (where column is still default)
UPDATE heuristics
SET origin = COALESCE(condition->>'origin', 'learned')
WHERE condition->'origin' IS NOT NULL
  AND origin = 'learned';

-- Remove origin key from condition JSONB to avoid duplication
UPDATE heuristics
SET condition = condition - 'origin'
WHERE condition->'origin' IS NOT NULL;
