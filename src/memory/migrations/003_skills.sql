-- Migration 003: Skills table
-- Stores skill manifests for capability discovery
-- Skills are loaded from YAML files and synced to DB for queryability

-- Skills table - core metadata
CREATE TABLE IF NOT EXISTS skills (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id       TEXT NOT NULL UNIQUE,           -- e.g., 'minecraft-skill'
    name            TEXT NOT NULL,                  -- Human-readable name
    version         TEXT NOT NULL,                  -- Semantic version
    description     TEXT,
    category        TEXT NOT NULL,                  -- style_modifier, domain_expertise, capability, etc.

    -- Capabilities this skill provides (for discovery)
    capabilities    TEXT[] DEFAULT '{}',            -- e.g., ['check_player_status', 'query_inventory']

    -- Activation conditions (when to load this skill)
    activation      JSONB DEFAULT '{}',             -- Sensor dependencies, personality triggers, etc.

    -- Methods (for capability skills)
    methods         JSONB DEFAULT '[]',             -- Array of {name, description, capabilities, parameters, returns}

    -- Full manifest (for reference)
    manifest        JSONB NOT NULL,                 -- Complete YAML as JSON
    manifest_path   TEXT,                           -- Path to manifest.yaml file

    -- Metadata
    loaded_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for capability discovery
CREATE INDEX IF NOT EXISTS idx_skills_capabilities ON skills USING GIN (capabilities);

-- Index for category queries
CREATE INDEX IF NOT EXISTS idx_skills_category ON skills (category);

-- Index for plugin_id lookups
CREATE INDEX IF NOT EXISTS idx_skills_plugin_id ON skills (plugin_id);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_skills_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for updated_at
DROP TRIGGER IF EXISTS skills_updated_at ON skills;
CREATE TRIGGER skills_updated_at
    BEFORE UPDATE ON skills
    FOR EACH ROW
    EXECUTE FUNCTION update_skills_updated_at();
