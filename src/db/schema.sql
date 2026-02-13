-- GLADyS canonical database schema for fresh installs.
-- This file represents the final state of migrations 001-015.
-- One-time data backfills from historical migrations are intentionally excluded.
-- Extensions are created by cli/init_db.py before this schema is applied.

-- =============================================================================
-- ENTITIES
-- =============================================================================
CREATE TABLE IF NOT EXISTS entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name  TEXT NOT NULL,
    aliases         TEXT[] DEFAULT '{}',
    entity_type     TEXT NOT NULL,
    source          TEXT,
    attributes      JSONB DEFAULT '{}',
    embedding       vector(384),
    first_seen      TIMESTAMPTZ DEFAULT now(),
    last_seen       TIMESTAMPTZ DEFAULT now(),
    mention_count   INTEGER DEFAULT 1,
    merged_into     UUID REFERENCES entities(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE entities OWNER TO gladys;

CREATE INDEX IF NOT EXISTS idx_entities_name ON entities (canonical_name)
    WHERE merged_into IS NULL;
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities (entity_type)
    WHERE merged_into IS NULL;
CREATE INDEX IF NOT EXISTS idx_entities_aliases ON entities USING GIN (aliases)
    WHERE merged_into IS NULL;
CREATE INDEX IF NOT EXISTS idx_entities_embedding ON entities
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_entities_last_seen ON entities (last_seen DESC)
    WHERE merged_into IS NULL;

-- =============================================================================
-- USER PROFILE
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_profile (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trait_category      TEXT NOT NULL,
    trait_name          TEXT NOT NULL,
    value_float         FLOAT,
    value_text          TEXT,
    value_json          JSONB,
    short_term          FLOAT,
    long_term           FLOAT,
    stability           FLOAT DEFAULT 0,
    confidence          FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    observation_count   INTEGER DEFAULT 0,
    embedding           vector(384),
    source_episodes     UUID[] DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (trait_category, trait_name)
);
ALTER TABLE user_profile OWNER TO gladys;

CREATE INDEX IF NOT EXISTS idx_profile_category ON user_profile (trait_category);
CREATE INDEX IF NOT EXISTS idx_profile_confidence ON user_profile (confidence DESC);
CREATE INDEX IF NOT EXISTS idx_profile_embedding ON user_profile
    USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- HEURISTICS
-- =============================================================================
CREATE TABLE IF NOT EXISTS heuristics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    condition           JSONB NOT NULL,
    action              JSONB NOT NULL,
    confidence          FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    source_pattern_ids  UUID[] DEFAULT '{}',
    last_fired          TIMESTAMPTZ,
    fire_count          INTEGER DEFAULT 0,
    success_count       INTEGER DEFAULT 0,
    frozen              BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    condition_tsv       tsvector,
    last_accessed       TIMESTAMPTZ,
    origin              TEXT DEFAULT 'learned',
    origin_id           TEXT,
    condition_embedding vector(384),
    source              TEXT,
    alpha               DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    beta                DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    CONSTRAINT chk_heuristics_alpha_positive CHECK (alpha > 0),
    CONSTRAINT chk_heuristics_beta_positive CHECK (beta > 0)
);
ALTER TABLE heuristics OWNER TO gladys;

COMMENT ON COLUMN heuristics.action IS
    'Action to take when heuristic fires. JSONB with "message" as canonical text field.';
COMMENT ON COLUMN heuristics.origin IS
    'How this heuristic was created: built_in, pack, learned, user';
COMMENT ON COLUMN heuristics.origin_id IS
    'Reference to origin source: pack ID, reasoning trace ID, user ID, etc.';

CREATE INDEX IF NOT EXISTS idx_heuristics_condition ON heuristics USING GIN (condition);
CREATE INDEX IF NOT EXISTS idx_heuristics_confidence ON heuristics (confidence DESC)
    WHERE frozen = FALSE;
CREATE INDEX IF NOT EXISTS idx_heuristics_condition_tsv
    ON heuristics USING GIN (condition_tsv);
CREATE INDEX IF NOT EXISTS idx_heuristics_performance
    ON heuristics (fire_count DESC, success_count DESC)
    WHERE frozen = FALSE;
CREATE INDEX IF NOT EXISTS idx_heuristics_lru
    ON heuristics (last_accessed DESC NULLS LAST)
    WHERE frozen = FALSE;
CREATE INDEX IF NOT EXISTS idx_heuristics_origin
    ON heuristics (origin);
CREATE INDEX IF NOT EXISTS idx_heuristics_condition_embedding
    ON heuristics USING hnsw (condition_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_heuristics_source ON heuristics(source);

CREATE OR REPLACE FUNCTION heuristics_condition_tsv_trigger() RETURNS trigger AS $$
BEGIN
    NEW.condition_tsv := to_tsvector('english', COALESCE(NEW.condition->>'text', ''));
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS heuristics_condition_tsv_update ON heuristics;
CREATE TRIGGER heuristics_condition_tsv_update
    BEFORE INSERT OR UPDATE ON heuristics
    FOR EACH ROW
    EXECUTE FUNCTION heuristics_condition_tsv_trigger();

-- =============================================================================
-- FEEDBACK EVENTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS feedback_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    target_type     TEXT NOT NULL,
    target_id       UUID,
    target_context  JSONB DEFAULT '{}',
    feedback_type   TEXT NOT NULL,
    feedback_value  FLOAT,
    feedback_text   TEXT,
    weight          FLOAT NOT NULL DEFAULT 1.0 CHECK (weight BETWEEN 0 AND 1),
    processed       BOOLEAN DEFAULT FALSE,
    processed_at    TIMESTAMPTZ,
    source          TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE feedback_events OWNER TO gladys;

CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON feedback_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_target ON feedback_events (target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_feedback_unprocessed ON feedback_events (timestamp)
    WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback_events (feedback_type);

-- =============================================================================
-- RELATIONSHIPS
-- =============================================================================
CREATE TABLE IF NOT EXISTS relationships (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id      UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    predicate       TEXT NOT NULL,
    object_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    attributes      JSONB DEFAULT '{}',
    confidence      FLOAT DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    source          TEXT,
    source_event_id UUID,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (subject_id, predicate, object_id)
);
ALTER TABLE relationships OWNER TO gladys;

CREATE INDEX IF NOT EXISTS idx_rel_subject ON relationships (subject_id);
CREATE INDEX IF NOT EXISTS idx_rel_object ON relationships (object_id);
CREATE INDEX IF NOT EXISTS idx_rel_predicate ON relationships (predicate);
CREATE INDEX IF NOT EXISTS idx_rel_confidence ON relationships (confidence DESC)
    WHERE confidence >= 0.5;
CREATE INDEX IF NOT EXISTS idx_rel_entity_all ON relationships (subject_id, object_id);

-- =============================================================================
-- SKILLS
-- =============================================================================
CREATE TABLE IF NOT EXISTS skills (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_id       TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    version         TEXT NOT NULL,
    description     TEXT,
    category        TEXT NOT NULL,
    capabilities    TEXT[] DEFAULT '{}',
    activation      JSONB DEFAULT '{}',
    methods         JSONB DEFAULT '[]',
    manifest        JSONB NOT NULL,
    manifest_path   TEXT,
    loaded_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE skills OWNER TO gladys;

CREATE INDEX IF NOT EXISTS idx_skills_capabilities ON skills USING GIN (capabilities);
CREATE INDEX IF NOT EXISTS idx_skills_category ON skills (category);
CREATE INDEX IF NOT EXISTS idx_skills_plugin_id ON skills (plugin_id);

CREATE OR REPLACE FUNCTION update_skills_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS skills_updated_at ON skills;
CREATE TRIGGER skills_updated_at
    BEFORE UPDATE ON skills
    FOR EACH ROW
    EXECUTE FUNCTION update_skills_updated_at();

-- =============================================================================
-- SENSORS (Sensor Components)
-- =============================================================================
CREATE TABLE IF NOT EXISTS sensors (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id                    UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    sensor_name                 TEXT NOT NULL,
    sensor_type                 TEXT NOT NULL CHECK (sensor_type IN ('push', 'poll')),
    source_pattern              TEXT NOT NULL,

    -- Protocol config (from manifest)
    heartbeat_interval_s        INTEGER NOT NULL DEFAULT 30,
    adapter_language            TEXT,
    driver_count                INTEGER DEFAULT 1,

    -- Health monitoring thresholds (per-sensor consolidation expectations)
    expected_consolidation_min  FLOAT DEFAULT 0.8,
    expected_consolidation_max  FLOAT DEFAULT 1.2,

    -- Manifest data
    manifest                    JSONB NOT NULL,
    config                      JSONB DEFAULT '{}',

    created_at                  TIMESTAMPTZ DEFAULT now(),
    updated_at                  TIMESTAMPTZ DEFAULT now(),

    UNIQUE(skill_id, sensor_name)
);

ALTER TABLE sensors OWNER TO gladys;

CREATE INDEX IF NOT EXISTS idx_sensors_skill ON sensors(skill_id);
CREATE INDEX IF NOT EXISTS idx_sensors_source_pattern ON sensors(source_pattern);
CREATE INDEX IF NOT EXISTS idx_sensors_type ON sensors(sensor_type);

COMMENT ON TABLE sensors IS 'Sensor components registered via skill packs';
COMMENT ON COLUMN sensors.source_pattern IS 'Source identifier pattern (e.g., "melvor", "gmail:%", "%@example.com")';
COMMENT ON COLUMN sensors.expected_consolidation_min IS 'Lower bound for healthy consolidation ratio (messages:events)';
COMMENT ON COLUMN sensors.expected_consolidation_max IS 'Upper bound for healthy consolidation ratio (messages:events)';

-- Example consolidation thresholds by sensor type:
-- RuneScape: min=20, max=60 (expect 20:1 to 60:1 ratio)
-- Melvor: min=10, max=40 (expect 10:1 to 40:1 ratio)
-- Email: min=0.8, max=1.2 (expect ~1:1 ratio, ±20%)
-- Sudoku: min=0.8, max=1.2 (expect ~1:1 ratio, ±20%)

-- =============================================================================
-- SENSOR STATUS (Runtime State)
-- =============================================================================
CREATE TABLE IF NOT EXISTS sensor_status (
    sensor_id           UUID PRIMARY KEY REFERENCES sensors(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'inactive'
                        CHECK (status IN ('inactive', 'active', 'disconnected', 'error', 'recovering')),
    last_heartbeat      TIMESTAMPTZ,
    last_error          TEXT,
    error_count         INTEGER DEFAULT 0,
    active_sources      TEXT[] DEFAULT '{}',
    events_received     BIGINT DEFAULT 0,
    events_published    BIGINT DEFAULT 0,
    updated_at          TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE sensor_status OWNER TO gladys;

CREATE INDEX IF NOT EXISTS idx_sensor_status_status ON sensor_status(status);
CREATE INDEX IF NOT EXISTS idx_sensor_status_heartbeat ON sensor_status(last_heartbeat DESC NULLS LAST);

COMMENT ON TABLE sensor_status IS 'Runtime state for each sensor (updated by orchestrator on heartbeat)';
COMMENT ON COLUMN sensor_status.active_sources IS 'Current sources reported in latest heartbeat (for multi-driver sensors)';
COMMENT ON COLUMN sensor_status.events_received IS 'Lifetime counter: total driver messages received';
COMMENT ON COLUMN sensor_status.events_published IS 'Lifetime counter: total events published to orchestrator';

-- =============================================================================
-- SENSOR METRICS (Time-Series Heartbeat Data)
-- =============================================================================
CREATE TABLE IF NOT EXISTS sensor_metrics (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sensor_id               UUID NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
    timestamp               TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Event counters (incremental since last heartbeat)
    events_received         BIGINT NOT NULL,
    events_published        BIGINT NOT NULL,
    events_filtered         BIGINT DEFAULT 0,
    events_errored          BIGINT DEFAULT 0,

    -- Performance metrics
    avg_latency_ms          FLOAT,
    consolidation_ratio     FLOAT,

    -- Queue depths (snapshot at heartbeat time)
    inbound_queue_depth     INTEGER DEFAULT 0,
    outbound_queue_depth    INTEGER DEFAULT 0,

    -- Per-driver metrics (JSONB for multi-driver sensors)
    driver_metrics          JSONB DEFAULT '{}',

    created_at              TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE sensor_metrics OWNER TO gladys;

CREATE INDEX IF NOT EXISTS idx_sensor_metrics_sensor_time ON sensor_metrics(sensor_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_sensor_metrics_timestamp ON sensor_metrics(timestamp DESC);

COMMENT ON TABLE sensor_metrics IS 'Time-series heartbeat data (30-day rolling retention)';
COMMENT ON COLUMN sensor_metrics.consolidation_ratio IS 'events_received / events_published (adapter efficiency)';
COMMENT ON COLUMN sensor_metrics.inbound_queue_depth IS 'Driver→Adapter queue depth at heartbeat time';
COMMENT ON COLUMN sensor_metrics.outbound_queue_depth IS 'Adapter→Orchestrator queue depth at heartbeat time';
COMMENT ON COLUMN sensor_metrics.driver_metrics IS 'Per-driver stats for multi-driver sensors (e.g., Gmail per-account)';

-- =============================================================================
-- EPISODES
-- =============================================================================
CREATE TABLE IF NOT EXISTS episodes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE episodes OWNER TO gladys;

-- =============================================================================
-- EPISODIC EVENTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS episodic_events (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp               TIMESTAMPTZ NOT NULL DEFAULT now(),
    source                  TEXT NOT NULL,
    raw_text                TEXT NOT NULL,
    embedding               vector(384),
    salience                JSONB NOT NULL DEFAULT '{}',
    structured              JSONB DEFAULT '{}',
    entity_ids              UUID[] DEFAULT '{}',
    archived                BOOLEAN DEFAULT false,
    created_at              TIMESTAMPTZ DEFAULT now(),
    access_count            INTEGER DEFAULT 0,
    predicted_success       FLOAT,
    prediction_confidence   FLOAT,
    response_id             TEXT,
    response_text           TEXT,
    llm_prompt_text         TEXT,
    decision_path           TEXT,
    matched_heuristic_id    UUID REFERENCES heuristics(id) ON DELETE SET NULL,
    episode_id              UUID REFERENCES episodes(id) ON DELETE SET NULL,
    intent                  TEXT NOT NULL,
    evaluation_data         JSONB
);
ALTER TABLE episodic_events OWNER TO gladys;

COMMENT ON COLUMN episodic_events.predicted_success IS
    'LLM prediction of action success probability (0.0-1.0). Populated when LLM reasoning was triggered.';
COMMENT ON COLUMN episodic_events.prediction_confidence IS
    'LLM confidence in the predicted_success value (0.0-1.0). Lower = more uncertain.';
COMMENT ON COLUMN episodic_events.response_id IS
    'Links to executive response/reasoning trace for feedback attribution.';
COMMENT ON COLUMN episodic_events.response_text IS
    'The actual LLM response text. Required for building fine-tuning datasets (input/output pairs).';

CREATE INDEX IF NOT EXISTS idx_episodic_timestamp ON episodic_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_source ON episodic_events (source, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_embedding ON episodic_events
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_episodic_active ON episodic_events (timestamp DESC)
    WHERE archived = false;
CREATE INDEX IF NOT EXISTS idx_episodic_salience ON episodic_events USING GIN (salience);
CREATE INDEX IF NOT EXISTS idx_episodic_entities ON episodic_events USING GIN (entity_ids);
CREATE INDEX IF NOT EXISTS idx_episodic_events_response_id
    ON episodic_events (response_id)
    WHERE response_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_episodic_decision_path ON episodic_events(decision_path);
CREATE INDEX IF NOT EXISTS idx_episodic_matched_heuristic ON episodic_events(matched_heuristic_id);

-- =============================================================================
-- HEURISTIC FIRES
-- =============================================================================
CREATE TABLE IF NOT EXISTS heuristic_fires (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    heuristic_id        UUID NOT NULL REFERENCES heuristics(id) ON DELETE CASCADE,
    event_id            TEXT NOT NULL,
    fired_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outcome             TEXT DEFAULT 'unknown',
    feedback_source     TEXT,
    feedback_at         TIMESTAMPTZ,
    episodic_event_id   UUID REFERENCES episodic_events(id) ON DELETE SET NULL
);
ALTER TABLE heuristic_fires OWNER TO gladys;

CREATE INDEX IF NOT EXISTS idx_heuristic_fires_heuristic_id ON heuristic_fires(heuristic_id);
CREATE INDEX IF NOT EXISTS idx_heuristic_fires_fired_at ON heuristic_fires(fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_heuristic_fires_pending ON heuristic_fires(outcome) WHERE outcome = 'unknown';
