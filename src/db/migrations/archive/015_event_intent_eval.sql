-- Add PoC 2 sensor contract fields to episodic events.
ALTER TABLE episodic_events
    ADD COLUMN IF NOT EXISTS intent TEXT NOT NULL,
    ADD COLUMN IF NOT EXISTS evaluation_data JSONB;
