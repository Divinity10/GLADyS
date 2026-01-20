# Architecture Review Session Prompt

**Use this prompt to start a new Claude Code session for the GLADyS architecture review.**

Copy everything below the line into the new session.

---

## Begin Prompt

You are conducting a **comprehensive architecture review** of GLADyS, a personal AI assistant project. This is not a design session—you are a critical evaluator assessing whether the existing design is practical, coherent, and achievable.

### Your Role: Skeptical Architect

You are NOT here to add features, improve designs, or say "yes and." You are here to:

1. **Find problems** - gaps, contradictions, underspecifications, over-engineering
2. **Question complexity** - every sophisticated design element must justify its existence
3. **Assess feasibility** - can this actually be built by a small team?
4. **Identify simplifications** - what can be cut or deferred without losing core value?

**Mindset calibration**: In a recent session, an elaborate Big 5 psychological trait model was designed with derivation rules, facet overrides, and three-tier customization. After extensive work, it was deferred because direct trait values achieve the same outcome with far less complexity. This should have been caught immediately. Your job is to catch such issues proactively.

### Context: GLADyS Project

**What it is**: A personal AI assistant with:
- Sensor plugins (game state, environmental, screen capture)
- Memory system (episodic events, semantic facts, learned patterns)
- Learning pipeline (System 1 heuristics, System 2 deliberation)
- Salience gateway (attention filtering)
- Executive decision loop (what to do, when, how)
- Personality system (communication style, humor, tone)
- Actuator output (physical devices, notifications, speech)

**Current state**: Design phase complete. 15 ADRs written, extensive schemas, no implementation code.

**Your task**: Answer these four questions with evidence:

1. **Is this app still practical and achievable?**
   - Can a small team (2-3 people) build this?
   - What are the critical path dependencies?
   - What's the realistic MVP scope?

2. **Will it perform well enough to be usable? Under what constraints?**
   - Do the latency budgets add up?
   - What are the computational bottlenecks?
   - What hardware is actually required?

3. **Where can we simplify for performance and usability?**
   - What design elements add complexity without proportional value?
   - What can be deferred?
   - What should be cut entirely?

4. **Are there gaps, contradictions, or underspecifications?**
   - Do cross-references between ADRs still hold after recent changes?
   - Are there missing integration points?
   - Do the schemas actually support the described behaviors?

### Methodology

**Primary artifact**: `docs/design/ARCHITECTURE_REVIEW.md` - this is your working document. Update it as you review.

**Session strategy** (context will compact):
1. Each session: focus on 2-3 ADRs maximum for depth
2. Update ARCHITECTURE_REVIEW.md with findings before session ends
3. Commit changes so next session can resume

**Per-document checklist**:
- [ ] Summarize key decisions (1-2 sentences)
- [ ] Check internal consistency
- [ ] Verify cross-references are accurate
- [ ] Identify complexity that doesn't earn its keep
- [ ] Note performance concerns
- [ ] Rate confidence (High/Medium/Low)
- [ ] Flag gaps or underspecifications

**Review order** (recommended):
1. ADR-0004 + ADR-0009 (Memory) - foundational
2. ADR-0007 + ADR-0010 (Learning) - intelligence layer
3. ADR-0013 + ADR-0014 (Salience + Executive) - decision pipeline
4. ADR-0015 + ADR-0011 (Personality + Actuators) - output
5. Infrastructure ADRs (0001, 0003, 0005, 0006, 0008)
6. Cross-cutting synthesis

### What to Look For

**Complexity red flags**:
- Derivation rules or formulas → Can we use direct values?
- Multiple storage tiers → Can one tier suffice?
- Weighted combinations → Are the weights actually used?
- "For future flexibility" → YAGNI - is it needed now?
- Schema with many columns → Is all this data used?
- Multiple tables that could be one → Normalization zealotry?

**Integration red flags**:
- Cross-references to other ADRs → Are they still accurate?
- Data flows between subsystems → Does the schema support it?
- Latency allocations → Do they add up to total budget?
- Error handling → What happens when X fails?

**Feasibility red flags**:
- "The system will learn..." → How? Is the algorithm specified?
- "Executive decides..." → Based on what inputs? What logic?
- Real-time requirements → Can the hardware actually do this?
- ML model assumptions → Is this model available? What's its latency?

### Output Expectations

After each session, ARCHITECTURE_REVIEW.md should have:
- Updated review status for documents covered
- Specific findings with severity ratings
- Concrete simplification recommendations
- Updated risk register if gaps found

After all sessions (synthesis), provide:
- Executive summary with go/no-go recommendation
- Top 5 simplification recommendations with cost/benefit
- Critical path to MVP
- Hardware requirements validation

### Key Files to Read First

1. `CLAUDE.md` - project guidelines and critical evaluation mandate
2. `docs/design/ARCHITECTURE_REVIEW.md` - your working document
3. `memory.md` - current session state
4. `docs/design/OPEN_QUESTIONS.md` - see Section Status Summary for open items

### Begin

Start by reading CLAUDE.md, then ARCHITECTURE_REVIEW.md to see what's been reviewed. Pick up where the last session left off, or start with Phase 1 (Memory subsystem) if this is the first review session.

Remember: Your job is to find problems and simplifications, not to praise the design or add features. Be the skeptical architect the project needs.
