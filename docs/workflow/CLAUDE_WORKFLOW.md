# Claude Workflow Conventions

Agent workflow conventions for Claude sessions on GLADyS. Read this file when working on multi-step tasks, agent coordination, or document maintenance.

Referenced from `CLAUDE.md`. For Gemini-specific guidance, see `AGENT_COORDINATION.md` (same directory).

---

## Mode Prefixes

The user may prefix messages with `!think`, `!plan`, `!do`, or `!review` to signal what kind of work they want. A hook (`.claude/hooks/mode_prefix.py`) injects mode-specific instructions automatically.

| Prefix | Meaning |
|--------|---------|
| `!think` | Critical analysis only. No code. Explore tradeoffs, identify gaps. |
| `!plan` | Design the approach. Break into steps. Get approval before implementing. |
| `!do` | Execute. The user has decided. Implement efficiently. |
| `!review` | Evaluate existing code/design. Be thorough, cite specifics. |
| `!archive` | Archive memory file, carry forward active work, start fresh. |
| (none) | Consider whether this needs discussion before implementation. |

---

## Working Memory (Effort-Scoped)

All gitignored. Agents read `efforts/working_memory.md` first, then the relevant effort file.

### Index: `efforts/working_memory.md`

Lean index (~40-50 lines max). Every agent reads this at session start.

```
## Session Info          — Team context, standing notes
## Efforts               — Table: effort name → file, status, one-line summary
## Active Assignments    — Table: agent → effort, task, status
## Cross-Effort Decisions — Stable decisions that span multiple efforts (few)
```

### Effort directories: `efforts/<name>/`

One directory per effort (e.g., `efforts/poc2/`). Contains all effort-scoped artifacts.

```
efforts/poc2/
├── state.md        — Working state (read by agents on this effort)
├── tasks.md        — Task list with phases and dependencies
└── prompts/        — Implementation prompts for this effort's tasks
```

Completed efforts can be a single file (e.g., `efforts/poc1-closed-loop.md`).

**Active state.md structure** (verbose during work):
```
## Work Stack       — Tasks for this effort (stack, not queue)
## Known Issues     — Bugs blocking this effort
## Decisions        — Effort-specific decisions (pointers to design docs)
## Discoveries      — Things that contradicted assumptions
## Open Questions   — Unresolved items
## Handoff          — Agent coordination (Claude/Gemini status)
```

**Completed effort structure** (compressed to ~15 lines):
```
## Outcome          — What was proven/built
## Key Lessons      — Things that affect future efforts
## Decisions Made   — Pointers to design docs
```

### Rules

- **Index stays lean** — effort detail goes in the effort file, not the index
- **Decisions are pointers, not records** — full rationale in design docs
- **Update after each decision or task transition** — don't wait until end of session
- **Stack, not queue** — within effort files, most recent task on top

### Multi-Agent Coordination

See `AGENT_COORDINATION.md` for full coordination protocol, trust boundaries, and prompt engineering patterns.

The Handoff section in each effort file is the coordination point:
- Each agent edits only their section (Architect or Investigator)
- Status: `idle` | `assigned` | `working` | `blocked`
- Write findings with specific file paths and line numbers

### Archiving

Use `!archive <description>` to archive. This runs `.claude/hooks/archive_memory.py` which:
1. Moves current index to `docs/archive/claude-memory-YYYYMMDD-<description>.md`
2. Creates fresh index with the standard template
3. Completed effort files stay in `efforts/` (already compressed)

---

## Document Lifecycle

**Design questions** (`docs/design/questions/`):
1. Questions start as "Open" entries in category files
2. When resolved, the decision migrates to the relevant design doc (`docs/design/`)
3. The question entry updates to "Resolved — see {design_doc}"
4. At milestone boundaries: review questions/ files for resolved items that haven't migrated

**INDEX.md**: Updated at **milestone boundaries**, not per-task. After creating or relocating a design doc, add it to INDEX.md.

**CONCEPT_MAP.md**: Update when adding new services or brain-inspired concepts. For cross-service dependencies, run `codebase-info rpcs`. For topology changes, update `docs/codebase/SERVICE_TOPOLOGY.md`.

---

## Milestone Cleanup

When closing a milestone:
1. Archive working_memory.md (`!archive <description>`)
2. Verify INDEX.md reflects all docs created during the milestone
3. Review `docs/design/questions/` for resolved items to migrate to design docs
4. Update CONCEPT_MAP.md if new concepts added; update SERVICE_TOPOLOGY.md if topology changed
