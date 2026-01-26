# Plan: Closing the Learning Loop

**Last Updated**: 2026-01-26

**Context**: We have successfully built the "Forward Pass" of the brain (Event -> Salience -> Routing -> Action). We have also proven the "Killer Feature" (Novel Event -> LLM -> New Heuristic).

**Problem**: The "Backward Pass" (Feedback -> Learning) is currently manual AND unreliable. The explicit feedback path (user thumbs up/down) doesn't consistently update heuristic confidence.

**Goal**: Prove GLADyS can learn and adapt, first reliably with explicit feedback, then autonomously with implicit observation.

---

## Parallel Execution Plan

| Phase | Task | Owner | Environment | Status |
|-------|------|-------|-------------|--------|
| 0 | Fix Explicit Feedback | Claude | Local (50050-50053) | ✅ Complete |
| 1 | Generalization Test | Gemini | Docker (50060-50063) | 🔴 Not Started |
| 2 | Implicit Feedback | Claude | Local | ✅ Complete |
| 3 | Feedback Persistence | Gemini | Docker | 🟢 Unblocked |

### Coordination

- **Work Log**: [LEARNING_WORK_LOG.md](LEARNING_WORK_LOG.md) - Both assistants update this file
- **Environment Separation**: Docker (Gemini) and Local (Claude) run on different ports
- **Code Sync**: Both work from the same Git branch; coordinate commits via work log

### Environment Ports

| Service | Local (Claude) | Docker (Gemini) |
|---------|----------------|-----------------|
| Orchestrator | 50050 | 50060 |
| Memory Python | 50051 | 50061 |
| Memory Rust | 50052 | 50062 |
| Executive Stub | 50053 | 50063 |
| PostgreSQL | 5432 | 5433 |

---

## Phase 0: Fix Explicit Feedback (PREREQUISITE)

**Owner**: Claude | **Environment**: Local | **Status**: ✅ Complete (2026-01-26)

**Problem**: `test_scenario_5_learning_loop.py` fails intermittently. The full loop (Event → LLM → Heuristic → Feedback → Confidence Update) doesn't work reliably.

**Why First**: Building implicit feedback on unreliable explicit feedback is building on a shaky foundation. If we can't reliably update confidence from a direct "thumbs up" API call, adding an automated "outcome watcher" will just multiply the unreliability.

### Tasks
1. **Diagnose the failure mode**:
   - Run `test_scenario_5_learning_loop.py` multiple times
   - Identify: Is the heuristic not being created? Not matched? Feedback not applied?
   - Check TD learning update logic in Memory subsystem
2. **Fix the root cause**:
   - Ensure heuristic creation returns valid ID
   - Ensure semantic matching finds the heuristic (0.7 cosine threshold)
   - Ensure feedback API updates confidence correctly
3. **Verify**:
   - Test passes 10/10 times (not 7/10)
   - Add assertions for intermediate states if needed

### Success Criteria
- `test_scenario_5_learning_loop.py` passes reliably
- Confidence increases measurably after positive feedback
- The test can be used as a regression guard for future work

### Handoff
When complete, update [LEARNING_WORK_LOG.md](LEARNING_WORK_LOG.md) with:
- What was broken
- How it was fixed
- Any changes that affect Docker environment

---

## Phase 1: Heuristic Generalization Verification

**Owner**: Gemini | **Environment**: Docker | **Status**: 🔴 Not Started

**Concept**: Proof that "One-Shot Learning" works immediately via the semantic path.

**Why Parallel**: This tests semantic matching, which is independent of the feedback→confidence path that Phase 0 fixes.

### Tasks
1. **Create Integration Test**: `test_generalization.py` in `src/integration/`
2. **Flow**:
   - Teach: "When the house is burning, call 911."
   - Trigger: "Smoke alarms are detecting fire."
   - Assert: Fast Path triggers "Call 911" action.
3. **Success Criteria**: The system generalizes "house burning" to "smoke alarms" instantly without re-training.

### Why This Can Run In Parallel
- Tests semantic heuristic matching (cosine similarity)
- Does NOT depend on feedback→confidence updates
- Uses different code path than Phase 0

### Prompt
See [../prompts/GEMINI_PHASE1_GENERALIZATION.md](../prompts/GEMINI_PHASE1_GENERALIZATION.md)

---

## Phase 2: Implicit Feedback (The "Outcome Evaluator")

**Owner**: Claude | **Environment**: Local | **Status**: ✅ Complete (2026-01-26)

**Concept**: A system that watches the event stream for "consequences" of actions. If GLADyS takes an action and the environment reaches a desired state shortly after, that is positive reinforcement.

**Why After Phase 0**: Uses the same feedback API that Phase 0 fixes.

### Tasks
1. **Define Success Signals**:
   - Create a simple lookup or configuration: `Heuristic ID -> Expected Outcome Event`
   - Example: Rule "Oven Alert" expects "Oven Turned Off" within 2 minutes
2. **Implement Outcome Watcher**:
   - A background process (in Orchestrator or Executive) that tracks pending expectations
   - If the expected event arrives, trigger a **Positive Feedback** call automatically
3. **Demonstrate**:
   - Trigger "Oven Alert"
   - Send "Oven Turned Off" event 30 seconds later
   - Verify the "Oven Alert" heuristic confidence *increases*

### Design Considerations
- Where does the outcome mapping live? (Config file? Database? Heuristic metadata?)
- How long to wait before marking "unknown" outcome?
- Should failed outcomes decrease confidence or just not increase it?

---

## Phase 3: Feedback Persistence (The "Flight Recorder")

**Owner**: Gemini | **Environment**: Docker | **Status**: 🟢 Unblocked

**Concept**: Track *when* a heuristic fired and *what happened*. Currently we update `fire_count` and `confidence` but lose the history.

**Why After Phase 0**: The schema should capture both explicit and implicit feedback, so we need to know how feedback works first.

### Tasks
1. **Implement `heuristic_fires` Table**:
   - Create migration `009_heuristic_fires.sql`
   - Columns: `id`, `heuristic_id`, `event_id`, `fired_at`, `outcome` (success/fail/unknown), `feedback_source` (explicit/implicit)
2. **Instrument the Orchestrator**:
   - When a heuristic fires (Fast Path), write to this table
3. **Link Feedback**:
   - When feedback (implicit or explicit) arrives, update the corresponding `heuristic_fires` row with the outcome

### Future Value
- Offline analysis ("Tuning Mode")
- Concept drift detection (rules that stopped working)
- Debugging why confidence changed

### Prompt
See [../prompts/GEMINI_PHASE3_PERSISTENCE.md](../prompts/GEMINI_PHASE3_PERSISTENCE.md)

---

## Strategic Summary

| Phase | Item | Type | Risk | Value | Parallel? |
|-------|------|------|------|-------|-----------|
| 0 | Fix Explicit Feedback | Bug fix | Low | Foundation | No (prerequisite) |
| 1 | Generalization Test | Proof | Low | Demo/Validation | Yes (with Phase 0) |
| 2 | Implicit Feedback | New capability | Medium | Differentiator | After Phase 0 |
| 3 | Feedback Persistence | Infrastructure | Low | Observability | After Phase 0 |

**Key Insight**: Phases 0 and 1 can run in parallel because they test different code paths. Phases 2 and 3 depend on Phase 0 completing.
