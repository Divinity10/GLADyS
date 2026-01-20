# ADR-0009: Memory Contracts and Compaction Policy

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Date** | 2026-01-09 |
| **Owner** | Mike Mulcahy (Divinity10), Scott (scottcm) |
| **Contributors** | |
| **Module** | Memory |
| **Tags** | memory, contracts, compaction, provenance |
| **Depends On** | ADR-0001, ADR-0004, ADR-0005, ADR-0008 |

---

## 1. Context and Problem Statement

The memory system is central to GLADyS, but multiple modules depend on it
(sensors, salience, executive). To avoid drift and rework, we need a stable
contract for how episodic data is ingested and queried. We also want to
formalize progressive compaction so older memories become increasingly
compressed while retaining provenance.

---

## 2. Decision Drivers

- Stable, minimal contracts across modules
- Progressive memory compression to control long-term storage growth
- Local-first privacy with traceability for user review
- Query performance for both recent context and long-term recall

---

## 3. Decision

Define memory contracts and a configurable compaction policy with sane
defaults. These contracts are logical API shapes; transport details live in
ADR-0005.

### 3.1 Episodic Event Envelope (Ingest Contract)

Required fields (minimum viable):
- `timestamp` (UTC)
- `source` (sensor/app identifier)
- `raw` (free text)
- `salience` (object with salience dimensions)

Optional fields:
- `episode_id` (UUID) - sensors typically don't know episode context; assigned by
  Memory subsystem during ingest based on active episode, or by Episode Boundary
  Detector when context switches are detected. See ADR-0004 Section 5.8.
- `structured` (domain-specific JSON)
- `embedding` (vector)
- `tokens` (pre-tokenized payload)
- `entities` (entity references)
- `trace_id` (for observability)

### 3.2 Memory API (Logical Operations)

Episodic:
- `IngestEpisodes(batch)` -> ack + failures
- `QueryEpisodes(filter)` -> list of episodes
- `GetEpisode(episode_id)` -> episode + provenance

Semantic:
- `QueryFacts(filter)` -> list of semantic facts
- `UpsertFact(fact)` -> ack + confidence update

Entities:
- `UpsertEntity(entity)` -> ack + merged entity_id
- `GetEntity(entity_id)` -> entity record

Profile:
- `GetUserProfile()` -> profile traits + confidence

Filters support:
- time range, source, salience thresholds
- text query and/or embedding query
- limit, sort order, include_archived

### 3.3 Compaction Policy (Configurable)

Compaction uses time tiers with optional salience exemptions. Defaults are
illustrative and must be configurable.

Policy shape (example):
```
compaction_policy:
  hot_window_days: 7
  warm_window_days: 90
  cold_window_days: 365
  keep_raw_in_warm: true
  keep_raw_in_cold: false
  salience_exempt_threshold: 0.85
  audit_retention_days: 0
```

Tier semantics:
- Hot: full raw episodes, structured fields, embeddings.
- Warm: keep key fields + summaries + extracted entities/facts; optionally
  drop raw payloads.
- Cold: keep summaries + semantic facts + minimal provenance only.

### 3.4 Compaction Outputs and Provenance

Compaction produces summarized records with back-references:
- `summary_id`, `episode_ids`, `time_range`, `topic`, `salience_aggregate`,
  `embedding`

Provenance is preserved by retaining minimal episode metadata (timestamp,
source, hash) and links from facts/summaries to source episodes.

---

## 4. Consequences

### Positive
- Stable contracts for all modules integrating with memory
- Configurable retention and compression without code changes
- Clear provenance for user transparency and debugging

### Negative
- Upfront design effort before implementation
- Requires policy and pipeline configuration early

### Risks
- Overly aggressive compaction could reduce explainability if defaults are poor

---

## 5. Related Decisions

- ADR-0001: GLADyS Architecture
- ADR-0004: Memory Schema Details
- ADR-0005: gRPC Service Contracts
- ADR-0008: Security and Privacy
