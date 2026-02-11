-- Migration 009: Heuristic fire tracking ("Flight Recorder")
-- Tracks when heuristics fired and what happened

CREATE TABLE IF NOT EXISTS heuristic_fires (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    heuristic_id UUID NOT NULL REFERENCES heuristics(id) ON DELETE CASCADE,
    event_id TEXT NOT NULL,           -- The event that triggered this fire
    fired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outcome TEXT DEFAULT 'unknown',   -- 'success', 'fail', 'unknown'
    feedback_source TEXT,             -- 'explicit', 'implicit', NULL if no feedback yet
    feedback_at TIMESTAMPTZ,          -- When feedback was received

    -- For linking back to the episodic event
    episodic_event_id UUID REFERENCES episodic_events(id) ON DELETE SET NULL
);

-- Index for querying fires by heuristic
CREATE INDEX IF NOT EXISTS idx_heuristic_fires_heuristic_id ON heuristic_fires(heuristic_id);

-- Index for querying recent fires
CREATE INDEX IF NOT EXISTS idx_heuristic_fires_fired_at ON heuristic_fires(fired_at DESC);

-- Index for finding fires awaiting feedback
CREATE INDEX IF NOT EXISTS idx_heuristic_fires_pending ON heuristic_fires(outcome) WHERE outcome = 'unknown';
