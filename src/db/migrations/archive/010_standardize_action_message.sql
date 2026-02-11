-- Standardize action.message field for heuristics
-- The action JSONB column may have been populated with different key names
-- (message, text, response). This migration normalizes to 'message'.

-- Add 'message' field to all heuristics that don't have it,
-- copying from 'text' or 'response' if available
UPDATE heuristics
SET action = jsonb_set(
    action,
    '{message}',
    COALESCE(
        action->'text',
        action->'response',
        '"(no message)"'::jsonb
    )
)
WHERE action->'message' IS NULL
  AND action IS NOT NULL;

-- Add comment explaining the canonical field
COMMENT ON COLUMN heuristics.action IS
    'Action to take when heuristic fires. JSONB with "message" as canonical text field.';
