-- Add prediction instrumentation fields to episodic_events
-- Per §27: "Instrument Now, Analyze Later" strategy
-- Records LLM predictions for later TD learning analysis

-- Add prediction columns
ALTER TABLE episodic_events
ADD COLUMN IF NOT EXISTS predicted_success FLOAT;

ALTER TABLE episodic_events
ADD COLUMN IF NOT EXISTS prediction_confidence FLOAT;

ALTER TABLE episodic_events
ADD COLUMN IF NOT EXISTS response_id TEXT;

-- Add index on response_id for linking back to executive responses
CREATE INDEX IF NOT EXISTS idx_episodic_events_response_id
    ON episodic_events (response_id)
    WHERE response_id IS NOT NULL;

-- Add comment documenting the fields
COMMENT ON COLUMN episodic_events.predicted_success IS
    'LLM prediction of action success probability (0.0-1.0). Populated when LLM reasoning was triggered.';

COMMENT ON COLUMN episodic_events.prediction_confidence IS
    'LLM confidence in the predicted_success value (0.0-1.0). Lower = more uncertain.';

COMMENT ON COLUMN episodic_events.response_id IS
    'Links to executive response/reasoning trace for feedback attribution.';
