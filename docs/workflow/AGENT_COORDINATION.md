# Agent Coordination

Guidance for working with AI implementation agents (currently Gemini) on GLADyS tasks.

For the **coordinating agent** (Claude) and the **human coordinator** (Scott). Captures patterns proven across 5 evaluated implementation tasks (T3-T7, Feb 2026).

Full evaluation data: `gemini_eval.md` (Claude auto-memory). Shareable summary: `docs/reviews/gemini-evaluation-summary.md`.

---

## 1. Gemini Operating Profile

### 1.1 Strengths

1. **Reliable spec-driven implementation** -- 92.5% of scored dimensions at "meets expectations" or above
2. **Both Python and Rust** -- correct async_trait, ownership, lock discipline
3. **Clean fix cycles** -- processes review feedback well, single-pass fixes
4. **Well-targeted clarifying questions** -- "ask first" questions hit real ambiguities

### 1.2 Trust Boundaries

| Area | Trust Level | Action |
|------|-------------|--------|
| Code quality | Trustworthy | Review but expect clean code |
| Test coverage | Trustworthy | With named tests in DoD |
| Self-reported status | **NOT trustworthy** | Must be externally verified |
| Cross-service impacts | **NOT detected** | Must be listed in prompt |

### 1.3 Weaknesses (Gemini's Own Terminology)

1. **"Local blinders"** -- solves the problem within scoped files but misses side effects in adjacent services. Especially proto changes.
2. **"State-machine mismatch"** -- visualizes the successful end-state and may describe that visualization rather than checking actual tool output. Causes hallucinated completion claims.
3. **Behavioral regressions** -- correctly extracts interfaces but may subtly change runtime behavior (cache warming, error fallback paths).

---

## 2. Prompt Engineering

### 2.1 What Works (Proven)

**Named tests in DoD** -- "verified by: `test_explicit_positive`" eliminates test coverage gaps. Every DoD checkbox should name its test. (Proven T4-T7)

**Behavioral Invariants section** -- for refactoring/extraction tasks, list runtime behaviors that MUST NOT change. In prompts, use the heading **"Invariants to Preserve"** (Gemini's preferred framing). (Proven T6b)

```markdown
## Invariants to Preserve
These runtime behaviors must be preserved exactly:
1. When embedding lookup fails, fall back to storage-only matching (do NOT error)
2. Storage matches must be added to the cache for warming
3. Empty candidates list returns SalienceResult::default(), not an error
```

**Impact Analysis section** -- for cross-service tasks, list every service consuming the changed contract. In prompts, frame as a **"Blast Radius Checklist"** (Gemini's term). (Addresses T7 blind spot)

```markdown
## Blast Radius Checklist
Proto `memory.proto` changes affect these consumers:
- Orchestrator: `src/services/orchestrator/gladys_orchestrator/server.py` (calls UpdateHeuristicConfidence)
- Executive: `src/services/executive/gladys_executive/server.py` (passes learning_rate -- verify removal)
- Salience (Rust): `src/services/salience/src/client.rs` (memory client -- verify no stale field refs)

**Before committing**: Grep the full codebase for every proto field you modify or remove.
```

**"Ask first" methodology** -- "Read the prompt and ask clarifying questions, then STOP." Costs one round-trip but consistently produces well-targeted questions. (Proven T6-T7)

### 2.2 What Doesn't Work

1. **Process checklists** -- "Commit your changes" has 60% success rate. Failures include fabrication (claimed commit with invented hash), not just omission.
2. **Self-reported completion** -- "Update handoff section" is claimed done when it isn't. Attention on process steps degrades as implementation complexity increases.

### 2.3 Forcing Functions (Replace Checklists)

Replace self-assessed process steps with observable proof. Gemini frames this as **"Trust but Verify"** -- requiring verifiable output rather than self-assessment.

| Instead of | Use |
|-----------|-----|
| "Commit your changes" | "Paste your `git log --oneline -1` output" |
| "Update handoff" | "Paste the Handoff section you wrote" |
| "All tests pass" | "Paste `pytest` output showing N tests passed" |
| "Proto stubs regenerated" | "Paste output of proto generation command" |

### 2.4 Terminology Mapping

When writing prompt sections that Gemini reads, use its terminology for better recognition:

| Our term | Gemini's term | Use in prompts |
|----------|--------------|----------------|
| Behavioral Invariants | "Invariants to Preserve" | Section heading in prompts |
| Impact Analysis | "Blast Radius Checklist" | Section heading in prompts |
| Forcing functions | "Trust but Verify" | Completion section framing |
| Cross-service blind spot | "Local blinders" | Internal analysis only |
| Hallucinated completion | "State-machine mismatch" | Internal analysis only |

---

## 3. Prompt Structure

Use `docs/prompts/TEMPLATE.md` as the base.

### 3.1 Required for All Tasks

- **Read order** -- files to read before implementing
- **Task** -- 1-2 sentences
- **What to Implement** -- numbered steps
- **Files to Change** -- explicit scope
- **Definition of Done** -- named tests for every behavioral checkbox
- **Pre-Flight Checklist** -- scope, deps, conventions
- **Completion** -- with forcing functions, NOT self-assessed checklists

### 3.2 Required for Refactoring Tasks (Add to Template)

- **Invariants to Preserve** -- list runtime behaviors that must NOT change

### 3.3 Required for Cross-Service Tasks (Add to Template)

- **Blast Radius Checklist** -- list affected services and files
- **CODEBASE_MAP.md reference** -- "consult CODEBASE_MAP.md Proto Services section for all consumers"

### 3.4 Optional

- **"Ask first" instruction** -- for complex or ambiguous tasks: "Read the prompt and ask clarifying questions, then STOP. After I answer, proceed."
- **Constraints** -- backward compat, scope limits

---

## 4. Task Types

### 4.1 Single-Service Implementation

Gemini's strongest operating envelope. Simplest prompts.

- Standard TEMPLATE.md
- Named tests in DoD
- Example: T5 Router Config Extraction

### 4.2 Single-Service Refactoring

Extraction or restructuring within one service.

- Add **Invariants to Preserve** section
- Be explicit about what must NOT change
- Example: T3 LLM Provider, T4 Decision Strategy, T6 Salience Scorer

### 4.3 Cross-Service Changes

Most complex. Gemini's weakest area due to "local blinders."

- Add **Blast Radius Checklist** listing all affected services
- Add "grep codebase for modified symbols" instruction
- Reference CODEBASE_MAP.md for service topology
- Consider splitting into per-service sub-tasks if feasible
- Example: T7 Learning Strategy

---

## 5. Coordination Protocol

### 5.1 Working Memory

- `efforts/working_memory.md` is the index; each effort has its own `state.md`
- Handoff section lives in the effort's `state.md` — each agent edits only their section
- Status values: `idle` | `assigned` | `working` | `blocked`

### 5.2 Task Lifecycle

1. Architect (Claude) creates prompt in `docs/prompts/`
2. Scott assigns to Gemini with the prompt file path
3. Gemini asks questions (if "ask first" used)
4. Claude/Scott answers
5. Gemini implements
6. Claude reviews (separate session, `!review` mode)
7. Fix cycle if needed (targeted fix prompt with Invariants to Preserve)

### 5.3 Post-Completion Verification

**Always verify externally. Do not trust self-reported status.**

1. `git log --oneline -3` -- did the commit actually happen?
2. Read the effort's `state.md` Handoff section -- was it actually updated?
3. Run tests -- do they actually pass?
4. For cross-service tasks: grep for modified symbols across all services

---

## 6. Document Maintenance

### 6.1 Design Questions Lifecycle

1. Questions start as "Open" entries in `docs/design/questions/{category}.md`
2. When resolved, the decision migrates to the relevant design doc (`docs/design/`)
3. The question entry updates to "Resolved -- see {design_doc}.md"
4. At milestone boundaries: review questions/ files for resolved items that haven't migrated

### 6.2 INDEX.md Maintenance

- Updated at **milestone boundaries**, not per-task
- After creating or relocating a design doc, add it to INDEX.md
- Periodic validation: run `docsearch --validate` to find orphan docs and dead links (when available)

### 6.3 CODEBASE_MAP.md Maintenance

- Verify when touching cross-service code or proto definitions
- Update when service topology, proto methods, or database schema changes
- Proto Services section serves as the cross-service dependency map for Gemini prompts

### 6.4 Milestone Cleanup

When closing a milestone:

1. Archive efforts/working_memory.md (`!archive <description>`)
2. Verify INDEX.md reflects all docs created during the milestone
3. Review `docs/design/questions/` for resolved items to migrate
4. Update CODEBASE_MAP.md if service topology changed
5. Prune MEMORY.md (Claude auto-memory) if approaching 200-line limit
