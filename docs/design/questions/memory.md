# Memory Questions

Database schema, memory hierarchy, entity/relationship storage, and semantic memory architecture.

**Last updated**: 2026-01-25

---

## Open Questions

### Q: ADR-0004 Memory Schema Gaps (§16)

**Status**: Partially resolved
**Priority**: High (foundational)
**Created**: 2026-01-19

Deep review of ADR-0004 against ADR-0007, ADR-0009, ADR-0010, ADR-0012 reveals significant gaps. ADR-0004 was written before the learning and compaction ADRs and needs reconciliation.

#### Implemented Schema

| Gap | Status |
|-----|--------|
| Heuristic Store | **Implemented** - `heuristics` table exists (migrations 003, 008) |

#### Designed but Deferred

These schema changes are proposed in ADR-0004 but **not yet implemented**:

| Gap | Design Reference | Status |
|-----|------------------|--------|
| Bayesian Pattern Storage | `learned_patterns` table (ADR-0004 §5.5) | Deferred |
| Feedback Events | `feedback_events` table (ADR-0004 §5.7) | Deferred |
| Episodes Table | `episodes` + `episode_events` junction (§5.8-5.9) | Deferred |
| Staleness Tracking | `semantic_facts` column additions (§5.2) | Deferred |

#### Remaining Gaps

**User Profile Schema Drift**:
ADR-0004's `user_profile` table has simple EWMA fields. ADR-0007's `AdaptiveParameter` model adds:
- `bayesian_alpha`, `bayesian_beta` (Bayesian confidence)
- `bounds_min`, `bounds_max` (safety bounds)
- `frozen` (learning freeze)

**Need**: Reconcile schemas.

#### Cross-ADR Consistency Issues

| Aspect | ADR-0004 | ADR-0009 | Action |
|--------|----------|----------|--------|
| Compaction policy | Nightly consolidation | Configurable tiers | ADR-0004 should defer to ADR-0009 |
| Summary storage | `summarized_into UUID` | Richer schema | Add `memory_summaries` table |

| Aspect | ADR-0004 | ADR-0010 | Action |
|--------|----------|----------|--------|
| Fact derivation | LLM-based `FactExtractor` | Pattern Detector subsystem | ADR-0010 implies structured pipeline |
| Context-aware beliefs | Not mentioned | Context-specific beliefs | Add context_tags |

#### Performance Concerns

1. **HNSW Index on High-Volume Table**: Consider partial index (only non-archived), index rebuild during sleep mode, or IVFFlat alternative
2. **GIN Index on JSONB Salience**: Slow updates; consider extracting frequently-queried dimensions
3. **Partition Boundary Management**: `now()` evaluated at table creation; need scheduled job

#### Extensibility Concerns

1. **Embedding Model Lock-in**: `vector(384)` hardcodes dimension; document migration strategy
2. **Event Schema Versioning**: No schema registry for JSONB event types
3. **Multi-User Support**: ADR-0004 assumes single user

#### Open Questions

**High Priority**:
1. How does Executive know when to query Memory vs Audit?
2. What's the embedding migration strategy when models change?
3. How are context tags applied? Manual or automatic inference?

**Medium Priority**:
4. Who creates new time partitions? Scheduled job? Orchestrator?
5. When entities merge, who updates `entity_ids` arrays in `episodic_events`?
6. How does Memory Controller know when "sleep mode" is active?

---

## Resolved

### R: Semantic Memory Architecture (§24)

**Decision**: PostgreSQL for semantic memory (entities + relationships)
**Date**: 2026-01-24

#### Key Insight

The LLM does the reasoning, not the graph. The semantic memory is a knowledge store that provides context for LLM planning, not a reasoning engine.

For "Is Steve online?":
- **Not**: Graph mechanically traverses Steve → Buggy → Minecraft → check_status
- **Yes**: Retrieve Steve's context (1-2 hops), give to LLM, LLM creates a plan

#### Decisions

| Decision | Rationale |
|----------|-----------|
| **PostgreSQL for semantic memory** | Context retrieval (1-2 hops), not graph algorithms. Single DB simplifies joins with events/heuristics. |
| **LLM is a planner, not an answerer** | Executive creates executable plans; doesn't answer questions directly. |
| **Heuristics cache plans, not answers** | When heuristic fires, skip LLM planning step, still execute skills. |
| **Entity extraction + 1-2 hop expansion** | Context retrieval strategy for LLM prompts. |

#### Why Not Graph DB

| Factor | Assessment |
|--------|------------|
| Traversal depth needed | 1-2 hops for context (shallow) |
| Graph algorithms needed | No (no PageRank, community detection, etc.) |
| Join with other data | Yes (events, heuristics in PostgreSQL) |
| Operational complexity | Single DB preferred |

A personal assistant has hundreds to low thousands of entities with shallow relationships. PostgreSQL with simple joins handles this well.

#### Schema (Migration 002)

```sql
-- entities table (existing from 001)
CREATE TABLE entities (
    id              UUID PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    aliases         TEXT[] DEFAULT '{}',
    entity_type     TEXT NOT NULL,
    attributes      JSONB DEFAULT '{}',
    embedding       vector(384),
    first_seen      TIMESTAMPTZ,
    last_seen       TIMESTAMPTZ,
    mention_count   INTEGER DEFAULT 1,
    merged_into     UUID REFERENCES entities(id)
);

-- relationships table (new in 002)
CREATE TABLE relationships (
    id              UUID PRIMARY KEY,
    subject_id      UUID NOT NULL REFERENCES entities(id),
    predicate       TEXT NOT NULL,
    object_id       UUID NOT NULL REFERENCES entities(id),
    attributes      JSONB DEFAULT '{}',
    confidence      FLOAT DEFAULT 1.0,
    source          TEXT,
    source_event_id UUID,
    UNIQUE (subject_id, predicate, object_id)
);
```

#### Example Data

```
entities:
  - Steve (type=person)
  - Buggy (type=game_character)
  - Minecraft (type=game)

relationships:
  - Steve --[has_character]--> Buggy
  - Buggy --[plays_in]--> Minecraft
```

#### Context Retrieval for LLM Planning

```
User query: "Is Steve online?"

Context:
- Steve: person, friend
  - plays Minecraft as "Buggy"
  - uses Discord as "SteveD"

Available skills:
- minecraft: can check player status
- discord: can check user presence

What action should be taken?
```

---

## Inspiration Sources

| Source | Relevance |
|--------|-----------|
| CPU Cache Hierarchy | Direct inspiration for L0-L4 design |
| LSM Trees (RocksDB) | Write-optimized storage, tiered compaction |
| Hippocampal Indexing Theory | Neuroscience basis for semantic/episodic split |
| Complementary Learning Systems | Fast episodic + slow semantic validates dual-store |
| Facebook FAISS | ANN search tradeoffs (IVF vs HNSW) |
