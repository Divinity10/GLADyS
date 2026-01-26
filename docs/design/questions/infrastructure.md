# Infrastructure Questions

Deployment models, latency profiles, operational concerns, and maintenance.

**Last updated**: 2026-01-25

---

## Open Questions

### Q: Deployment Model and Resource Constraints (§15)

**Status**: Gap - needs design
**Priority**: High (affects architecture decisions)
**Created**: 2026-01-20

#### Problem

ADR-0001 states "local-first" but this doesn't address:
- What if user doesn't have a gaming rig?
- What combinations of local/network/cloud are supported?
- Where can the database live?
- What are minimum hardware requirements?

#### Deployment Spectrum

| Configuration | Example | Implications |
|---------------|---------|--------------|
| **Fully local** | Gaming rig | Ideal. All processing on single machine. |
| **Local network** | Home server + client | Database/LLM on server, sensors on client. 1-5ms network latency. |
| **Remote cloud** | Cloud LLM API | Privacy concerns. 50-200ms network latency. Data residency questions. |

#### Open Questions

1. **Minimum specs**: What hardware is required to run GLADyS at all?
2. **Database locality**: Can PostgreSQL be remote (local network or cloud)?
3. **LLM locality**: Local-only? Cloud fallback? User choice?
4. **Hybrid configurations**: Which components can be split across machines?
5. **Privacy vs performance trade-off**: When is remote acceptable? How does user control this?

#### Relationship to ADRs

- **ADR-0001**: Says "local-first" but doesn't define deployment configurations
- **ADR-0008**: Security model assumes local processing but doesn't address network boundaries
- **ADR-0004**: Memory design assumes local database (50ms query target)

#### What This Is NOT About

This is NOT about:
- Fine-tuning LLMs (learning happens in preference layer per ADR-0010, not model weights)
- Needing "model control" for self-learning (ADR-0010 uses EWMA + Bayesian, not LLM training)

The LLM is a black box. The question is: where does that black box live?

---

### Q: Gemini Code Review Action Items (§26)

**Status**: Tracked
**Priority**: Medium
**Created**: 2026-01-24

#### Context

Gemini performed a comprehensive 9-chunk code review. After assessment, most concerns were either misunderstandings (conflating ADR vision with PoC scope), already resolved, or future work.

#### Action Items (Worth Doing)

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| gRPC error handling: Use proper status codes | High | Low | Done |
| Document Executive stub as C# reference | Medium | Low | TODO |
| Consider `websearch_to_tsquery` for search | Low | Medium | TODO |

##### 26.1 gRPC Error Handling (Done)

**Issue**: The gRPC server returned 200 OK with error in response payload. This breaks retry logic.

**Fix**: Changed to proper gRPC status codes:
```python
await context.abort(grpc.StatusCode.INTERNAL, str(e))  # Proper gRPC error
```

##### 26.2 Document Executive Stub as Reference (TODO)

**Issue**: The Executive stub (`stub_server.py`) contains production-quality logic for TD learning and pattern extraction. This should be formally documented as the reference implementation for the eventual C# Executive.

**Action**: Add a design doc noting:
- `PATTERN_EXTRACTION_PROMPT` is the canonical format
- TD learning formula is authoritative
- `_store_trace` / `_cleanup_old_traces` patterns should be ported

##### 26.3 PostgreSQL Text Search Improvement (TODO)

**Issue**: Current search uses manual regex. PostgreSQL's `websearch_to_tsquery` provides better tokenization.

**Current**:
```python
ILIKE '%fire%warning%'  # Fragile
```

**Better**:
```sql
WHERE to_tsvector('english', condition_text) @@ websearch_to_tsquery('fire warning')
```

**Priority**: Low - current search is working for PoC.

#### Resolved/Non-Issues

| Item | Assessment |
|------|------------|
| ADR trait scale mismatch | Already fixed - ADR-0003 §7.1 correctly uses -1 to +1 |
| Episode ID nullability | No issue - Both ADRs agree it's optional |
| Skill Registry blocking | Disagree - Learning is higher priority for PoC |
| Over-engineering concerns | Disagree - ADRs describe vision; PoC implements subset |

---

## Resolved

### R: Latency Profiles (§4, §11)

**Decision**: Profile-based latency budgets
**Date**: 2026-01-XX

#### Problem Addressed

ADR-0005 defined a fixed 1000ms conversational budget. But latency requirements are **context/domain-driven**:
- PvP gaming: <500ms end-to-end
- Thermostat: Can be slow (and SHOULD be slow to avoid oscillation)
- Safety systems: Fast response
- Background learning: Async OK

#### Decision: Latency Profiles

| Profile | End-to-End | Preprocessor Chain | Use Cases |
|---------|------------|-------------------|-----------|
| `realtime` | <500ms | <100ms total | PvP gaming, safety alerts, threat detection |
| `conversational` | <1000ms | <200ms total | Voice interaction, general Q&A |
| `comfort` | <5000ms | <500ms total | Thermostat, lighting, non-urgent IoT |
| `background` | Best-effort | Async OK | Learning, batch analysis, reporting |

#### How It Flows (Pull Model)

**Key insight**: Latency requirements flow from ACTION → SENSOR (pull), not sensor → action.

1. **Sensors** are agnostic - reusable by any feature
2. **Features/Actions** declare their latency requirements
3. **Validation at startup**: System benchmarks the full chain
4. **Orchestrator** schedules based on profile priority

#### Override Hierarchy

```
System Default → Feature/Actuator Override → User Override
```

#### Graceful Degradation (Runtime Overload)

1. **Priority queuing**: `realtime` > `conversational` > `comfort` > `background`
2. **Background suspension**: `background` work pauses entirely under load
3. **Skip optional**: `enhances_with` stages can be dropped when pressed
4. **Single notification**: Warn user once on sustained overload
5. **Safety carve-out**: `realtime` safety events NEVER degraded

#### Remaining Work

- Security review: malicious plugins claiming `background`, bundle trust verification
- ADR-0005: Needs update to define profiles instead of single 1000ms budget
- ADR-0011: Actuator latency becomes profile-based
