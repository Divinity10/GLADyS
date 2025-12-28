# ADR-0004: Memory Schema Details

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Date** | 2025-01-27 |
| **Owner** | Mike Mulcahy (Divinity10) |
| **Contributors** | Scott |
| **Depends On** | ADR-0001 |

---

## 1. Context and Problem Statement

The GLADyS requires a memory system that supports:
- Fast retrieval for real-time interaction (~50ms budget)
- Semantic search for contextually relevant memories
- Structured queries for filtering by time, source, salience
- Long-term storage with configurable retention
- Background consolidation and extraction (sleep cycle)
- Adaptive user profiling with uncertainty quantification

This ADR defines the memory schema, hierarchical storage architecture, caching strategy, and query patterns.

---

## 2. Decision Drivers

1. **Latency:** Memory retrieval must complete within ~50ms to meet 1000ms end-to-end target
2. **Semantic capability:** Must find conceptually related memories, not just keyword matches
3. **Scalability:** Handle unbounded event types as sensors expand
4. **Flexibility:** Mix of structured queries and vector similarity search
5. **Consolidation:** Support human-brain-inspired memory processing during "sleep"
6. **Adaptability:** Learn user preferences over time with appropriate uncertainty
7. **Recoverability:** Backup and restore without data loss

---

## 3. Decision

Implement a hierarchical memory architecture inspired by CPU cache design, with PostgreSQL + pgvector as the persistent store. Use EWMA-based adaptation for user profiling and time-based partitioning for episodic events.

---

## 4. Memory Hierarchy

### 4.1 Overview

| Level | Name | Storage | Capacity | Access Time | Contents |
|-------|------|---------|----------|-------------|----------|
| L0 | Context Window | LLM prompt | ~8-32K tokens | 0ms | Current event, recent buffer, active profile |
| L1 | Hot Cache | In-memory (Python dict + list) | ~500-1000 events | <5ms | Recent events, high-salience, frequently accessed |
| L2 | Warm Buffer | In-memory (ring buffer) | ~5000-10000 events | <20ms | Last 30 min, pending DB write |
| L3 | Database Hot | PostgreSQL (RAM) | ~100K-1M rows | ~50-100ms | Last 24h-7d, indexed, queryable |
| L4 | Database Cold | PostgreSQL (disk) | Unbounded | ~200-500ms | Archived, compressed, rarely accessed |

### 4.2 Level 0: Context Window

Directly embedded in LLM prompt. Managed by Executive.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CONTEXT WINDOW (L0)                                                    │
│                                                                         │
│  Contents:                                                              │
│  ├── System prompt + personality                                        │
│  ├── Current event being evaluated                                      │
│  ├── Recent events (last 1-2 min, pre-tokenized)                        │
│  ├── Retrieved relevant memories (from L1-L3)                           │
│  ├── Active user profile summary                                        │
│  └── Current focus/goal context                                         │
│                                                                         │
│  Size: Limited by model context window                                  │
│  Eviction: Sliding window, oldest events removed first                  │
│  Update: Every tick                                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Level 1: Hot Cache

In-memory cache for fastest access. Managed by Memory Controller.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  HOT CACHE (L1)                                                         │
│                                                                         │
│  Data Structures:                                                       │
│  ├── event_by_id: Dict[UUID, Event]        # O(1) lookup                │
│  ├── events_by_time: SortedList[Event]     # O(log n) range queries     │
│  ├── events_by_source: Dict[str, List]     # O(1) source filter         │
│  ├── entity_cache: Dict[UUID, Entity]      # O(1) entity lookup         │
│  └── salience_cache: Dict[hash, Salience]  # O(1) salience reuse        │
│                                                                         │
│  Capacity: ~500-1000 events, ~100 entities                              │
│  Eviction: LRU weighted by salience (high salience = longer retention)  │
│  Population: Recent events + query results promoted from L2/L3          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Eviction Policy:**

```python
def eviction_score(event):
    """Lower score = evict first"""
    age_minutes = (now() - event.timestamp).total_seconds() / 60
    recency_score = 1.0 / (1 + age_minutes * 0.1)
    
    salience_score = max(
        event.salience.threat,
        event.salience.opportunity,
        event.salience.goal_relevance
    )
    
    access_score = event.access_count * 0.1
    
    return recency_score + salience_score + access_score
```

### 4.4 Level 2: Warm Buffer

In-memory ring buffer for recent events not yet persisted.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  WARM BUFFER (L2)                                                       │
│                                                                         │
│  Structure: Ring buffer with lazy indexing                              │
│                                                                         │
│  ├── buffer: CircularBuffer[Event]         # Fixed size, overwrites    │
│  ├── time_index: SortedDict[timestamp, idx] # Built on-demand          │
│  └── pending_embeddings: Queue[Event]      # Background embedding gen   │
│                                                                         │
│  Capacity: ~5000-10000 events (~30 min at high tick rate)               │
│  Flush: Batch write to L3 every 5 min or when buffer 80% full           │
│  Embeddings: Computed lazily or in background thread                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.5 Level 3: Database Hot (PostgreSQL)

Primary persistent storage with full indexing.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  DATABASE HOT (L3)                                                      │
│                                                                         │
│  Tables:                                                                │
│  ├── episodic_events_current   # Last 24h, heavily indexed              │
│  ├── episodic_events_recent    # 1-7 days, indexed                      │
│  ├── semantic_facts            # Derived knowledge                      │
│  ├── user_profile              # User traits and preferences            │
│  └── entities                  # Known people, places, things           │
│                                                                         │
│  PostgreSQL config: shared_buffers sized to keep hot tables in RAM      │
│  Indexes: B-tree on time/source, pgvector HNSW on embeddings            │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.6 Level 4: Database Cold (Archived)

Compressed, rarely-accessed historical data.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  DATABASE COLD (L4)                                                     │
│                                                                         │
│  Tables:                                                                │
│  └── episodic_events_archive   # Older than retention threshold         │
│                                                                         │
│  Characteristics:                                                       │
│  ├── Summarized (raw text condensed)                                    │
│  ├── Compressed (TOAST compression)                                     │
│  ├── Minimal indexes (timestamp only)                                   │
│  └── Accessed only for historical queries                               │
│                                                                         │
│  Retention: Configurable (default: 90 days, then purge)                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Database Schema

### 5.1 Episodic Events Table

Stores raw events as they occur. High volume, append-mostly.

```sql
-- Partitioned by time for efficient queries and archival
CREATE TABLE episodic_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          TEXT NOT NULL,              -- Sensor ID that generated event
    raw_text        TEXT NOT NULL,              -- Natural language description
    
    -- Embeddings for semantic search
    embedding       vector(384),                -- all-MiniLM-L6-v2 dimensions
    
    -- Salience scores (computed by Salience Gateway)
    salience        JSONB NOT NULL DEFAULT '{}',
    /*
        {
            "threat": 0.0-1.0,
            "opportunity": 0.0-1.0,
            "humor": 0.0-1.0,
            "novelty": 0.0-1.0,
            "goal_relevance": 0.0-1.0,
            "social": 0.0-1.0,
            "emotional": -1.0-1.0,
            "actionability": 0.0-1.0,
            "habituation": 0.0-1.0
        }
    */
    
    -- Domain-specific structured data (varies by source)
    structured      JSONB DEFAULT '{}',
    /*
        For minecraft sensor:
        {
            "event_type": "player_spotted",
            "entity": "xX_Slayer_Xx",
            "coordinates": [100, 64, -200],
            "health": 0.8
        }
    */
    
    -- Entity references (extracted by Entity Extractor)
    entity_ids      UUID[] DEFAULT '{}',
    
    -- Lifecycle
    archived        BOOLEAN DEFAULT false,
    summarized_into UUID REFERENCES semantic_facts(id),
    
    -- Metadata
    created_at      TIMESTAMPTZ DEFAULT now(),
    access_count    INTEGER DEFAULT 0
) PARTITION BY RANGE (timestamp);

-- Partitions
CREATE TABLE episodic_events_current PARTITION OF episodic_events
    FOR VALUES FROM (now() - interval '1 day') TO (MAXVALUE);

CREATE TABLE episodic_events_recent PARTITION OF episodic_events
    FOR VALUES FROM (now() - interval '7 days') TO (now() - interval '1 day');

CREATE TABLE episodic_events_archive PARTITION OF episodic_events
    FOR VALUES FROM (MINVALUE) TO (now() - interval '7 days');

-- Indexes
CREATE INDEX idx_episodic_timestamp ON episodic_events (timestamp DESC);
CREATE INDEX idx_episodic_source ON episodic_events (source, timestamp DESC);
CREATE INDEX idx_episodic_embedding ON episodic_events 
    USING hnsw (embedding vector_cosine_ops) 
    WITH (m = 16, ef_construction = 64);

-- Partial index for non-archived events (most queries)
CREATE INDEX idx_episodic_active ON episodic_events (timestamp DESC) 
    WHERE archived = false;

-- GIN index for salience JSONB queries
CREATE INDEX idx_episodic_salience ON episodic_events USING GIN (salience);

-- GIN index for entity references
CREATE INDEX idx_episodic_entities ON episodic_events USING GIN (entity_ids);
```

### 5.2 Semantic Facts Table

Derived knowledge in subject-predicate-object form. Lower volume, higher value.

```sql
CREATE TABLE semantic_facts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Triple structure
    subject_entity  UUID REFERENCES entities(id),
    subject_text    TEXT NOT NULL,              -- Fallback if no entity linked
    predicate       TEXT NOT NULL,              -- Relationship type
    object_entity   UUID REFERENCES entities(id),
    object_text     TEXT,                       -- Fallback or literal value
    
    -- Embedding for semantic search
    embedding       vector(384),
    
    -- Confidence and provenance
    confidence      FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    source_episodes UUID[] DEFAULT '{}',        -- Episodes that support this fact
    
    -- Lifecycle
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    superseded_by   UUID REFERENCES semantic_facts(id),
    
    -- Prevent duplicate facts
    UNIQUE (subject_text, predicate, object_text) 
        WHERE superseded_by IS NULL
);

-- Indexes
CREATE INDEX idx_facts_subject ON semantic_facts (subject_entity) 
    WHERE superseded_by IS NULL;
CREATE INDEX idx_facts_predicate ON semantic_facts (predicate) 
    WHERE superseded_by IS NULL;
CREATE INDEX idx_facts_object ON semantic_facts (object_entity) 
    WHERE superseded_by IS NULL;
CREATE INDEX idx_facts_embedding ON semantic_facts 
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_facts_confidence ON semantic_facts (confidence DESC) 
    WHERE superseded_by IS NULL;
```

**Example Facts:**

| subject_text | predicate | object_text | confidence |
|--------------|-----------|-------------|------------|
| xX_Slayer_Xx | is_hostile | true | 0.85 |
| xX_Slayer_Xx | last_seen_at | Nether Portal | 0.95 |
| User | prefers | diamond_sword over iron_sword | 0.70 |
| User | struggles_with | redstone_circuits | 0.60 |

### 5.3 User Profile Table

User traits and preferences with confidence and adaptation tracking.

```sql
CREATE TABLE user_profile (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Trait identification
    trait_category  TEXT NOT NULL,              -- personality, preference, behavior, context
    trait_name      TEXT NOT NULL,              -- e.g., "humor_preference", "play_style"
    
    -- Current value (EWMA-smoothed)
    value_float     FLOAT,                      -- For numeric traits
    value_text      TEXT,                       -- For categorical traits
    value_json      JSONB,                      -- For complex traits
    
    -- Adaptation tracking (EWMA state)
    short_term      FLOAT,                      -- Fast-moving average (α = 0.3-0.5)
    long_term       FLOAT,                      -- Slow-moving average (β = 0.05-0.1)
    stability       FLOAT DEFAULT 0,            -- How stable is short_term? (for promotion)
    
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

-- Indexes
CREATE INDEX idx_profile_category ON user_profile (trait_category);
CREATE INDEX idx_profile_confidence ON user_profile (confidence DESC);
CREATE INDEX idx_profile_embedding ON user_profile 
    USING hnsw (embedding vector_cosine_ops);
```

**EWMA Adaptation Logic:**

```python
class UserTraitAdapter:
    """
    TCP/IP-inspired adaptation for user traits.
    Short-term responds quickly, long-term updates only when stable.
    """
    
    ALPHA = 0.4          # Short-term learning rate
    BETA = 0.08          # Long-term learning rate
    STABILITY_THRESHOLD = 0.1  # Variance threshold for promotion
    STABILITY_WINDOW = 10      # Observations to measure stability
    
    def __init__(self, trait):
        self.short_term = trait.short_term or trait.value_float or 0.5
        self.long_term = trait.long_term or trait.value_float or 0.5
        self.recent_values = []
    
    def observe(self, new_value):
        """Update based on new observation."""
        # Update short-term (fast adaptation)
        self.short_term = self.ALPHA * new_value + (1 - self.ALPHA) * self.short_term
        
        # Track recent values for stability
        self.recent_values.append(self.short_term)
        if len(self.recent_values) > self.STABILITY_WINDOW:
            self.recent_values.pop(0)
        
        # Check stability
        if len(self.recent_values) >= self.STABILITY_WINDOW:
            variance = statistics.variance(self.recent_values)
            if variance < self.STABILITY_THRESHOLD:
                # Stable: promote to long-term
                self.long_term = self.BETA * self.short_term + (1 - self.BETA) * self.long_term
        
        return self.short_term, self.long_term
    
    def get_effective_value(self):
        """Return value to use for decisions."""
        # Weight by stability: more stable = trust long-term more
        stability = self._calculate_stability()
        return stability * self.long_term + (1 - stability) * self.short_term
```

**Example Traits:**

| trait_category | trait_name | value_float | short_term | long_term | confidence |
|----------------|------------|-------------|------------|-----------|------------|
| personality | sarcasm_tolerance | 0.8 | 0.82 | 0.78 | 0.85 |
| personality | verbosity_preference | 0.3 | 0.25 | 0.35 | 0.70 |
| preference | response_speed | 0.7 | 0.7 | 0.7 | 0.90 |
| behavior | play_style_aggressive | 0.6 | 0.55 | 0.62 | 0.65 |
| context | skill_level_minecraft | 0.7 | 0.72 | 0.68 | 0.80 |

### 5.4 Entities Table

Known people, places, things, and concepts.

```sql
CREATE TABLE entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identification
    canonical_name  TEXT NOT NULL,
    aliases         TEXT[] DEFAULT '{}',
    entity_type     TEXT NOT NULL,              -- person, place, item, concept, organization
    source          TEXT,                       -- Where first encountered
    
    -- Flexible attributes
    attributes      JSONB DEFAULT '{}',
    /*
        For a player:
        {
            "threat_level": 0.8,
            "relationship": "hostile",
            "last_known_location": "Nether",
            "weapons_observed": ["diamond_sword", "bow"],
            "interaction_count": 15
        }
    */
    
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

-- Indexes
CREATE INDEX idx_entities_name ON entities (canonical_name) 
    WHERE merged_into IS NULL;
CREATE INDEX idx_entities_type ON entities (entity_type) 
    WHERE merged_into IS NULL;
CREATE INDEX idx_entities_aliases ON entities USING GIN (aliases) 
    WHERE merged_into IS NULL;
CREATE INDEX idx_entities_embedding ON entities 
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_entities_last_seen ON entities (last_seen DESC) 
    WHERE merged_into IS NULL;

-- Full text search on name and aliases
CREATE INDEX idx_entities_fts ON entities 
    USING GIN (to_tsvector('english', canonical_name || ' ' || array_to_string(aliases, ' ')));
```

**Example Entities:**

| canonical_name | entity_type | aliases | attributes |
|----------------|-------------|---------|------------|
| xX_Slayer_Xx | person | ["Slayer", "that guy"] | {"threat_level": 0.8, "relationship": "hostile"} |
| Diamond Mine | place | ["the mine", "home base mine"] | {"coordinates": [100, 12, -50], "safety": 0.9} |
| Enchanted Diamond Sword | item | ["my sword", "Slicer"] | {"enchantments": ["Sharpness V"], "durability": 0.6} |

---

## 6. Short-Term Memory Structure

In-memory representation for events before persistence.

### 6.1 Event Model

```python
@dataclass
class Event:
    """In-memory event representation."""
    
    # Identity
    id: UUID
    timestamp: datetime
    source: str                     # Sensor ID
    
    # Content
    raw_text: str                   # Natural language description
    structured: Dict[str, Any]      # Domain-specific fields
    
    # Computed fields
    salience: SalienceVector
    embedding: Optional[np.ndarray] # Computed lazily
    tokens: Optional[List[int]]     # Pre-tokenized for LLM injection
    entity_ids: List[UUID]          # Extracted entity references
    
    # Cache metadata
    access_count: int = 0
    last_accessed: datetime = None
    
    def to_context_string(self) -> str:
        """Format for LLM context injection."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] [{self.source}] {self.raw_text}"
    
    def compute_embedding(self, model):
        """Lazy embedding computation."""
        if self.embedding is None:
            self.embedding = model.encode(self.raw_text)
        return self.embedding


@dataclass
class SalienceVector:
    """Multi-dimensional salience scores."""
    
    threat: float = 0.0
    opportunity: float = 0.0
    humor: float = 0.0
    novelty: float = 0.0
    goal_relevance: float = 0.0
    social: float = 0.0
    emotional: float = 0.0         # -1 to 1
    actionability: float = 0.0
    habituation: float = 0.0
    
    def max_score(self) -> float:
        """Highest salience dimension (ignoring habituation)."""
        return max(
            self.threat, self.opportunity, self.humor,
            self.novelty, self.goal_relevance, self.social,
            abs(self.emotional), self.actionability
        )
    
    def should_suppress(self) -> bool:
        """High habituation = suppress this event."""
        return self.habituation > 0.8 and self.max_score() < 0.5
```

### 6.2 Memory Buffer Implementation

```python
class MemoryBuffer:
    """
    Hierarchical memory buffer (L1 + L2).
    """
    
    def __init__(
        self,
        l1_capacity: int = 1000,
        l2_capacity: int = 10000,
        flush_threshold: float = 0.8,
        flush_interval_seconds: int = 300
    ):
        # L1: Hot cache
        self.l1_by_id: Dict[UUID, Event] = {}
        self.l1_by_time: SortedList[Event] = SortedList(key=lambda e: e.timestamp)
        self.l1_by_source: Dict[str, List[Event]] = defaultdict(list)
        self.l1_capacity = l1_capacity
        
        # L2: Warm buffer (ring buffer)
        self.l2_buffer: Deque[Event] = deque(maxlen=l2_capacity)
        self.l2_capacity = l2_capacity
        
        # Entity cache
        self.entity_cache: Dict[UUID, Entity] = {}
        
        # Flush tracking
        self.last_flush = datetime.now()
        self.flush_threshold = flush_threshold
        self.flush_interval = flush_interval_seconds
        self.pending_persist: List[Event] = []
    
    def add(self, event: Event):
        """Add event to memory buffer."""
        # Always add to L1
        self._add_to_l1(event)
        
        # Also add to L2 for persistence queue
        self.l2_buffer.append(event)
        self.pending_persist.append(event)
        
        # Check if flush needed
        if self._should_flush():
            self._flush_to_database()
    
    def _add_to_l1(self, event: Event):
        """Add to L1 hot cache with eviction."""
        if len(self.l1_by_id) >= self.l1_capacity:
            self._evict_from_l1()
        
        self.l1_by_id[event.id] = event
        self.l1_by_time.add(event)
        self.l1_by_source[event.source].append(event)
    
    def _evict_from_l1(self, count: int = 100):
        """Evict lowest-scored events from L1."""
        scored = [(self._eviction_score(e), e) for e in self.l1_by_id.values()]
        scored.sort(key=lambda x: x[0])
        
        for _, event in scored[:count]:
            del self.l1_by_id[event.id]
            self.l1_by_time.remove(event)
            self.l1_by_source[event.source].remove(event)
    
    def _eviction_score(self, event: Event) -> float:
        """Lower score = evict first."""
        age_minutes = (datetime.now() - event.timestamp).total_seconds() / 60
        recency = 1.0 / (1 + age_minutes * 0.1)
        salience = event.salience.max_score()
        access = event.access_count * 0.1
        return recency + salience + access
    
    def query_recent(
        self,
        minutes: int = 5,
        source: Optional[str] = None,
        min_salience: Optional[float] = None
    ) -> List[Event]:
        """Query recent events from L1."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        
        if source:
            events = [e for e in self.l1_by_source[source] if e.timestamp > cutoff]
        else:
            # Use sorted list for efficient range query
            events = [e for e in self.l1_by_time if e.timestamp > cutoff]
        
        if min_salience:
            events = [e for e in events if e.salience.max_score() >= min_salience]
        
        # Mark as accessed
        for e in events:
            e.access_count += 1
            e.last_accessed = datetime.now()
        
        return events
    
    def _should_flush(self) -> bool:
        """Check if we should flush to database."""
        buffer_full = len(self.pending_persist) > self.l2_capacity * self.flush_threshold
        time_elapsed = (datetime.now() - self.last_flush).total_seconds() > self.flush_interval
        return buffer_full or time_elapsed
    
    async def _flush_to_database(self):
        """Batch write pending events to L3."""
        if not self.pending_persist:
            return
        
        events_to_flush = self.pending_persist.copy()
        self.pending_persist.clear()
        self.last_flush = datetime.now()
        
        # Batch insert to PostgreSQL
        await self.db.batch_insert_events(events_to_flush)
```

---

## 7. Query Patterns

### 7.1 Query Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          QUERY FLOW                                     │
│                                                                         │
│  Query arrives                                                          │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────┐  hit   Return immediately                                  │
│  │ Check L1 │──────► (update access count)                              │
│  └────┬────┘                                                            │
│       │ miss                                                            │
│       ▼                                                                 │
│  ┌─────────┐  hit   Return + promote to L1                              │
│  │ Check L2 │──────► (if high salience or frequently accessed)          │
│  └────┬────┘                                                            │
│       │ miss                                                            │
│       ▼                                                                 │
│  ┌─────────┐        Return + promote subset to L1                       │
│  │ Query L3 │──────► (top results by relevance)                         │
│  └────┬────┘                                                            │
│       │ insufficient results                                            │
│       ▼                                                                 │
│  ┌─────────┐        Return + note for potential summarization           │
│  │ Query L4 │──────► (cold storage)                                     │
│  └─────────┘                                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Common Query Patterns

#### Recent Events by Source

```python
async def get_recent_by_source(
    source: str,
    minutes: int = 10,
    limit: int = 50
) -> List[Event]:
    """Get recent events from a specific sensor."""
    
    # Try L1 first
    events = self.buffer.query_recent(minutes=minutes, source=source)
    if len(events) >= limit:
        return events[:limit]
    
    # Fall back to L3
    query = """
        SELECT * FROM episodic_events
        WHERE source = $1
          AND timestamp > now() - interval '%s minutes'
          AND archived = false
        ORDER BY timestamp DESC
        LIMIT $2
    """
    db_events = await self.db.fetch(query, source, minutes, limit)
    
    # Merge and dedupe
    all_events = self._merge_events(events, db_events)
    return all_events[:limit]
```

#### Semantic Similarity Search

```python
async def semantic_search(
    query_text: str,
    source_filter: Optional[str] = None,
    time_filter_hours: Optional[int] = None,
    salience_filter: Optional[Dict[str, float]] = None,
    limit: int = 10
) -> List[Event]:
    """Find semantically similar events."""
    
    # Generate query embedding
    query_embedding = self.embedding_model.encode(query_text)
    
    # Build query with filters
    conditions = ["archived = false"]
    params = [query_embedding, limit]
    
    if source_filter:
        conditions.append(f"source = ${len(params) + 1}")
        params.append(source_filter)
    
    if time_filter_hours:
        conditions.append(f"timestamp > now() - interval '{time_filter_hours} hours'")
    
    if salience_filter:
        for dim, threshold in salience_filter.items():
            conditions.append(f"(salience->>'{dim}')::float >= {threshold}")
    
    where_clause = " AND ".join(conditions)
    
    query = f"""
        SELECT *, embedding <=> $1 AS distance
        FROM episodic_events
        WHERE {where_clause}
        ORDER BY embedding <=> $1
        LIMIT $2
    """
    
    results = await self.db.fetch(query, *params)
    
    # Promote top results to L1
    for event in results[:3]:
        self.buffer.promote_to_l1(event)
    
    return results
```

#### Entity-Based Retrieval

```python
async def get_events_for_entity(
    entity_id: UUID,
    limit: int = 20
) -> List[Event]:
    """Get events involving a specific entity."""
    
    # Check entity cache
    entity = self.buffer.entity_cache.get(entity_id)
    if not entity:
        entity = await self.db.get_entity(entity_id)
        self.buffer.entity_cache[entity_id] = entity
    
    # Query events
    query = """
        SELECT * FROM episodic_events
        WHERE $1 = ANY(entity_ids)
          AND archived = false
        ORDER BY timestamp DESC
        LIMIT $2
    """
    
    return await self.db.fetch(query, entity_id, limit)
```

#### Composite Relevance Query

```python
async def get_relevant_memories(
    current_context: Context,
    limit: int = 10
) -> List[Event]:
    """
    Multi-factor relevance search combining:
    - Semantic similarity
    - Recency
    - Entity overlap
    - Salience alignment
    """
    
    query_embedding = self.embedding_model.encode(current_context.summary)
    
    query = """
        WITH scored AS (
            SELECT 
                e.*,
                -- Semantic similarity (0-1, higher is better)
                1 - (embedding <=> $1) AS semantic_score,
                
                -- Recency score (exponential decay)
                EXP(-EXTRACT(EPOCH FROM (now() - timestamp)) / 3600) AS recency_score,
                
                -- Entity overlap (0 or 1)
                CASE WHEN entity_ids && $2 THEN 0.5 ELSE 0 END AS entity_score,
                
                -- Salience alignment
                GREATEST(
                    (salience->>'threat')::float * $3,
                    (salience->>'opportunity')::float * $4,
                    (salience->>'goal_relevance')::float * $5
                ) AS salience_score
                
            FROM episodic_events e
            WHERE archived = false
              AND timestamp > now() - interval '24 hours'
        )
        SELECT *,
            (0.4 * semantic_score + 
             0.3 * recency_score + 
             0.15 * entity_score + 
             0.15 * salience_score) AS relevance
        FROM scored
        ORDER BY relevance DESC
        LIMIT $6
    """
    
    params = [
        query_embedding,
        current_context.entity_ids,
        current_context.threat_weight,
        current_context.opportunity_weight,
        current_context.goal_weight,
        limit
    ]
    
    return await self.db.fetch(query, *params)
```

---

## 8. Background Jobs (Sleep Cycle)

### 8.1 Job Schedule

| Job | Frequency | Purpose |
|-----|-----------|---------|
| Entity Extractor | Continuous | Identify entities in new events |
| Embedding Generator | Continuous | Compute embeddings for events without them |
| Fact Extractor | Every 10 min | Derive semantic facts from episodes |
| Profile Updater | Every hour | Update user traits from observations |
| Memory Consolidator | Nightly | Summarize and compress old episodes |
| Integrity Checker | Nightly | Verify data integrity via hashing |
| Backup | Nightly | Point-in-time backup |
| Partition Manager | Weekly | Create new partitions, archive old |

### 8.2 Entity Extractor

```python
class EntityExtractor:
    """Extract and link entities from events."""
    
    async def process_event(self, event: Event):
        """Extract entities from a single event."""
        
        # Use small LLM to extract entity mentions
        prompt = f"""
        Extract entities (people, places, items) from this text.
        Return JSON: {{"entities": [{{"name": "...", "type": "...", "aliases": []}}]}}
        
        Text: {event.raw_text}
        """
        
        result = await self.llm.generate(prompt)
        entities = json.loads(result)["entities"]
        
        linked_ids = []
        for entity_data in entities:
            # Try to match existing entity
            existing = await self.find_existing_entity(entity_data["name"])
            
            if existing:
                # Update existing
                await self.update_entity(existing, event)
                linked_ids.append(existing.id)
            else:
                # Create new
                new_entity = await self.create_entity(entity_data, event)
                linked_ids.append(new_entity.id)
        
        # Update event with entity links
        await self.db.update_event_entities(event.id, linked_ids)
    
    async def find_existing_entity(self, name: str) -> Optional[Entity]:
        """Find entity by name or alias."""
        query = """
            SELECT * FROM entities
            WHERE merged_into IS NULL
              AND (canonical_name ILIKE $1 OR $1 = ANY(aliases))
            LIMIT 1
        """
        return await self.db.fetchone(query, name)
```

### 8.3 Fact Extractor

```python
class FactExtractor:
    """Extract semantic facts from episodic events."""
    
    async def run_extraction_cycle(self):
        """Process recent events and extract facts."""
        
        # Get events not yet processed for facts
        events = await self.db.fetch("""
            SELECT * FROM episodic_events
            WHERE timestamp > now() - interval '1 hour'
              AND summarized_into IS NULL
              AND archived = false
            ORDER BY timestamp
            LIMIT 100
        """)
        
        # Batch for LLM processing
        batch_text = "\n".join([
            f"[{e.timestamp}] {e.raw_text}" for e in events
        ])
        
        prompt = f"""
        Extract factual statements from these events.
        Return JSON array of facts:
        [{{
            "subject": "entity name",
            "predicate": "relationship",
            "object": "value or entity",
            "confidence": 0.0-1.0
        }}]
        
        Events:
        {batch_text}
        """
        
        result = await self.llm.generate(prompt)
        facts = json.loads(result)
        
        for fact_data in facts:
            await self.upsert_fact(fact_data, events)
    
    async def upsert_fact(self, fact_data: Dict, source_events: List[Event]):
        """Insert or update a semantic fact."""
        
        existing = await self.db.fetchone("""
            SELECT * FROM semantic_facts
            WHERE subject_text = $1 
              AND predicate = $2 
              AND object_text = $3
              AND superseded_by IS NULL
        """, fact_data["subject"], fact_data["predicate"], fact_data["object"])
        
        if existing:
            # Update confidence (weighted by new evidence)
            new_confidence = (
                existing.confidence * 0.7 + 
                fact_data["confidence"] * 0.3
            )
            
            await self.db.execute("""
                UPDATE semantic_facts
                SET confidence = $1,
                    source_episodes = source_episodes || $2,
                    updated_at = now()
                WHERE id = $3
            """, new_confidence, [e.id for e in source_events], existing.id)
        else:
            # Insert new fact
            await self.db.execute("""
                INSERT INTO semantic_facts 
                (subject_text, predicate, object_text, confidence, source_episodes, embedding)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, 
                fact_data["subject"],
                fact_data["predicate"],
                fact_data["object"],
                fact_data["confidence"],
                [e.id for e in source_events],
                self.embedding_model.encode(
                    f"{fact_data['subject']} {fact_data['predicate']} {fact_data['object']}"
                )
            )
```

### 8.4 Memory Consolidator (Sleep Cycle)

```python
class MemoryConsolidator:
    """
    Consolidate and compress old memories.
    Runs during 'sleep' period.
    """
    
    async def run_nightly_consolidation(self):
        """Full consolidation cycle."""
        
        # 1. Summarize old episodic events
        await self.summarize_old_episodes()
        
        # 2. Update fact confidences (decay unused facts)
        await self.decay_unused_facts()
        
        # 3. Merge duplicate entities
        await self.merge_duplicate_entities()
        
        # 4. Archive old events
        await self.archive_events()
        
        # 5. Run integrity check
        await self.integrity_check()
        
        # 6. Backup
        await self.backup()
    
    async def summarize_old_episodes(self):
        """Summarize episodes older than threshold into semantic facts."""
        
        # Get events older than 7 days, not yet summarized
        events = await self.db.fetch("""
            SELECT * FROM episodic_events
            WHERE timestamp < now() - interval '7 days'
              AND summarized_into IS NULL
              AND archived = false
            ORDER BY timestamp
            LIMIT 500
        """)
        
        if not events:
            return
        
        # Group by source for coherent summarization
        by_source = defaultdict(list)
        for event in events:
            by_source[event.source].append(event)
        
        for source, source_events in by_source.items():
            await self.summarize_event_batch(source, source_events)
    
    async def summarize_event_batch(self, source: str, events: List[Event]):
        """Summarize a batch of events into facts."""
        
        batch_text = "\n".join([e.raw_text for e in events])
        
        prompt = f"""
        Summarize these {source} events into key facts.
        Focus on: patterns, significant events, learned information.
        
        Events:
        {batch_text}
        
        Return JSON:
        {{
            "facts": [{{"subject": "...", "predicate": "...", "object": "...", "confidence": 0.0-1.0}}],
            "summary": "One paragraph summary"
        }}
        """
        
        result = await self.llm.generate(prompt)
        data = json.loads(result)
        
        # Create summary fact
        summary_fact = await self.db.insert_returning("""
            INSERT INTO semantic_facts (subject_text, predicate, object_text, confidence, source_episodes)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """,
            source,
            "period_summary",
            data["summary"],
            0.8,
            [e.id for e in events]
        )
        
        # Mark events as summarized
        await self.db.execute("""
            UPDATE episodic_events
            SET summarized_into = $1
            WHERE id = ANY($2)
        """, summary_fact.id, [e.id for e in events])
        
        # Insert derived facts
        for fact in data["facts"]:
            await self.upsert_fact(fact, events)
    
    async def archive_events(self):
        """Move old, summarized events to archive partition."""
        
        await self.db.execute("""
            UPDATE episodic_events
            SET archived = true
            WHERE timestamp < now() - interval '7 days'
              AND summarized_into IS NOT NULL
              AND archived = false
        """)
    
    async def integrity_check(self):
        """Verify data integrity."""
        
        # Check for orphaned references
        orphaned_facts = await self.db.fetch("""
            SELECT id FROM semantic_facts
            WHERE subject_entity IS NOT NULL
              AND subject_entity NOT IN (SELECT id FROM entities WHERE merged_into IS NULL)
        """)
        
        if orphaned_facts:
            logger.warning(f"Found {len(orphaned_facts)} orphaned fact references")
        
        # Verify partition boundaries
        # ... additional checks
```

---

## 9. Caching Strategy

### 9.1 What to Cache (Phase 1 - Implement Now)

| Cache | Contents | Size | Eviction |
|-------|----------|------|----------|
| **L1 Event Cache** | Recent events, high-salience events | 1000 events | LRU + salience weighted |
| **Entity Cache** | Frequently accessed entities | 100 entities | LRU |

### 9.2 When to Add More Caching (Phase 2)

| Cache | Trigger Metric | Threshold | Implementation |
|-------|---------------|-----------|----------------|
| **Salience Result Cache** | Duplicate salience computations | > 20% of computations | Hash(event_text) → SalienceVector |
| **Query Result Cache** | Repeated identical queries | > 10% of queries | Hash(query_params) → Result IDs |
| **Embedding Cache** | Embedding computation time | > 20% of retrieval latency | Hash(text) → embedding vector |

### 9.3 Cache Invalidation Rules

| Cache | Invalidation Trigger |
|-------|---------------------|
| Event Cache | Event updated, event archived |
| Entity Cache | Entity attributes updated, entity merged |
| Salience Cache | TTL (5 min) or context change |
| Query Cache | New events added to relevant scope |

---

## 10. Complexity Addition Framework

### 10.1 Metrics to Monitor

```python
# Instrument these from day one
METRICS = {
    # Latency
    "memory_retrieval_p50_ms": Histogram,
    "memory_retrieval_p95_ms": Histogram,
    "memory_retrieval_p99_ms": Histogram,
    "embedding_computation_ms": Histogram,
    "db_query_ms": Histogram,
    
    # Cache effectiveness
    "l1_cache_hit_rate": Gauge,
    "l1_cache_size": Gauge,
    "entity_cache_hit_rate": Gauge,
    
    # Throughput
    "events_per_second": Counter,
    "queries_per_second": Counter,
    "db_writes_per_second": Counter,
    
    # Resource usage
    "memory_buffer_size": Gauge,
    "pending_persist_count": Gauge,
    "db_connection_pool_used": Gauge,
}
```

### 10.2 Decision Thresholds

| Observation | Threshold | Action |
|-------------|-----------|--------|
| P95 retrieval latency | > 50ms for 1 hour | Add/tune L1 cache |
| L1 hit rate | < 30% after 1 week | Adjust eviction policy or capacity |
| L1 hit rate | > 95% stable | May reduce cache size |
| Duplicate salience computations | > 20% | Add salience cache |
| Embedding computation | > 20% of query time | Add embedding cache |
| DB query time | > 100ms P95 | Add indexes or pre-filtering |
| Event backlog | > 1000 pending | Increase flush frequency |

### 10.3 Optimization Sequence

```
1. MEASURE baseline (1 week minimum)
       │
       ▼
2. IDENTIFY bottleneck from metrics
       │
       ├── Retrieval slow? ──► Check cache hit rate ──► Tune L1
       │
       ├── DB slow? ──► EXPLAIN queries ──► Add indexes or pre-filter
       │
       ├── Embedding slow? ──► Add embedding cache
       │
       └── Salience slow? ──► Add salience cache
       │
       ▼
3. IMPLEMENT single optimization
       │
       ▼
4. MEASURE impact (1 week)
       │
       ├── < 20% improvement? ──► Consider rollback
       │
       └── >= 20% improvement? ──► Document and keep
       │
       ▼
5. REPEAT from step 2
```

---

## 11. Backup and Recovery

### 11.1 Backup Strategy

| Component | Frequency | Method | Retention |
|-----------|-----------|--------|-----------|
| PostgreSQL full | Nightly | pg_dump | 7 days |
| PostgreSQL WAL | Continuous | pg_basebackup + archive | 24 hours |
| L1/L2 state | On shutdown | JSON export | 1 copy |

### 11.2 Recovery Scenarios

| Scenario | Recovery Method |
|----------|-----------------|
| Application crash | L1/L2 lost, rebuild from L3 on startup |
| Database corruption | Restore from last pg_dump + WAL replay |
| Accidental deletion | Point-in-time recovery from WAL |
| Full system loss | Restore from offsite backup |

---

## 12. Consequences

### 12.1 Positive

1. Hierarchical design matches access patterns (recent = fast)
2. Flexible schema handles unbounded event types
3. EWMA adaptation provides stable yet responsive user profiling
4. Time partitioning enables efficient archival
5. Clear upgrade path for adding caching layers

### 12.2 Negative

1. Multiple storage layers add operational complexity
2. Cache invalidation requires careful handling
3. Background jobs need monitoring and failure handling
4. Embedding computation adds latency (mitigated by lazy/background generation)

### 12.3 Risks

1. Cache staleness could cause inconsistent behavior
2. Partition management requires ongoing attention
3. LLM-based extraction quality varies (need validation)

---

## 13. Related Decisions

- ADR-0001: GLADyS Architecture
- ADR-0002: Hardware Requirements
- ADR-0003: Plugin Manifest Specification
- ADR-0005: gRPC Service Contracts
- ADR-0006: Observability & Monitoring
- ADR-0007: Adaptive Algorithms
- ADR-0008: Security and Privacy (data retention policies, memory consolidation)

---

## 14. Notes

The hierarchical memory design is inspired by CPU cache architecture but adapted for semantic (not address-based) access patterns. The key insight is that temporal locality (recent events accessed more) holds, but spatial locality must be replaced with semantic locality (related concepts accessed together).

EWMA adaptation for user profiles mirrors TCP congestion control: respond quickly to changes but don't overreact to noise. The stability check before long-term promotion prevents oscillation.

Start with L0 + L1 + L3 (skip L2 initially). Add L2 warm buffer only if flush-to-DB latency becomes problematic.
