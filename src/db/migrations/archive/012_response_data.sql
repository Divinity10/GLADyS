-- Add decision chain columns to episodic_events
ALTER TABLE episodic_events ADD COLUMN IF NOT EXISTS llm_prompt_text TEXT;
ALTER TABLE episodic_events ADD COLUMN IF NOT EXISTS decision_path TEXT;
-- NOTE: matched_heuristic_id column already exists (added in prior migration).
-- Only add if missing:
ALTER TABLE episodic_events ADD COLUMN IF NOT EXISTS matched_heuristic_id UUID REFERENCES heuristics(id) ON DELETE SET NULL;

-- Episodes table (minimal — schema prep for future use)
CREATE TABLE IF NOT EXISTS episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE episodic_events ADD COLUMN IF NOT EXISTS episode_id UUID REFERENCES episodes(id) ON DELETE SET NULL;

-- Indexes for response tab queries
CREATE INDEX IF NOT EXISTS idx_episodic_decision_path ON episodic_events(decision_path);
CREATE INDEX IF NOT EXISTS idx_episodic_matched_heuristic ON episodic_events(matched_heuristic_id);
