# ADR-0012: Audit Logging

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Date** | 2026-01-18 |
| **Owner** | Mike Mulcahy (Divinity10), Scott (scottcm) |
| **Contributors** | |
| **Module** | Security |
| **Tags** | audit, logging, accountability, tamper-proof, compliance |
| **Depends On** | ADR-0001, ADR-0008, ADR-0009 |

---

## 1. Context and Problem Statement

GLADyS takes actions that affect the physical world (actuators) and handles sensitive data (observations). Users need:

- **Accountability**: What did GLADyS do and when?
- **Forensics**: If something goes wrong, trace what happened
- **Trust**: Users trust systems they can inspect

Audit logging is distinct from the brain's memory system:

| Aspect | Brain Memory | Audit Log |
|--------|--------------|-----------|
| Purpose | Context, learning | Accountability |
| Mutable | Yes (compaction) | No (append-only) |
| Retention | Configurable | Policy-driven, potentially forever |
| Who writes | Brain | System-wide |
| Who reads | Brain | Brain (read-only) + User |

---

## 2. Decision Drivers

1. **Tamper resistance**: Audit cannot be modified, even by the system
2. **Completeness**: All auditable events must be captured
3. **Queryability**: Users can search their audit history
4. **Privacy**: Audit data is sensitive; user controls access
5. **Storage**: Append-only grows forever; need management strategy
6. **Integration**: Brain can read audit for context but not modify

---

## 3. Decision

### 3.1 Event Type Taxonomy

Events use a hierarchical naming convention: `category.subject.action`

| Category | Description | Examples |
|----------|-------------|----------|
| `security` | Auth, permissions, breaches | `security.permission.granted`, `security.auth.failed` |
| `actuator` | Physical device commands | `actuator.thermostat.set`, `actuator.lock.unlock` |
| `config` | System configuration changes | `config.retention.updated`, `config.plugin.enabled` |
| `executive` | High-level decisions | `executive.decision.actuate`, `executive.decision.speak` |
| `sensor` | Observation events (if audited) | `sensor.temperature.threshold_crossed` |

The `source` field (plugin ID) is stored separately, not embedded in event type.

### 3.2 Tiered Storage Architecture

Three tables with different integrity mechanisms based on risk profile:

| Table | Integrity | Use Cases | Retention Default |
|-------|-----------|-----------|-------------------|
| `audit_security` | Merkle tree | Locks, permissions, auth, security breaches | Forever (-1) |
| `audit_actions` | Hash per record | Actuator commands, config changes | 365 days |
| `audit_observations` | Light/none | Sensor readings (if audited) | 30 days |

**Merkle tree rationale**: O(log n) verification of any record's integrity. Enables proving "this record existed at time T and hasn't been modified" without trusting the system.

### 3.3 Audit Record Schema

```sql
-- Common columns across all audit tables
event_type      VARCHAR(128) NOT NULL,  -- category.subject.action
source          VARCHAR(64)  NOT NULL,  -- plugin_id or system component
timestamp       TIMESTAMPTZ  NOT NULL,
details         JSONB,                   -- event-specific payload
outcome         VARCHAR(32),             -- success/failure/pending/denied
correlation_id  UUID,                    -- links related events

-- Integrity fields (vary by table)
record_hash     BYTEA,                   -- SHA-256 of record (actions, security)
merkle_root     BYTEA,                   -- current tree root (security only)
merkle_proof    BYTEA,                   -- proof path (security only)
```

### 3.4 Retention Policy

**Values**:

- `>0` = retain for N days, then archive/delete
- `-1` = retain forever (no automatic deletion)
- `0` = don't audit this event type

**Policy hierarchy** (lower overrides higher where allowed):

```
System Defaults → Org Policy (locked) → User Preferences
```

Org policies can lock minimum retention (users can extend, not shorten).

**Default retention** shipped with system:

| Event Category | Default | Rationale |
|----------------|---------|-----------|
| `security.*` | Forever (-1) | Legal/compliance, physical safety |
| `actuator.lock.*` | Forever (-1) | Physical security |
| `actuator.*` (other) | 365 days | Troubleshooting, patterns |
| `config.*` | 365 days | Change tracking |
| `executive.*` | 90 days | Decision analysis |
| `sensor.*` | 30 days | Usually low value |

### 3.5 Event Routing

Configuration determines which table receives each event type:

```yaml
audit_routing:
  security:  # → audit_security table (Merkle)
    - security.*
    - actuator.lock.*
    - actuator.garage.*
    - permission.*

  actions:   # → audit_actions table (hash per record)
    - actuator.*        # unless caught by security
    - config.*
    - executive.*

  observations:  # → audit_observations table (light)
    - sensor.*
    - observation.*
```

Plugins declare which event types they emit in their manifest (see ADR-0003).

### 3.6 Access Model

| Role | Permissions |
|------|-------------|
| Brain (Executive) | Read-only queries for context ("what did I do?") |
| User | Full query access, export, retention preferences |
| Admin | Org policy management, retention minimums |
| System | Append-only write, retention expiry execution |

**No one** can modify or delete records before retention expiry.

### 3.7 Query Interface

Audit queries are **separate** from memory queries:

- Different API endpoint
- Different query semantics (time-range + event-type focused)
- No embedding/vector search (audit is structured, not semantic)

Indexes optimized for:

- Time range queries (most common)
- Event type filtering
- Source (plugin) filtering
- Correlation ID lookups

### 3.8 Storage Management

**Tiered storage** (industry standard pattern):

- **Hot** (SSD): Recent data, fast queries (configurable window, default 30 days)
- **Warm** (HDD): Older data, slower queries
- **Cold** (archive): Compressed, rarely accessed, export-focused

Transitions are automatic based on age. Cold storage can be external (S3, etc.) for enterprise deployments.

---

## 4. Open Questions

*Resolved questions moved to Section 3.*

### Remaining

1. **Plugin manifest schema**: Exact format for declaring emitted event types (coordinate with ADR-0003 update)
2. **Export format**: JSON lines? Parquet? Both?
3. **Merkle tree implementation**: Build vs. buy? (e.g., merkle-tree crate)
4. **Cross-device sync**: If GLADyS runs on multiple devices, how sync audit?

---

## 5. Consequences

### Positive

1. **User trust**: Complete visibility into what GLADyS did and when
2. **Forensics**: When things go wrong, full audit trail available
3. **Compliance-ready**: Tiered integrity supports enterprise/regulated environments
4. **Learning separation**: Brain can learn patterns from audit without corrupting source of truth
5. **Flexible retention**: Per-event-type policies balance storage vs. compliance needs

### Negative

1. **Storage growth**: Append-only inevitably grows; requires tiered storage infrastructure
2. **Complexity**: Three tables with different integrity mechanisms adds implementation burden
3. **Performance overhead**: Merkle tree updates on every security event (O(log n), but still work)

### Risks

1. **Clock tampering**: Merkle trees don't protect against system clock manipulation; consider NTP validation or trusted timestamping for high-security deployments
2. **Key management**: If Merkle signing keys are compromised, integrity guarantees are void
3. **Privacy tension**: "Forever" retention conflicts with right-to-be-forgotten in some jurisdictions; may need jurisdiction-aware policies

---

## 6. Related Decisions

- ADR-0008: Security and Privacy (security principles)
- ADR-0009: Memory Contracts (distinct from brain memory)
- ADR-0010: Learning and Inference (can learn from audit)
- ADR-0011: Actuator Subsystem (commands are audited)
