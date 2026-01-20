# Archived: Memory Hierarchy L1/L2 Design

**Status**: Archived (deferred to post-MVP)
**Original Source**: ADR-0004 Section 4
**Archived Date**: 2026-01-20
**Archived By**: Architecture Review (Session 1)

---

## Why This Was Deferred

The L1 (Hot Cache) and L2 (Warm Buffer) memory tiers were designed as part of a 5-tier memory hierarchy inspired by CPU caches. During architecture review, this was identified as premature optimization:

1. **No measured need**: No performance data shows PostgreSQL direct access exceeds the 50ms latency budget
2. **Adds complexity**: Additional data structures, eviction policies, consistency management
3. **YAGNI**: MVP can validate if caching is needed with real usage patterns

**Trigger to reconsider**: If PostgreSQL query latency consistently exceeds 50ms under load, revisit L1/L2 caching.

---

## Original Design: Level 1 Hot Cache

From ADR-0004 Section 4.3:

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

### Eviction Policy

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

---

## Original Design: Level 2 Warm Buffer

From ADR-0004 Section 4.4:

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

### Purpose

The warm buffer was designed to:
1. Absorb high-frequency event bursts without immediate DB writes
2. Enable lazy embedding computation in background thread
3. Provide fast access to very recent events (< 30 min)

### Flush Strategy

```python
async def flush_warm_buffer():
    """Batch write warm buffer to L3 PostgreSQL"""
    if len(buffer) < FLUSH_THRESHOLD and not buffer.is_stale():
        return

    batch = buffer.drain(max_size=1000)

    # Ensure embeddings are computed before write
    for event in batch:
        if event.embedding is None:
            event.embedding = await compute_embedding(event.raw_text)

    async with db.transaction():
        await db.execute_many(INSERT_EVENTS, batch)

    # Promote high-salience to L1
    for event in batch:
        if event.max_salience > L1_PROMOTION_THRESHOLD:
            l1_cache.add(event)
```

---

## Original Design: Level 4 Cold Storage

From ADR-0004 Section 4.6:

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

### Cold Storage Migration

```python
async def migrate_to_cold():
    """Move old events from hot to cold storage"""
    cutoff = now() - timedelta(days=COLD_THRESHOLD_DAYS)

    # Select events to archive
    events = await db.fetch("""
        SELECT * FROM episodic_events
        WHERE timestamp < $1 AND NOT archived
    """, cutoff)

    # Summarize before archiving
    for batch in chunk(events, 100):
        summary = await summarize_events(batch)
        await db.execute("""
            INSERT INTO episodic_events_archive
            (time_range, summary, source_event_ids, embedding)
            VALUES ($1, $2, $3, $4)
        """, (batch.time_range, summary.text, batch.ids, summary.embedding))

        # Mark originals as archived (soft delete)
        await db.execute("""
            UPDATE episodic_events SET archived = true
            WHERE id = ANY($1)
        """, batch.ids)
```

---

## Memory Tier Interaction (Full Design)

Original full-tier interaction from ADR-0004:

```
Query Flow (retrieval):
┌───────────────────────────────────────────────────────────────────────────┐
│                                                                           │
│  1. Check L1 (Hot Cache) ─── Hit? ──→ Return immediately (<5ms)           │
│         │                                                                 │
│         │ Miss                                                            │
│         ▼                                                                 │
│  2. Check L2 (Warm Buffer) ── Hit? ──→ Promote to L1, return (<20ms)      │
│         │                                                                 │
│         │ Miss                                                            │
│         ▼                                                                 │
│  3. Query L3 (PostgreSQL Hot) ─ Hit? ──→ Promote to L1, return (~50ms)    │
│         │                                                                 │
│         │ Miss (historical query)                                         │
│         ▼                                                                 │
│  4. Query L4 (PostgreSQL Cold) ──→ Return (~200ms, no promotion)          │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘

Write Flow (ingestion):
┌───────────────────────────────────────────────────────────────────────────┐
│                                                                           │
│  1. Event received from sensor                                            │
│         │                                                                 │
│         ▼                                                                 │
│  2. Add to L2 (Warm Buffer) immediately (<1ms)                            │
│         │                                                                 │
│         │ Background thread                                               │
│         ▼                                                                 │
│  3. Compute embedding (10-50ms, async)                                    │
│         │                                                                 │
│         │ Timer/threshold trigger                                         │
│         ▼                                                                 │
│  4. Batch flush to L3 (PostgreSQL)                                        │
│         │                                                                 │
│         │ If high salience                                                │
│         ▼                                                                 │
│  5. Promote to L1 (Hot Cache)                                             │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## MVP Simplification

For MVP, the memory hierarchy is simplified to:

| Level | Name | Storage | MVP Status |
|-------|------|---------|------------|
| L0 | Context Window | LLM prompt | **Keep** - Essential |
| L1 | Hot Cache | In-memory | **Skip** - Premature |
| L2 | Warm Buffer | In-memory | **Skip** - Premature |
| L3 | Database Hot | PostgreSQL | **Keep** - Primary store |
| L4 | Database Cold | PostgreSQL | **Defer** - Add when retention policy active |

### MVP Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│  MVP MEMORY ARCHITECTURE                                                  │
│                                                                           │
│  Event ──→ PostgreSQL (L3) directly                                       │
│              │                                                            │
│              │ Query                                                      │
│              ▼                                                            │
│        Retrieved events ──→ L0 (Context Window) ──→ LLM                   │
│                                                                           │
│  No L1 cache, no L2 buffer, no L4 archival initially                      │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## When to Restore This Design

Add L1/L2 caching if ANY of these occur:

1. **Latency exceeds budget**: PostgreSQL queries consistently >50ms under typical load
2. **Write amplification**: High event rate causes write contention
3. **Embedding bottleneck**: Synchronous embedding generation blocks event processing

**Measurement approach**:
- Monitor p95 query latency via Prometheus (ADR-0006)
- Track events/second throughput
- Measure embedding computation time

**Expected trigger**: ~1000+ events/minute sustained

---

## Related Files

- [ADR-0004](../adr/ADR-0004-Memory-Schema-Details.md) - Original source (still contains full design)
- [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) - Review that identified this as deferrable
- [USE_CASES.md](USE_CASES.md) - Use cases that validated MVP scope
