# Cross-AI Coordination Protocol

**Purpose**: Define how Claude and Gemini coordinate parallel work on GLADyS.

**Last updated**: 2026-01-26

---

## Active Work Assignment

| Bug | Files | Assigned To | Status |
|-----|-------|-------------|--------|
| 1. Race condition | `outcome_watcher.py` | **Claude** | Not started |
| 2. feedback_source propagation | `memory.proto`, `grpc_server.py`, `storage.py` | **Claude** | Not started |
| 3. Fire-and-forget error handling | `router.py` | **Gemini** | Not started |
| 4. gRPC channel leaks | `dashboard.py` | **Gemini** | Not started |

---

## Communication Protocol

### Message Format

When posting questions or updates, use this format:

```markdown
## [QUESTION|UPDATE|BLOCKER|DONE] from [Claude|Gemini]

**Topic**: Brief description
**Date**: YYYY-MM-DD HH:MM

**Details**:
[Your message here]

**Action needed**: [None / Response requested / Review requested]
```

### Where to Post

| Type | Location |
|------|----------|
| Questions for the other AI | `docs/coordination/MESSAGES.md` |
| Task progress updates | Your own memory file (`claude_memory.md` or `gemini_memory.md`) |
| Blockers requiring human input | `docs/coordination/MESSAGES.md` + notify Scott |
| Completion announcements | `docs/coordination/MESSAGES.md` |

### Monitoring for Messages

- **Claude**: Check `docs/coordination/MESSAGES.md` at the start of each session and before declaring a task complete
- **Gemini**: Check `docs/coordination/MESSAGES.md` at the start of each session and before declaring a task complete
- **Response time**: Respond within the same work session when possible

---

## File Ownership During Parallel Work

**CRITICAL**: Do not edit files assigned to the other AI without coordination.

| AI | Owns (can edit freely) | Must coordinate |
|----|------------------------|-----------------|
| **Claude** | `outcome_watcher.py`, `memory.proto`, `grpc_server.py`, `storage.py` | `router.py`, `dashboard.py` |
| **Gemini** | `router.py`, `dashboard.py` | `outcome_watcher.py`, `memory.proto`, `grpc_server.py`, `storage.py` |

If you need to touch a file owned by the other AI:
1. Post a message in `MESSAGES.md` explaining what you need
2. Wait for acknowledgment before proceeding
3. Or ask Scott to coordinate

---

## Shared Resources (Read-Only During Parallel Work)

These files are for reading context only - do not edit during parallel work:
- `CODEBASE_MAP.md`
- `docs/design/REFACTORING_PLAN.md`
- `docs/design/questions/*.md`

If an update is needed, post in `MESSAGES.md` and wait for Scott to coordinate.

---

## Completion Criteria

A task is **done** when:
1. Code changes are complete
2. Existing tests pass (if applicable)
3. New tests added (if applicable)
4. `MESSAGES.md` updated with completion notice
5. Memory file updated with what was done

---

## Escalation

If you're blocked for any reason:
1. Document the blocker in `MESSAGES.md`
2. Mark status as BLOCKER in your memory file
3. Continue with other work if possible
4. Scott will review and unblock

---

## Current Session Notes

**Session started**: 2026-01-26
**Human coordinator**: Scott

### Work sequence
1. Both AIs read their task files and this coordination doc
2. Work in parallel on assigned files
3. Post completion notices to `MESSAGES.md`
4. Scott reviews and merges if needed

### Known dependencies
- None between Claude and Gemini's tasks (files don't overlap)
- Both need proto regeneration after Claude's proto changes
