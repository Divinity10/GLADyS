-- GLADyS Memory Subsystem - Relationships Schema
-- Semantic memory: entity relationships for context retrieval
-- See docs/design/questions/memory.md §24: LLM reasons, graph provides context

-- =============================================================================
-- RELATIONSHIPS
-- Connects entities for 1-2 hop context retrieval during LLM planning.
-- Not a graph DB - we're providing context, not running graph algorithms.
-- =============================================================================

CREATE TABLE IF NOT EXISTS relationships (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Subject -> Predicate -> Object
    subject_id      UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    predicate       TEXT NOT NULL,              -- e.g., 'has_character', 'plays_in', 'lives_at', 'works_at'
    object_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,

    -- Optional attributes for the relationship
    attributes      JSONB DEFAULT '{}',         -- e.g., {"since": "2024-01", "primary": true}

    -- Confidence in this relationship
    confidence      FLOAT DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),

    -- Provenance
    source          TEXT,                       -- Where we learned this: 'user', 'inferred', 'pack:minecraft'
    source_event_id UUID,                       -- Optional: episodic event that established this

    -- Lifecycle
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),

    -- Prevent duplicate relationships
    UNIQUE (subject_id, predicate, object_id)
);

-- Indexes for relationship traversal
-- Both directions needed for bidirectional context retrieval
CREATE INDEX IF NOT EXISTS idx_rel_subject ON relationships (subject_id);
CREATE INDEX IF NOT EXISTS idx_rel_object ON relationships (object_id);
CREATE INDEX IF NOT EXISTS idx_rel_predicate ON relationships (predicate);
CREATE INDEX IF NOT EXISTS idx_rel_confidence ON relationships (confidence DESC)
    WHERE confidence >= 0.5;

-- Composite index for "get all relationships for an entity"
CREATE INDEX IF NOT EXISTS idx_rel_entity_all ON relationships (subject_id, object_id);

-- =============================================================================
-- EXAMPLE DATA (for testing "Is Steve online?" scenario)
-- =============================================================================
-- Uncomment to seed test data:
--
-- INSERT INTO entities (canonical_name, entity_type, attributes) VALUES
--     ('Steve', 'person', '{"notes": "Friend of Mike"}'),
--     ('Buggy', 'game_character', '{"game": "minecraft"}'),
--     ('Minecraft', 'game', '{"platform": "pc"}');
--
-- INSERT INTO relationships (subject_id, predicate, object_id, source)
-- SELECT
--     (SELECT id FROM entities WHERE canonical_name = 'Steve'),
--     'has_character',
--     (SELECT id FROM entities WHERE canonical_name = 'Buggy'),
--     'user';
--
-- INSERT INTO relationships (subject_id, predicate, object_id, source)
-- SELECT
--     (SELECT id FROM entities WHERE canonical_name = 'Buggy'),
--     'plays_in',
--     (SELECT id FROM entities WHERE canonical_name = 'Minecraft'),
--     'user';
