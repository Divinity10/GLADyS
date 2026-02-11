# Phase 5: Episodic Memory

**Status**: Planned
**Predecessor**: [Phase 4](phase4.md)

### Question to answer

Can GLADyS reason about temporal context - segmenting events into meaningful episodes, retrieving relevant past experiences, and using historical context to inform current responses?

### Success Criteria

| # | Claim | Success criteria |
|---|-------|-----------------|
| 1 | Event segmentation works | System identifies episode boundaries (e.g., "game session", "work meeting"); events cluster into coherent chunks. |
| 2 | Temporal retrieval is relevant | Given current event, system retrieves past episodes with similar context; not just keyword match. |
| 3 | Context improves responses | Responses using episodic context are measurably more accurate/helpful than without (A/B test or skill rating). |
| 4 | Storage scales | Weeks/months of event history stored and queryable; retrieval latency <1s p95. |
| 5 | Privacy is preserved | Episodic data stays local; user can inspect/delete episodes; no cross-domain leakage. |

### Abort Signals

- **Segmentation is arbitrary**: Cannot identify meaningful episode boundaries; all attempts feel like random chunking.
- **Retrieval is noise**: Past episodes retrieved are irrelevant; adding context degrades response quality.
- **Storage costs explode**: Episodic data grows faster than disk/memory can handle; no viable compression or pruning strategy.
- **Temporal reasoning intractable**: LLM or heuristic system cannot effectively use past context; added complexity provides no benefit.

### Dependencies

- Phase 1-4 event and response pipelines must be stable
- Requires robust event storage and indexing (Phase 2+)
- Need timeline/segmentation algorithms
- Likely depends on embedding-based retrieval infrastructure from learning system
- Privacy and data retention policies must be defined

---

**Note**: This enables Phase 6 (advanced learning can use episodic patterns for consolidation). Workstreams defined during planning.
