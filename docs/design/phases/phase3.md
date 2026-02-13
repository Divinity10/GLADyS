# Phase 3: Domain Skills

**Status**: Planned
**Predecessor**: [Phase 2](phase2.md)

## Question to answer

Can we define and load domain-specific skill interfaces that provide context-aware success evaluation, action boundaries, and behavioral guidance?

### Success Criteria

| # | Claim | Success criteria |
|---|-------|-----------------|
| 1 | Skill interface is viable | At least 2 domain skills implemented (e.g., Sudoku, Melvor); both define success criteria and load successfully. |
| 2 | Success evaluation works | Domain skill receives event + response, returns success/failure judgment; judgment feeds into learning system. |
| 3 | Skills are domain-scoped | Sudoku skill never evaluates Melvor events; no cross-domain pollution. |
| 4 | Plugin architecture scales | Can add new skill without modifying core system; skill discovery and loading is automated. |
| 5 | Skills define action boundaries | Each skill specifies safe/unsafe actions (preparation for Phase 8 actuators). |

### Abort Signals

- **Interface too rigid**: Real domain needs don't fit the skill abstraction; constant special-casing required.
- **Success definition intractable**: Cannot objectively determine if a response was correct (e.g., subjective preferences dominate).
- **Skills too coupled**: Adding a skill requires changes to orchestrator, memory, or executive; plugin isolation fails.
- **No viable plugin model**: Cannot find a plugin architecture that works across Python, Rust, and C# services.

### Dependencies

- Phase 2 multi-sensor architecture must be stable
- Need clear understanding of what "success" means per domain (from Phase 1/2 learnings)
- May require prototyping skill interfaces during Phase 2

---

**Note**: This is foundational for Phases 4, 6, 8, and 9. Workstreams defined during planning.
