-- GLADyS Memory Subsystem - Initial Schema
-- Based on ADR-0004: Memory Schema Details
-- MVP scope: Core tables only (episodic_events, entities, user_profile, heuristics, feedback_events)

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- =============================================================================
-- EPISODIC EVENTS
-- Stores raw events as they occur. High volume, append-mostly.
-- =============================================================================

CREATE TABLE IF NOT EXISTS episodic_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          TEXT NOT NULL,              -- Sensor ID that generated event
    raw_text        TEXT NOT NULL,              -- Natural language description

    -- Embedding for semantic search (all-MiniLM-L6-v2 = 384 dims)
    embedding       vector(384),

    -- Salience scores (computed by Salience Gateway)
    salience        JSONB NOT NULL DEFAULT '{}',

    -- Domain-specific structured data (varies by source)
    structured      JSONB DEFAULT '{}',

    -- Entity references (extracted by Entity Extractor)
    entity_ids      UUID[] DEFAULT '{}',

    -- Lifecycle
    archived        BOOLEAN DEFAULT false,

    -- Metadata
    created_at      TIMESTAMPTZ DEFAULT now(),
    access_count    INTEGER DEFAULT 0
);

-- Indexes for episodic_events
CREATE INDEX IF NOT EXISTS idx_episodic_timestamp ON episodic_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_source ON episodic_events (source, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_embedding ON episodic_events
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_episodic_active ON episodic_events (timestamp DESC)
    WHERE archived = false;
CREATE INDEX IF NOT EXISTS idx_episodic_salience ON episodic_events USING GIN (salience);
CREATE INDEX IF NOT EXISTS idx_episodic_entities ON episodic_events USING GIN (entity_ids);

-- =============================================================================
-- ENTITIES
-- Known people, places, things, and concepts.
-- =============================================================================

CREATE TABLE IF NOT EXISTS entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identification
    canonical_name  TEXT NOT NULL,
    aliases         TEXT[] DEFAULT '{}',
    entity_type     TEXT NOT NULL,              -- person, place, item, concept, organization
    source          TEXT,                       -- Where first encountered

    -- Flexible attributes
    attributes      JSONB DEFAULT '{}',

    -- Embedding for semantic search
    embedding       vector(384),

    -- Temporal tracking
    first_seen      TIMESTAMPTZ DEFAULT now(),
    last_seen       TIMESTAMPTZ DEFAULT now(),
    mention_count   INTEGER DEFAULT 1,

    -- Deduplication
    merged_into     UUID REFERENCES entities(id),

    -- Metadata
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Indexes for entities
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
-- User traits and preferences with confidence and adaptation tracking.
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_profile (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Trait identification
    trait_category  TEXT NOT NULL,              -- personality, preference, behavior, context
    trait_name      TEXT NOT NULL,              -- e.g., "humor_preference", "play_style"

    -- Current value (EWMA-smoothed)
    value_float     FLOAT,                      -- For numeric traits
    value_text      TEXT,                       -- For categorical traits
    value_json      JSONB,                      -- For complex traits

    -- Adaptation tracking (EWMA state)
    short_term      FLOAT,                      -- Fast-moving average
    long_term       FLOAT,                      -- Slow-moving average
    stability       FLOAT DEFAULT 0,            -- How stable is short_term?

    -- Confidence
    confidence      FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    observation_count INTEGER DEFAULT 0,

    -- Embedding for semantic queries
    embedding       vector(384),

    -- Provenance
    source_episodes UUID[] DEFAULT '{}',

    -- Lifecycle
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),

    UNIQUE (trait_category, trait_name)
);

-- Indexes for user_profile
CREATE INDEX IF NOT EXISTS idx_profile_category ON user_profile (trait_category);
CREATE INDEX IF NOT EXISTS idx_profile_confidence ON user_profile (confidence DESC);
CREATE INDEX IF NOT EXISTS idx_profile_embedding ON user_profile
    USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- HEURISTICS
-- System 1 fast rules derived from patterns.
-- =============================================================================

CREATE TABLE IF NOT EXISTS heuristics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Rule definition
    name            TEXT NOT NULL,
    condition       JSONB NOT NULL,             -- When to fire
    action          JSONB NOT NULL,             -- What to do

    -- Confidence and provenance
    confidence      FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    source_pattern_ids UUID[] DEFAULT '{}',

    -- Usage tracking
    last_fired      TIMESTAMPTZ,
    fire_count      INTEGER DEFAULT 0,
    success_count   INTEGER DEFAULT 0,

    -- Lifecycle
    frozen          BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Indexes for heuristics
CREATE INDEX IF NOT EXISTS idx_heuristics_condition ON heuristics USING GIN (condition);
CREATE INDEX IF NOT EXISTS idx_heuristics_confidence ON heuristics (confidence DESC)
    WHERE frozen = FALSE;

-- =============================================================================
-- FEEDBACK EVENTS
-- Records explicit and implicit user feedback for learning.
-- =============================================================================

CREATE TABLE IF NOT EXISTS feedback_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- What was the feedback about
    target_type     TEXT NOT NULL,              -- 'action', 'suggestion', 'heuristic', 'pattern'
    target_id       UUID,
    target_context  JSONB DEFAULT '{}',

    -- Feedback signal
    feedback_type   TEXT NOT NULL,              -- 'explicit_positive', 'explicit_negative', etc.
    feedback_value  FLOAT,                      -- -1.0 to 1.0 for graded feedback
    feedback_text   TEXT,

    -- Signal strength
    weight          FLOAT NOT NULL DEFAULT 1.0 CHECK (weight BETWEEN 0 AND 1),

    -- Processing status
    processed       BOOLEAN DEFAULT FALSE,
    processed_at    TIMESTAMPTZ,

    -- Metadata
    source          TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Indexes for feedback_events
CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON feedback_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_target ON feedback_events (target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_feedback_unprocessed ON feedback_events (timestamp)
    WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback_events (feedback_type);
