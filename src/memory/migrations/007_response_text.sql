-- Add response_text field to episodic_events
-- Stores the actual LLM response for fine-tuning dataset creation
-- Input/output pairs are required for ML training

ALTER TABLE episodic_events
ADD COLUMN IF NOT EXISTS response_text TEXT;

COMMENT ON COLUMN episodic_events.response_text IS
    'The actual LLM response text. Required for building fine-tuning datasets (input/output pairs).';
