# GLADyS Architecture Review

**Status**: In Progress
**Started**: 2026-01-19
**Last Updated**: 2026-01-20

---

## 1. Review Objectives

This review answers four executive-level questions:

1. **Feasibility**: Is this app still practical and achievable?
2. **Performance**: Will it perform well enough to be usable? Under what constraints?
3. **Optimization**: Where can we simplify for performance and usability? What are the costs/benefits?
4. **Integrity**: Are there gaps, contradictions, or underspecifications across the design?

---

## 2. Review Methodology

### 2.1 Principles

- **Simplification bias**: Prefer boring, proven approaches over clever ones
- **YAGNI enforcement**: If we can't articulate a concrete scenario requiring a feature, defer it
- **Proportionality**: Solution complexity must be proportional to problem complexity
- **Cross-reference verification**: When ADRs reference each other, verify accuracy

### 2.2 Per-Document Review Checklist

For each ADR/design doc:

- [ ] Summarize key decisions (1-2 sentences)
- [ ] Check internal consistency
- [ ] Verify cross-references are accurate
- [ ] Identify complexity/simplification opportunities
- [ ] Note performance concerns
- [ ] Rate confidence level (High/Medium/Low)
- [ ] Flag gaps or underspecifications

### 2.3 Session Strategy

Each review session:
1. Read this file first to resume context
2. Focus on 2-3 ADRs maximum for depth
3. Update findings in Section 4
4. Update progress in Section 3
5. Commit changes before session ends

---

## 3. Document Inventory

### 3.1 ADRs (Review Status)

| ADR | Title | Status | Session | Confidence |
|-----|-------|--------|---------|------------|
| ADR-0001 | GLADyS Architecture | ✅ Complete | 1 | High |
| ADR-0002 | Hardware Requirements | ✅ Complete | 1 | High |
| ADR-0003 | Plugin Manifest Specification | ✅ Complete | 1 | Medium |
| ADR-0004 | Memory Schema Details | ✅ Complete | 1 | Medium |
| ADR-0005 | gRPC Service Contracts | ✅ Complete | 1 | High |
| ADR-0006 | Observability and Monitoring | ✅ Complete | 1 | High |
| ADR-0007 | Adaptive Algorithms | ✅ Complete | 1 | Medium |
| ADR-0008 | Security and Privacy | ✅ Complete | 1 | High |
| ADR-0009 | Memory Contracts and Compaction | ✅ Complete | 1 | Medium |
| ADR-0010 | Learning and Inference | ✅ Complete | 1 | Medium |
| ADR-0011 | Actuator Subsystem | ✅ Complete | 1 | High |
| ADR-0012 | Audit Logging | ✅ Complete | 1 | High |
| ADR-0013 | Salience Subsystem | ✅ Complete | 1 | High |
| ADR-0014 | Executive Decision Loop | ✅ Complete | 1 | Medium |
| ADR-0015 | Personality Subsystem | ✅ Complete | 1 | High |

### 3.2 Design Documents

| Document | Purpose | Status |
|----------|---------|--------|
| GLOSSARY.md | Term definitions | [ ] Not Started |
| USE_CASES.md | Validation scenarios | [x] Consolidated (2026-01-20) - 11 UCs + 9 behavioral requirements |
| ~~SCOTT_UC_FEASIBILITY.md~~ | *(Deleted - content merged into USE_CASES.md and Section 10 below)* | [x] Complete (2026-01-20) |
| OPEN_QUESTIONS.md | Active gaps | [ ] Not Started |
| PERSONALITY_IDENTITY_MODEL.md | Deferred design | [ ] Not Started |
| PERSONALITY_TEMPLATES.md | Test archetypes | [ ] Not Started |

### 3.3 Review Order (Recommended)

**Phase 1: Data Foundation**
- ADR-0004 (Memory Schema) - foundational
- ADR-0009 (Memory Contracts) - builds on 0004
- ADR-0012 (Audit) - separate data path

**Phase 2: Intelligence Layer**
- ADR-0007 (Adaptive Algorithms) - learning primitives
- ADR-0010 (Learning and Inference) - builds on 0007

**Phase 3: Processing Pipeline**
- ADR-0013 (Salience) - input processing
- ADR-0014 (Executive) - decision making
- ADR-0003 (Plugin Manifest) - plugin contracts

**Phase 4: Output Layer**
- ADR-0011 (Actuators) - physical output
- ADR-0015 (Personality) - communication style

**Phase 5: Infrastructure**
- ADR-0001 (Architecture) - overall coherence
- ADR-0005 (gRPC) - service contracts
- ADR-0006 (Observability) - operational
- ADR-0008 (Security) - cross-cutting

**Phase 6: Synthesis**
- Cross-cutting analysis
- Performance assessment
- Simplification recommendations
- Executive summary

---

## 4. Subsystem Findings

### 4.1 Memory Subsystem (ADR-0004, ADR-0009)

**Review Status**: ✅ Complete (Session 1, 2026-01-19)

**Key Decisions**:
- 5-tier memory hierarchy (L0-L4) inspired by CPU caches
- PostgreSQL + pgvector for persistent storage
- EWMA for user profile adaptation with stability-gated long-term promotion
- Time-based partitioning for episodic events
- 9 tables total (episodic_events, semantic_facts, user_profile, entities, learned_patterns, heuristics, feedback_events, episodes, episode_events)

**Internal Consistency**: ⚠️ Issues Found
- Partition boundary definitions use `now()` which is evaluated at table creation time, not dynamically. New partitions won't be created automatically.
- ADR-0004 notes "Start with L0 + L1 + L3" but the architecture diagram and code assume all levels exist.

**Cross-Reference Accuracy**: ⚠️ Issues Found
- **ADR-0009 vs ADR-0004**: Ingest contract requires `episode_id` but ADR-0004 has `primary_episode_id` as nullable
- **Terminology mismatch**: ADR-0009 API is `IngestEpisodes()` but ADR-0004 stores events, not episodes
- **Compaction output fields**: ADR-0009 mentions `topic`, `salience_aggregate` in summaries but no `memory_summaries` table exists
- **ADR-0009 is severely underspecified**: 135 lines vs 1629 lines in ADR-0004. Contracts are logical API shapes without actual message definitions.

**Complexity Assessment**: 🔴 High - Needs Simplification

| Aspect | Count | Concern |
|--------|-------|---------|
| Tables | 9 | Too many for MVP |
| Memory tiers | 5 | Over-engineered; L1+L2 may be premature |
| Background jobs | 6+ | Heavy operational burden |
| Indexes | 12+ | GIN on JSONB is expensive to maintain |

**Specific complexity red flags:**
1. **episode_events junction table**: Many-to-many relationship for events ↔ episodes. Justification is weak ("doorbell relevant to gaming AND home security"). Most events have exactly one episode. YAGNI.
2. **semantic_facts requires LLM extraction**: Runs every 10 min with LLM calls. Significant compute cost. Is this needed for MVP?
3. **learned_patterns + heuristics tables**: Support ADR-0010 System 1/2 but add complexity. Can be added later.
4. **Salience stored as JSONB with GIN index**: Expensive writes. Top dimensions could be extracted to columns.

**Performance Concerns**: ⚠️ Medium

| Issue | Impact | Mitigation |
|-------|--------|------------|
| HNSW index on append-heavy table | Write amplification | Partial index on non-archived only (partially addressed) |
| GIN index on salience JSONB | Slow updates on high-frequency writes | Extract top dimensions to columns |
| Embedding computation ~10-50ms | Bottleneck at high event rates | Lazy/background generation (addressed) |
| Partition boundary bug | New partitions won't auto-create | Needs scheduled partition manager job (not specified) |
| Embedding dimension `vector(384)` | Model lock-in | No migration strategy documented |

**Simplification Opportunities**:

| ID | Current | Proposed | Savings | Risk |
|----|---------|----------|---------|------|
| S-MEM-1 | 9 tables | 4 tables (episodic_events, entities, user_profile, feedback_events) | -5 tables, simpler schema | Defer learning until proven |
| S-MEM-2 | L1 hot cache + L2 warm buffer | Skip both; start with PostgreSQL only | Simpler architecture | May need cache later if latency >50ms |
| S-MEM-3 | episode_events junction (M:M) | primary_episode_id FK only (1:M) | -1 table, simpler queries | Lose secondary associations (unlikely needed) |
| S-MEM-4 | semantic_facts via LLM | Defer to post-MVP | No LLM background jobs | Less "understanding" initially |
| S-MEM-5 | Salience as JSONB | Top 3 dimensions as columns | No GIN index, faster writes | Less flexibility in salience dimensions |

**Gaps/Issues**:

| ID | Severity | Description |
|----|----------|-------------|
| G-MEM-1 | High | Partition management not specified - `now()` evaluated once at creation |
| G-MEM-2 | Medium | Memory vs Audit query routing unspecified (when to query each) |
| G-MEM-3 | Medium | Embedding migration strategy when models change |
| G-MEM-4 | Low | Multi-user support not addressed (single `user_profile`) |
| G-MEM-5 | Medium | ADR-0009 contracts don't specify error handling or failure modes |

**Recommendations**:

1. **Immediate**: Fix partition boundary bug - add scheduled partition manager job
2. **MVP scope**: Reduce to 4 core tables; skip L1/L2; defer semantic_facts and learned_patterns
3. **Short-term**: Document Memory vs Audit query routing
4. **Pre-MVP**: Reconcile ADR-0009 terminology with ADR-0004 (events vs episodes)

**Confidence**: Medium
- Core design is sound (hierarchical storage, EWMA adaptation)
- Complexity has crept in without proportional value
- Cross-ADR contracts need reconciliation

---

### 4.2 Learning Subsystem (ADR-0007, ADR-0010)

**Review Status**: ✅ Complete (Session 1, 2026-01-19)

**Key Decisions**:
- Dual-timescale EWMA (short-term fast α=0.3-0.5, long-term slow β=0.05-0.1)
- Bayesian confidence tracking overlaid on EWMA
- Gradient descent for threshold tuning
- System 1/2 dual-process model (Kahneman-inspired)
- Six learning subsystems (Heuristic Store, Novelty Detector, Episodic Store, Pattern Detector, Preference Tracker, Causal Modeler)
- Three Bayesian model types (Beta-Binomial, Normal-Gamma, Gamma-Poisson)
- Sleep mode batch processing for heavy computation

**Internal Consistency**: ⚠️ Minor Issues
- ADR-0007 focuses on user preferences; ADR-0010 on pattern learning. Overlap in Bayesian tracking approaches.
- EWMA α/β naming conflicts with Bayesian α/β parameters (different meanings)
- Both ADRs define similar concepts slightly differently

**Cross-Reference Accuracy**: ✅ Generally Good
- ADR-0010 correctly references ADR-0007 for preference tracking
- ADR-0010 correctly references ADR-0009 for episodic storage
- Tables defined in ADR-0004 match ADR-0010 requirements (learned_patterns, heuristics)

**Complexity Assessment**: 🔴 High - Needs Significant Simplification

**Mechanism layering is excessive:**

| Layer | ADR-0007 | ADR-0010 | Combined Burden |
|-------|----------|----------|-----------------|
| Smoothing | EWMA dual-timescale | - | ✓ |
| Confidence | Bayesian Beta | 3 Bayesian model types | Overlapping |
| Thresholds | Gradient descent tuning | - | ✓ |
| Loss tracking | 4-component loss function | - | Premature |
| Pattern matching | - | Heuristic Store | ✓ |
| Novelty | - | Novelty Detector | Add-on |
| Causality | - | Causal Modeler | Deferred but designed |

**Six learning subsystems is too many for MVP:**
1. Heuristic Store
2. Novelty Detector
3. Episodic Store
4. Pattern Detector
5. Preference Tracker
6. Causal Modeler (+ Executive LLM for System 2)

**Specific concerns:**
1. **EWMA + Bayesian overlay**: Each parameter has *both* EWMA tracking *and* Bayesian confidence. Pick one for MVP.
2. **10+ parameters with per-category learning rates**: Each has its own α, β, stability_threshold. Configuration explosion.
3. **Loss function with 4 components**: timing_loss, relevance_loss, tone_loss, verbosity_loss with weights. Is this needed for MVP?
4. **System 1/2 distinction**: Nice theory, but escalation triggers are underspecified. What's the actual algorithm?
5. **Three Bayesian models "required from Day 1"**: Beta-Binomial, Normal-Gamma, Gamma-Poisson. Each needs correct implementation.
6. **Open questions in ADR-0010**: Heuristic representation, novelty threshold, pattern promotion still undefined.

**Performance Concerns**: ⚠️ Medium

| Issue | Impact | Mitigation |
|-------|--------|------------|
| Sleep mode dependency | Batch learning never runs if system always active | Need explicit scheduling |
| Computational budget vague | "5-10% background" - of what? | Need concrete limits |
| Embedding similarity for novelty | Expensive for high-volume events | Cache embeddings (already noted) |

**Simplification Opportunities**:

| ID | Current | Proposed | Savings | Risk |
|----|---------|----------|---------|------|
| S-LRN-1 | EWMA + Bayesian per parameter | EWMA only for MVP | -50% tracking complexity | Lose confidence intervals |
| S-LRN-2 | 6 learning subsystems | 2 subsystems (Preference Tracker + LLM) | -4 subsystems | Less "fast path" optimization |
| S-LRN-3 | 3 Bayesian model types | Beta-Binomial only | -2 model implementations | Can't model continuous/rate data properly |
| S-LRN-4 | Per-parameter learning rates | 3 rate profiles (fast/medium/slow) | -75% config | Less fine-grained tuning |
| S-LRN-5 | Loss function tracking | Skip for MVP | No loss computation | Harder to optimize later |
| S-LRN-6 | System 1/2 escalation | Always use LLM (System 2) | No heuristic short-circuit | Higher latency, more LLM cost |
| S-LRN-7 | Causal Modeler | Remove entirely | -1 subsystem | No causal reasoning |
| S-LRN-8 | Novelty Detector | Defer to post-MVP | -1 subsystem | Less intelligent routing |

**Gaps/Issues**:

| ID | Severity | Description |
|----|----------|-------------|
| G-LRN-1 | Medium | System 1→2 escalation triggers underspecified |
| G-LRN-2 | Medium | Heuristic representation schema not defined |
| G-LRN-3 | Medium | Novelty threshold value not specified |
| G-LRN-4 | Low | Pattern promotion criteria undefined |
| G-LRN-5 | Medium | Sleep mode activation criteria too vague ("user idle for 30 min") |

**Recommendations**:

1. **MVP simplification**: Use simple EWMA preference tracking + LLM for all decisions. Add heuristics later when latency is a measured problem.
2. **Remove Causal Modeler**: Acknowledged as background/deferred - remove from architecture.
3. **Reduce parameters**: Identify 5 core preferences (verbosity, humor, proactivity, formality, helpfulness). Add more only when needed.
4. **Skip loss function**: Track simple feedback (thumbs up/down) for MVP.
5. **Define escalation triggers**: If keeping System 1/2, specify exact algorithm for when to escalate.

**Confidence**: Medium
- Dual-process model is sound conceptually
- Implementation complexity far exceeds MVP needs
- Strong candidate for aggressive simplification

---

### 4.3 Salience Subsystem (ADR-0013)

**Review Status**: ✅ Complete (Session 1, 2026-01-19)

**Key Decisions**:
- Multi-stage evaluation pipeline: Suppression Check (1ms) → Heuristic Eval (5-20ms) → Deep Eval (50-80ms, optional) → Threshold Gate
- 9 salience dimensions (threat, opportunity, humor, novelty, goal_relevance, social, emotional, actionability, habituation)
- Attention budget with token-based capacity and priority queuing
- Context profiles with per-dimension weights and thresholds
- Exponential habituation decay with min_sensitivity floor (never fully suppress)
- Executive feedback loop (suppress, heighten, habituate signals)

**Internal Consistency**: ✅ Good
- Pipeline stages are well-defined with clear latency budgets
- Cold start strategy is explicit and reasonable (forward more initially)
- Embedding model migration strategy is thorough

**Cross-Reference Accuracy**: ⚠️ Minor Issues
- References ADR-0010 heuristics but heuristic format is underspecified in ADR-0010
- References ADR-0001 Section 7.1 for dimensions - accurate
- References ADR-0005 for gRPC - accurate

**Complexity Assessment**: 🟡 Medium - Some Simplification Possible

| Aspect | Count | Concern |
|--------|-------|---------|
| Salience dimensions | 9 | Could reduce to 4-5 for MVP |
| Pipeline stages | 4 | Reasonable |
| Context profiles | 3+ (gaming, home, work, general) | Reasonable |
| Configurable parameters per context | 18+ (9 weights + 9 thresholds) | High config burden |

**Specific concerns**:
1. **Cross-context event routing**: Events can be evaluated by multiple contexts, take MAX. Adds complexity.
2. **Deep evaluation trigger undefined**: "heuristics are uncertain" - what threshold?
3. **9 dimensions is many**: humor, social, emotional may be redundant for MVP
4. **Burst detection for habituation**: Nice-to-have, not MVP

**Performance Concerns**: ✅ Low - Well-Specified
- Latency targets are reasonable and achievable
- >100 events/sec throughput is realistic
- Overload handling is specified

**Simplification Opportunities**:

| ID | Current | Proposed | Savings | Risk |
|----|---------|----------|---------|------|
| S-SAL-1 | 9 salience dimensions | 5 dimensions (threat, opportunity, goal_relevance, novelty, habituation) | -4 computations per event | Lose humor/social/emotional nuance |
| S-SAL-2 | Cross-context routing (MAX) | Single active context | Simpler routing | Doorbell during gaming may be missed |
| S-SAL-3 | Deep evaluation (Stage 3) | Skip for MVP - heuristics only | -50ms latency path | Less nuanced scoring |
| S-SAL-4 | Exponential decay + burst detection | Linear decay | Simpler math | Less biologically accurate |
| S-SAL-5 | Embedding model migration planning | Defer to post-MVP | Less planning overhead | May need rework later |

**Gaps/Issues**:

| ID | Severity | Description |
|----|----------|-------------|
| G-SAL-1 | Medium | Deep evaluation trigger threshold not specified |
| G-SAL-2 | Low | Multi-user salience profiles deferred but not planned |
| G-SAL-3 | Low | Context detection algorithm not specified (how detect "gaming"?) |

**Recommendations**:
1. **MVP**: 5 dimensions, single context, heuristics only
2. **Post-MVP**: Add cross-context routing when multiple use cases are active
3. **Specify**: Deep evaluation trigger threshold (e.g., heuristic confidence <0.6)

**Confidence**: High
- Well-structured ADR
- Reasonable complexity for the problem
- Clear simplification path for MVP

---

### 4.4 Executive Subsystem (ADR-0014)

**Review Status**: ✅ Complete (Session 1, 2026-01-19)

**Key Decisions**:
- Hybrid loop: event-driven + clock-driven (1 Hz tick)
- 4-stage decision framework: Relevance → Timing → Response Type → Content
- 7 personality traits affecting multiple decision stages
- Skill pipeline for response generation (Domain → Style → Personality Filter)
- Proactive scheduling with 5 opportunity types
- Output routing to TTS/text/action

**Internal Consistency**: ⚠️ Minor Issues
- Personality traits reference ADR-0001 Section 9.2, but ADR-0015 now defines personality
- Skill orchestration references ADR-0003 but details are thin

**Cross-Reference Accuracy**: ⚠️ Issues Found
- **ADR-0014 → ADR-0001**: References personality matrix from Section 9.2, but ADR-0015 now supersedes this
- **Latency math**: ADR-0013 allocates 100ms for salience, ADR-0014 allocates 100ms for decision + 200ms for generation. ADR-0001 gives 400ms total. This adds up but is tight.
- **ADR-0014 → ADR-0007**: Correctly references adaptive algorithms for learning

**Complexity Assessment**: 🔴 High - Needs Simplification

| Aspect | Count | Concern |
|--------|-------|---------|
| Personality traits | 7 | Each affects different decision stages |
| Response types | 6 | Alert, Observation, Suggestion, Question, Quip, Check-in |
| Proactive opportunity types | 5 | Check-in, Observation, Reminder, Mood comment, Achievement |
| Skill pipeline stages | 3 | Domain → Style → Personality Filter |
| PersonalityState components | 5 | base, context_modifiers, user_overrides, mood, rapport |

**Specific concerns**:
1. **Trait proliferation**: 7 traits all modifying decisions is complex to test and debug
2. **Mood + Rapport tracking**: Adds emotional state on top of traits. Needed for MVP?
3. **Proactive scheduling**: 5 opportunity types each with min_interval, probability, cooldown. Over-engineered.
4. **Skill pipeline**: Multiple transformation stages before output. Can we just use LLM directly?
5. **Open questions are significant**: LLM selection, multi-turn conversation, goal management, fallback - these need answers before implementation.

**Performance Concerns**: ⚠️ Medium

| Issue | Impact | Mitigation |
|-------|--------|------------|
| 400ms LLM latency budget is tight | May not hit targets with local models | Consider cloud LLM for MVP |
| 1 Hz tick rate | 1 second max response latency | May need faster tick for gaming |
| Skill pipeline adds latency | Each stage adds overhead | Can bypass for MVP |

**Simplification Opportunities**:

| ID | Current | Proposed | Savings | Risk |
|----|---------|----------|---------|------|
| S-EXE-1 | 7 personality traits | 4 traits (humor, proactive, helpfulness, verbosity) | -3 traits, simpler interaction | Less personality nuance |
| S-EXE-2 | 6 response types | 3 types (Alert, Observation, Quip) | Simpler type selection | Lose Suggestion, Question, Check-in |
| S-EXE-3 | 5 proactive opportunity types | 1 type (Check-in only) | Much simpler proactive | Lose achievements, observations |
| S-EXE-4 | Skill pipeline (3 stages) | Direct LLM generation | No pipeline overhead | Lose skill composition |
| S-EXE-5 | Mood + Rapport tracking | Skip for MVP | Less state management | Less emotionally intelligent |
| ~~S-EXE-6~~ | ~~Proactive behavior~~ | ~~Reactive only for MVP~~ | ~~No proactive complexity~~ | **REJECTED**: Proactive is MVP-required |

**Gaps/Issues**:

| ID | Severity | Description |
|----|----------|-------------|
| G-EXE-1 | High | LLM selection not decided (local vs cloud, which model) |
| G-EXE-2 | High | Goal management undefined (where do goals come from?) |
| G-EXE-3 | Medium | Multi-turn conversation handling not specified |
| G-EXE-4 | Medium | Fallback behavior when LLM fails not specified |
| G-EXE-5 | Medium | Personality reference to ADR-0001 should be ADR-0015 |

**Recommendations**:
1. **Immediate**: Update personality references to ADR-0015
2. **Pre-MVP**: Decide LLM strategy (recommend: cloud API for MVP, local for v2)
3. **MVP scope**: Proactive + reactive, 3-4 traits, 3 response types, simplified skill pipeline
4. **Post-MVP**: Add cross-context routing, sophisticated proactive scheduling
5. **Specify**: Fallback behavior for LLM timeout/error

**Confidence**: Medium
- Good conceptual framework
- Too much complexity for MVP
- Open questions need resolution before implementation

---

### 4.5 Personality Subsystem (ADR-0015)

**Review Status**: ✅ Complete (Session 1, 2026-01-19)

**Key Decisions**:
- Response Model only for MVP (Identity Model deferred - good decision!)
- Bipolar traits (-1 to +1) for communication, affect, interaction
- Humor separated: frequency (0-1) + weighted styles
- Two-tier customization: Response (±0.2 bounded by pack), Safety (full user control)
- Personality as plugin with prompts, style rules, voice config
- Context modifiers (high_threat, user_frustrated, late_night, celebration)

**Internal Consistency**: ✅ Good
- Identity Model correctly deferred with full design preserved
- Clear distinction between irony (communication mode) and sarcasm (irony + humor)
- Pack-defined bounds enable character coherence

**Cross-Reference Accuracy**: ⚠️ Minor Issues
- ADR-0015 supersedes ADR-0001 Section 9 - should be noted explicitly
- ADR-0014 trait names may not match ADR-0015 exactly - needs reconciliation

**Complexity Assessment**: 🟡 Medium - Acceptable for Feature Importance

| Aspect | Count | Concern |
|--------|-------|---------|
| Communication traits | 5 | irony, literalness, directness, formality, verbosity |
| Humor styles | 5 | observational, self_deprecating, punny, absurdist, dark |
| Affect + Interaction traits | 4 | warmth, energy, proactivity, confidence |
| Context modifiers | 4 automatic + user triggers | Reasonable |
| New database tables | 3 | personality_packs, user_personality_state, active_personality_state |

**Positive notes**:
- Identity Model was correctly identified as over-engineering and deferred
- Pack-based distribution is extensible
- Safety boundaries are well-specified (punch up, not down)
- Irony/sarcasm distinction is thoughtful design

**Specific concerns**:
1. **Humor callback memory**: Tracking interactions for joke references adds state. Is this MVP?
2. **Mood persistence**: How long does mood state persist across sessions? Underspecified.
3. **10+ trait dimensions**: May be hard to tune all of them coherently

**Performance Concerns**: ✅ Low
- Personality traits are static per request - no compute overhead
- Context modifiers are rule-based lookups
- Pack loading is infrequent

**Simplification Opportunities**:

| ID | Current | Proposed | Savings | Risk |
|----|---------|----------|---------|------|
| S-PER-1 | 5 communication + 4 affect/interaction | 5 core traits | -4 dimensions | Less nuance |
| S-PER-2 | Humor callback memory | Skip for MVP | Less state | Lose "remember when" jokes |
| S-PER-3 | 4 context modifiers | 1 modifier (high_threat only) | Simpler | Less adaptive |
| S-PER-4 | Mood persistence | Reset each session | Less state | Lose mood continuity |

**Gaps/Issues**:

| ID | Severity | Description |
|----|----------|-------------|
| G-PER-1 | Medium | Mood persistence duration not specified |
| G-PER-2 | Low | TTS engine selection still open question |
| G-PER-3 | Low | Pack marketplace infrastructure unspecified |
| G-PER-4 | Medium | ADR-0014 trait names may not match |

**Recommendations**:
1. **Immediate**: Reconcile trait names with ADR-0014
2. **MVP scope**: All traits as designed (personality is core value prop), but skip callback memory
3. **Document**: Mood persistence rules
4. **Consider**: Single personality pack for MVP (SecUnit) - depth over breadth

**Confidence**: High
- Well-designed ADR with good complexity decisions
- Identity Model deferral was the right call
- Personality is core to product - justified complexity

---

### 4.6 Actuator Subsystem (ADR-0011)

**Review Status**: ✅ Complete (Session 1, 2026-01-19)

**Key Decisions**:
- Integration plugin model (Home Assistant first, Google/Amazon later)
- Three trust tiers: comfort, security, safety
- Per-actuator rate limiting to prevent oscillation
- Safety bounds enforced at orchestrator level
- Confirmation UX for high-risk actions (security tier)
- Async feedback via state monitoring

**Internal Consistency**: ✅ Good
- Trust tier → audit routing is clear
- Rate limiting model is well-specified
- Safety bounds are non-bypassable

**Cross-Reference Accuracy**: ✅ Good
- ADR-0011 → ADR-0003: Extends plugin model correctly
- ADR-0011 → ADR-0008: References permission model
- ADR-0011 → ADR-0012: Routes to correct audit tables by trust tier

**Complexity Assessment**: 🟡 Medium - Reasonable for Problem

| Aspect | Count | Concern |
|--------|-------|---------|
| Trust tiers | 3 | Appropriate |
| Conflict resolution strategies | 4 | Could simplify |
| Open questions | 7 | Need resolution |

**Specific concerns**:
1. **Dependency modeling**: "Can't AC if window open" - soft constraints add complexity
2. **Conflict resolution**: 4 strategies (latest wins, safety wins, user wins, source priority) - which is default?
3. **Open questions significant**: Credential storage, entity discovery, offline handling still unresolved
4. **Gaming actuators**: How Aperture fits this model is unclear

**Performance Concerns**: ✅ Low
- Latency budgets are reasonable (2000ms user-requested, 500ms reactive safety)
- Rate limiting prevents runaway commands
- Separate from conversational latency budget

**Simplification Opportunities**:

| ID | Current | Proposed | Savings | Risk |
|----|---------|----------|---------|------|
| S-ACT-1 | Dependency modeling | Skip for MVP | Less validation | Manual user coordination |
| S-ACT-2 | 4 conflict resolution strategies | 2 strategies (safety wins, then user wins) | Simpler logic | Less flexibility |
| S-ACT-3 | Async feedback with state monitoring | Sync only for MVP | Less state tracking | May miss slow actuators |
| S-ACT-4 | Auto entity discovery | Explicit mapping only | Less "magic" | More manual config |

**Gaps/Issues**:

| ID | Severity | Description |
|----|----------|-------------|
| G-ACT-1 | High | Credential storage for integration tokens unspecified |
| G-ACT-2 | Medium | Gaming actuator (Aperture) fit unclear |
| G-ACT-3 | Medium | Offline/degraded handling unspecified |
| G-ACT-4 | Low | Multi-integration conflict (same device via HA and Google) |

**Recommendations**:
1. **Pre-MVP**: Resolve credential storage with ADR-0008
2. **Pre-MVP**: Clarify gaming actuator strategy
3. **MVP scope**: Home Assistant only, explicit mapping, sync feedback
4. **Default**: Safety wins > User wins > Latest wins for conflict resolution

**Confidence**: High
- Well-structured for the problem
- Open questions are resolvable
- Trust tier model is sound

---

### 4.7 Audit Subsystem (ADR-0012)

**Review Status**: ✅ Complete (Session 1, 2026-01-19)

**Key Decisions**:
- Three audit tables with different integrity: audit_security (Merkle tree), audit_actions (hash per record), audit_observations (light)
- Hierarchical event taxonomy: category.subject.action
- Separate from brain memory (append-only vs mutable)
- Tiered storage (hot/warm/cold)
- Role-based access (Brain read-only, User full query, no one can modify before retention expiry)

**Internal Consistency**: ✅ Good
- Clear separation from memory system
- Tiered integrity matches risk profiles

**Cross-Reference Accuracy**: ✅ Good
- ADR-0012 → ADR-0011: Actuator trust tiers route to correct tables
- ADR-0012 → ADR-0008: Aligns with security principles

**Complexity Assessment**: 🟡 Medium - Acceptable

| Aspect | Count | Concern |
|--------|-------|---------|
| Audit tables | 3 | Appropriate for risk tiering |
| Integrity mechanisms | 3 | Hash, Merkle, light |
| Open questions | 4 | Resolvable |

**Simplification Opportunities**:

| ID | Current | Proposed | Savings | Risk |
|----|---------|----------|---------|------|
| S-AUD-1 | 3 integrity mechanisms | 2 (hash + Merkle) | Skip light tier | audit_observations less efficient |
| S-AUD-2 | Merkle tree | Hash per record only | No Merkle implementation | Lose tamper-proof verification |

**Gaps/Issues**:

| ID | Severity | Description |
|----|----------|-------------|
| G-AUD-1 | Medium | Merkle tree implementation undefined (build vs buy) |
| G-AUD-2 | Low | Export format undefined (JSON lines vs Parquet) |
| G-AUD-3 | Low | GDPR right-to-be-forgotten tension with "forever" retention |

**Confidence**: High - Well-designed, reasonable complexity

---

### 4.8 Plugin System (ADR-0003)

**Review Status**: ✅ Complete (Session 1, 2026-01-19)

**Key Decisions**:
- YAML manifest format for all plugin types
- Four plugin types: sensor, skill, personality, output
- Resource declaration (GPU, VRAM, memory, models)
- Lifecycle configuration (startup, shutdown, state persistence)
- Activation conditions by type

**Internal Consistency**: ⚠️ Issues Found
- **Personality manifest format outdated**: ADR-0003 uses 0-1 traits, ADR-0015 uses bipolar -1 to +1
- **Trait names don't match ADR-0015**: ADR-0003 uses `sarcasm`, ADR-0015 uses `irony`

**Cross-Reference Accuracy**: ⚠️ Issues Found
- **ADR-0003 → ADR-0012**: Plugins should declare emitted audit event types but schema doesn't include this
- **ADR-0003 → ADR-0015**: Personality manifest example doesn't match ADR-0015 Response Model

**Complexity Assessment**: 🟡 Medium - Comprehensive but Needs Update

**Gaps/Issues**:

| ID | Severity | Description |
|----|----------|-------------|
| G-PLG-1 | Medium | Personality manifest doesn't match ADR-0015 Response Model |
| G-PLG-2 | Medium | No field for declaring audit event types (per ADR-0012) |
| G-PLG-3 | Low | Manifest versioning strategy incomplete |

**Recommendations**:
1. **Immediate**: Update personality manifest schema to match ADR-0015
2. **Pre-MVP**: Add audit event declaration field to manifest schema

**Confidence**: Medium - Good foundation but needs reconciliation with ADR-0015

---

### 4.9 Infrastructure (ADR-0001, ADR-0002, ADR-0005, ADR-0006, ADR-0008)

**Review Status**: ✅ Complete (Session 1, 2026-01-19)

#### ADR-0001 (Core Architecture)

**Key Decisions**: Brain-inspired polyglot architecture (Rust orchestrator, Python sensors/salience/memory, C# Executive), gRPC IPC, plugin-based extensibility

**Assessment**: ✅ Foundation is solid but some sections outdated
- Section 9 (Personality) superseded by ADR-0014/0015
- Section 8 (Memory) superseded by ADR-0004/0009
- Latency budget (1000ms) is exactly allocated - no slack

#### ADR-0002 (Hardware)

**Key Decisions**: RTX 2070 8GB baseline, dual-GPU upgrade path, model VRAM estimates

**Assessment**: ✅ Realistic assessment
- Correctly identifies GPU as limiting factor
- Good model recommendations by component
- Cloud API fallback acknowledged for Executive

#### ADR-0005 (gRPC)

**Key Decisions**: Pub/sub via orchestrator, proto package structure, common messages

**Assessment**: ✅ Well-specified
- Topology is clear
- Message patterns appropriate
- Latency considerations included

#### ADR-0006 (Observability)

**Key Decisions**: Prometheus + Loki + Jaeger + Grafana stack

**Assessment**: ✅ Industry standard, local-friendly
- Good pillar coverage
- Polyglot support confirmed
- No obvious gaps

#### ADR-0008 (Security)

**Key Decisions**: Local-first, fail-closed, defense-in-depth, tiered retention, permission chain

**Assessment**: ✅ Strong security posture
- Core principles well-defined
- Data retention tiers specified
- Plugin sandboxing mentioned

**Overall Infrastructure Confidence**: High - Foundation is solid

---

## 5. Cross-Cutting Concerns

### 5.1 Data Flow Trace

**Scenario**: Doorbell rings → GLADyS alerts user

| Step | Component | ADR | Latency | Notes |
|------|-----------|-----|---------|-------|
| 1 | Home Assistant sensor emits event | ADR-0003, ADR-0011 | ~50ms | Integration plugin receives |
| 2 | Event sent via gRPC to Orchestrator | ADR-0005 | ~5ms | Pub/sub fan-out |
| 3 | Salience Gateway evaluates | ADR-0013 | ~20-100ms | Heuristic + optional deep eval |
| 4 | Event stored in memory | ADR-0004 | ~10ms | PostgreSQL insert |
| 5 | Executive receives salient event | ADR-0014 | ~100ms | Decision framework |
| 6 | LLM generates response | ADR-0014 | ~200-400ms | "Someone's at the door" |
| 7 | TTS synthesizes audio | ADR-0003 (output) | ~150ms | Piper TTS |
| 8 | User hears alert | - | - | End-to-end complete |

**Total**: ~535-815ms (within 1000ms budget)

**Gaps Identified**:
- Step 5→6: Skill pipeline routing not fully specified (direct LLM OK for MVP)
- Step 6→7: Output routing contract not explicit in any ADR (implicit in ADR-0005)

### 5.2 Latency Budget Allocation

| Profile | Total Budget | Allocated | Remaining | Status |
|---------|-------------|-----------|-----------|--------|
| realtime | 500ms | 50+5+20+10+100+200+100 = 485ms | 15ms | ⚠️ Tight |
| conversational | 1000ms | 50+5+100+10+100+400+150 = 815ms | 185ms | ✅ OK |
| comfort | 5000ms | Same pipeline, longer LLM allowed | >4000ms | ✅ OK |

**Concerns**: Realtime profile has almost no slack. Any component going over breaks budget.

### 5.3 Schema Consistency

| Table | Defined In | Referenced By | Consistent? |
|-------|------------|---------------|-------------|
| episodic_events | ADR-0004 | ADR-0009, 0010, 0013 | ⚠️ episode_id required vs optional |
| semantic_facts | ADR-0004 | ADR-0009, 0010 | ✅ |
| learned_patterns | ADR-0004 | ADR-0010 | ⚠️ Heuristic format underspecified |
| heuristics | ADR-0004 | ADR-0010 | ⚠️ Heuristic format underspecified |
| user_profile | ADR-0004, ADR-0007 | ADR-0010, 0014 | ✅ |
| episodes | ADR-0004 | ADR-0009 | ✅ |
| episode_events | ADR-0004 | - | ⚠️ YAGNI - junction may be over-engineered |
| personality_packs | ADR-0015 | ADR-0003 | ⚠️ Manifest doesn't match |
| audit_* | ADR-0012 | ADR-0011 | ✅ |

### 5.4 Error Handling Gaps

| Component | Error Type | Handling Specified? | Gap Severity |
|-----------|------------|---------------------|--------------|
| Sensors | Crash | ✅ ADR-0001: graceful degradation | Low |
| Executive | LLM timeout | ⚠️ ADR-0001: fallback mentioned | Medium - no specific response |
| Memory | Query timeout | ❌ Not specified | Medium |
| Actuator | Command failure | ✅ ADR-0011: feedback loop | Low |
| gRPC | Connection lost | ⚠️ ADR-0005: circuit breaker mentioned | Medium - details thin |

### 5.5 Security Boundary Verification

| Boundary | Protection | ADR | Status |
|----------|------------|-----|--------|
| Plugin → Orchestrator | Permission chain | ADR-0008 | ✅ |
| Sensor → Raw data | No storage (transcription only) | ADR-0008 | ✅ |
| Memory → User | Data locality | ADR-0001, 0008 | ✅ |
| Actuator → Physical | Trust tiers + confirmation | ADR-0011 | ✅ |
| Audit → Brain | Read-only access | ADR-0012 | ✅ |
| External credentials | Storage mechanism | ADR-0008 | ❌ Not specified (G-ACT-1) |

---

## 6. Performance Assessment

### 6.1 Computational Costs

| Operation | Frequency | Cost | Concern Level |
|-----------|-----------|------|---------------|
| Embedding generation | Per event (~100/sec max) | ~10-50ms | 🟡 Medium - batching helps |
| HNSW search | Per query | ~5-20ms | ✅ Low |
| Bayesian update | Per feedback | ~1ms | ✅ Low |
| LLM call (local 7-14B) | Per response | 200-500ms | 🟡 Medium - GPU dependent |
| LLM call (cloud API) | Per response | 500-2000ms | ⚠️ Network variability |
| Salience heuristics | Per event | ~5-20ms | ✅ Low |
| Salience deep eval | Per uncertain event | ~50-80ms | 🟡 Medium - skip for MVP |
| GIN index update (JSONB) | Per insert | ~1-5ms | 🟡 Medium - consider columns |
| HNSW index maintenance | Background | O(log n) | ⚠️ May need partial index |

### 6.2 Storage Projections

**Assumptions**: 1 event/second average during active hours (8 hrs/day), 2KB per full event, 10:1 consolidation

| Data Type | Growth Rate | 1 Year | 5 Years | Concern |
|-----------|-------------|--------|---------|---------|
| Episodic events (full) | ~29K/day → consolidated | ~500MB active | Rolls over | ✅ Low (consolidation) |
| Semantic facts | ~3K/day (10:1 from events) | ~220MB | ~1.1GB | ✅ Low |
| Audit logs (actions) | ~5K/day | ~150MB | ~750MB | ✅ Low |
| Audit logs (security) | ~100/day | ~5MB | ~25MB | ✅ Low |
| Embeddings | ~29K/day × 1.5KB | ~16GB | ~80GB | 🟡 Medium - prune old |

**Total Year 1**: ~20GB (manageable on local storage)

### 6.3 Bottleneck Analysis

| Bottleneck | Component | Impact | Mitigation |
|------------|-----------|--------|------------|
| **LLM inference** | Executive | Dominates latency budget (200-500ms) | Cloud API for MVP, local for v2 |
| **GPU contention** | All ML models | Can't run Whisper + YOLO + LLM concurrently on 8GB | Dual GPU or time-slice |
| **HNSW on high-volume** | Memory | Insert amplification | Partial index on non-archived |
| **Realtime budget** | End-to-end | Only 15ms slack | Relax to conversational (1000ms) for MVP |

---

## 7. Simplification Opportunities

### 7.1 MVP Simplification Summary

**Recommended MVP scope vs full design:**

| Subsystem | Full Design | MVP Scope | Savings |
|-----------|-------------|-----------|---------|
| **Memory** | 9 tables, 5 tiers | 4 tables, 2 tiers (L0+L3) | -5 tables, -3 tiers |
| **Learning** | 6 subsystems, 3 Bayesian models | EWMA + LLM only | -5 subsystems |
| **Salience** | 9 dimensions, 4 stages | 5 dimensions, heuristics only | -4 dims, -1 stage |
| **Executive** | 7 traits, 6 response types, 5 proactive types | 4 traits, 3 types, 2 proactive types | Moderate |
| **Personality** | Full Response Model | Full (core value prop) | Minimal |
| **Actuator** | Home Assistant + Google + Amazon | Home Assistant only | Fewer integrations |

### 7.2 High-Priority Simplifications

| ID | Area | Current | Simplified | Savings | Risk | Priority |
|----|------|---------|------------|---------|------|----------|
| **S-MEM-1** | Memory tables | 9 | 4 (events, entities, profile, feedback) | -5 tables | Defer learning | **High** |
| **S-MEM-3** | episode_events | M:M junction | 1:M FK only | -1 table | Lose secondary associations | **High** |
| **S-LRN-1** | Learning | EWMA + Bayesian | EWMA only | -50% complexity | Lose confidence intervals | **High** |
| **S-LRN-6** | System 1/2 | Dual-process | Always LLM | No heuristic fast-path | Higher LLM cost | **High** |
| ~~S-EXE-6~~ | ~~Proactive~~ | ~~Reactive only~~ | ~~Major simplification~~ | **REJECTED**: Proactive MVP-required | **N/A** |
| **S-SAL-1** | Salience dims | 9 | 5 (threat, opportunity, goal, novelty, habituation) | -4 computations | Lose humor/social nuance | **Medium** |

### 7.3 Deferred Features (Already Identified)

| Feature | ADR | Why Deferred | Trigger to Reconsider |
|---------|-----|--------------|----------------------|
| Identity Model | ADR-0015 | Complexity without clear value | Personality drift, pack quality issues |
| L2 warm buffer | ADR-0004 | Premature optimization | Flush latency >100ms |
| Belief propagation | ADR-0010 | Complexity | Need causal chains |
| Causal Modeler | ADR-0010 | Research-grade feature | Explicit causal reasoning needed |
| Deep salience evaluation | ADR-0013 | Heuristics may suffice | Heuristic confidence issues |
| Cross-context routing | ADR-0013 | Single context for MVP | Multiple active domains |

### 7.4 Complexity Budget

**Rule of thumb**: Each subsystem should have 3-5 core components for MVP. Current vs target:

| Subsystem | Current Components | MVP Target | Status |
|-----------|-------------------|------------|--------|
| Memory | 9 tables + 6 jobs + 5 tiers | 4 tables + 2 jobs + 2 tiers | 🔴 Over |
| Learning | 6 subsystems + 3 models | 1 (EWMA) + LLM | 🔴 Over |
| Salience | 9 dims + 4 stages | 5 dims + 2 stages | 🟡 Borderline |
| Executive | 7 traits + 6 types + 5 proactive | 4 traits + 3 types + 2 proactive | 🟡 Borderline |
| Personality | 10 dims + 5 humor styles | Full (justified) | ✅ OK |
| Actuator | 3 integrations | 1 (Home Assistant) | ✅ OK |

---

## 8. Risk Register

### 8.1 High-Severity Gaps

| ID | Description | Severity | ADR(s) | Recommendation |
|----|-------------|----------|--------|----------------|
| G-MEM-1 | Partition management not specified - `now()` evaluated once | High | ADR-0004 | Add scheduled partition manager |
| G-EXE-1 | LLM selection not decided (local vs cloud, which model) | High | ADR-0014 | Decide pre-MVP: recommend cloud for MVP |
| G-EXE-2 | Goal management undefined (where do goals come from?) | High | ADR-0014 | Defer goals to post-MVP |
| G-ACT-1 | Credential storage for integration tokens unspecified | High | ADR-0011 | Coordinate with ADR-0008 |

### 8.2 Medium-Severity Gaps

| ID | Description | Severity | ADR(s) | Status |
|----|-------------|----------|--------|--------|
| G-MEM-2 | Memory vs Audit query routing unspecified | Medium | ADR-0004, 0012 | Needs spec |
| G-MEM-3 | Embedding migration strategy when models change | Medium | ADR-0004 | Document approach |
| G-LRN-1 | System 1→2 escalation triggers underspecified | Medium | ADR-0010 | Can skip if S-LRN-6 adopted |
| G-SAL-1 | Deep evaluation trigger threshold not specified | Medium | ADR-0013 | Needs threshold |
| G-EXE-3 | Multi-turn conversation handling not specified | Medium | ADR-0014 | Defer to post-MVP |
| G-EXE-4 | Fallback behavior when LLM fails not specified | Medium | ADR-0014 | Needs spec |
| G-PER-1 | Mood persistence duration not specified | Medium | ADR-0015 | Document rules |
| G-ACT-2 | Gaming actuator (Aperture) fit unclear | Medium | ADR-0011 | Clarify strategy |

### 8.3 Contradictions

| ID | Description | ADRs Involved | Resolution |
|----|-------------|---------------|------------|
| C-001 | episode_id required vs optional | ADR-0009 vs ADR-0004 | Align: make optional with null allowed |
| C-002 | Personality trait names mismatch | ADR-0003 vs ADR-0015 | Update ADR-0003 manifest to match 0015 |
| C-003 | Trait range mismatch (0-1 vs -1 to +1) | ADR-0003 vs ADR-0015 | Update ADR-0003 to bipolar range |
| C-004 | ADR-0014 references ADR-0001 Section 9 for personality | ADR-0014 vs ADR-0015 | Update to reference ADR-0015 |

### 8.4 Underspecifications

| ID | Description | ADR | Impact |
|----|-------------|-----|--------|
| U-001 | Heuristic representation schema not defined | ADR-0010 | Blocks System 1 implementation |
| U-002 | Context detection algorithm (how detect "gaming"?) | ADR-0013 | Blocks context-aware salience |
| U-003 | Merkle tree implementation approach | ADR-0012 | Blocks audit_security table |
| U-004 | Audit event declaration in plugin manifest | ADR-0003, 0012 | Plugins can't declare events |

---

## 9. Executive Summary

**Status**: ✅ Complete (Session 1, 2026-01-19)

### 9.1 Feasibility Assessment

**Verdict**: ✅ **FEASIBLE** with significant MVP scope reduction

The GLADyS architecture is fundamentally sound. The brain-inspired design provides a coherent mental model, the polyglot approach leverages team strengths, and the local-first philosophy is well-integrated throughout. However, the full design is over-engineered for an MVP.

**Key Strengths**:
- Brain metaphor provides coherent component design
- Security posture is strong (local-first, fail-closed, defense-in-depth)
- Personality system is well-designed with good complexity decisions (Identity Model deferred)
- Infrastructure choices are solid (gRPC, PostgreSQL, Prometheus stack)

**Key Constraints**:
- RTX 2070 8GB limits concurrent model execution
- 1000ms latency budget is tight (815ms allocated in typical flow)
- Learning subsystem complexity exceeds MVP needs
- Memory schema is over-normalized (9 tables)

**Critical Dependencies**:
- LLM inference (dominates latency and GPU budget)
- PostgreSQL + pgvector (storage foundation)
- Home Assistant (actuator integration)

### 9.2 Performance Assessment

**Verdict**: 🟡 **ACHIEVABLE** with conversational (1000ms) latency profile

**Limiting Factors**:
1. **LLM inference**: 200-500ms local, 500-2000ms cloud API
2. **GPU contention**: Single 8GB GPU can't run multiple large models
3. **Realtime (500ms) profile**: Only 15ms slack - not reliable for MVP

**Recommended Hardware for MVP**:
- Current RTX 2070 8GB is sufficient with cloud LLM fallback
- Dual-GPU upgrade path for fully local v2

**Storage**: ~20GB/year is manageable on local storage

### 9.3 Top Recommendations

**Immediate (Before Implementation)**:

1. **Resolve LLM strategy** (G-EXE-1): Recommend cloud API (Claude/GPT-4) for MVP to offload GPU; add local LLM in v2
2. **Fix partition management** (G-MEM-1): Add scheduled partition manager - current design has a bug
3. **Reconcile ADR contradictions** (C-001 through C-004): Update ADR-0003 personality manifest, align episode_id semantics
4. **Resolve credential storage** (G-ACT-1): Coordinate ADR-0008 and ADR-0011

**MVP Scope Reduction**:

5. **Simplify Memory**: 4 tables (episodic_events, entities, user_profile, feedback_events); skip semantic_facts, learned_patterns, heuristics, episodes, episode_events
6. **Simplify Learning**: EWMA preference tracking + LLM only; skip System 1/2, skip 3 Bayesian models
7. **Proactive from start**: Proactive behavior is NON-NEGOTIABLE - GLADyS must initiate, not just respond
8. **Single context**: Skip cross-context salience routing; single active context

**Post-MVP**:

9. Add local LLM with GPU upgrade
10. Add System 1 heuristics if latency requires it
11. Add cross-context salience routing

### 9.4 Go/No-Go Decision

**Recommendation**: ✅ **GO** - Proceed to implementation with MVP scope

**Conditions for GO**:
1. Adopt recommended MVP simplifications (Section 7)
2. Resolve high-severity gaps before implementation (Section 8.1)
3. Reconcile ADR contradictions (Section 8.3)
4. Accept conversational (1000ms) latency as MVP target (not realtime 500ms)

**Risk Level**: Medium
- Core architecture is sound
- Complexity is manageable with MVP scope reduction
- No showstopper technical blockers identified

---

## 10. Use Case Analysis

**Added**: 2026-01-20 (from consolidated USE_CASES.md)

This section validates which architectural complexity is justified by the use cases.

### 10.1 ADR Coverage Matrix

Which ADRs are exercised by which use cases?

| ADR | Topic | UC-01 | UC-02 | UC-03 | UC-04 | UC-05 | UC-06 | UC-07 | UC-08 | UC-09 | UC-10 | UC-11 |
|-----|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| 0001 | Architecture | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| 0003 | Plugin Manifests | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| 0004 | Memory Schema | Yes | Yes | Partial | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| 0005 | gRPC Contracts | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| 0006 | Observability | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| 0007 | Adaptive Algorithms | **Yes** | **Yes** | Partial | Partial | **Yes** | Partial | Partial | Partial | Partial | Partial | Partial |
| 0008 | Security | Yes | Yes | Yes | Yes | Yes | **Yes** | Yes | Yes | **Yes** | Yes | Yes |
| 0009 | Memory Contracts | Yes | Yes | Partial | Partial | Yes | Yes | Partial | Partial | Partial | Partial | Yes |
| 0010 | Learning | **Yes** | **Yes** | **Yes** | Partial | **Yes** | Partial | Partial | Partial | Partial | Partial | Partial |
| 0011 | Actuators | - | - | - | - | **Yes** | **Yes** | **Yes** | Partial | - | **Yes** | - |
| 0012 | Audit | Yes | Yes | Yes | Yes | Yes | **Yes** | Yes | Yes | Yes | Yes | Yes |
| 0013 | Salience | **Yes** | **Yes** | Yes | Yes | Yes | **Yes** | Yes | Yes | Yes | Yes | Yes |
| 0014 | Executive | **Yes** | **Yes** | Yes | Yes | Yes | **Yes** | Yes | Yes | Yes | Yes | **Yes** |
| 0015 | Personality | **Yes** | **Yes** | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | **Yes** |

**Bold** = heavily exercised by this use case

### 10.2 Feature Complexity Validation

Which complex features are actually required by which use cases?

| Feature | UC-01 | UC-02 | UC-03 | UC-04 | UC-05 | UC-06 | Verdict |
|---------|-------|-------|-------|-------|-------|-------|---------|
| **Real-time latency** | **Yes** | **Yes** | - | - | - | **Yes** | MVP |
| **Actuator subsystem** | - | - | - | - | **Yes** | **Yes** | MVP |
| **EWMA preferences** | **Yes** | **Yes** | Yes | Yes | **Yes** | Yes | MVP |
| **Salience (5 dims)** | **Yes** | **Yes** | - | Yes | Yes | **Yes** | MVP |
| **Habituation** | **Yes** | Yes | - | Yes | - | Yes | MVP |
| **STT/TTS** | Yes | Yes | - | Yes | Yes | Yes | MVP |
| **Home Assistant integration** | - | - | - | **Yes** | **Yes** | **Yes** | MVP |
| **Security trust tier** | - | - | - | - | - | **Yes** | MVP |
| **DAG preprocessing** | Partial | Partial | - | Partial | - | Partial | MVP |
| **Proactive scheduling** | **Yes** | **Yes** | - | **Yes** | **Yes** | **Yes** | **MVP** |
| **Bayesian confidence** | Yes | Yes | Yes | - | Yes | - | Post-MVP |
| **System 1/2 escalation** | - | - | - | - | - | - | **Skip** |
| **9 salience dims** | - | - | - | - | - | - | **5 sufficient** |
| **semantic_facts table** | - | - | - | - | - | - | **Defer** |
| **learned_patterns table** | Yes | Yes | Yes | - | Yes | - | Post-MVP |
| **Cross-context routing** | - | - | - | - | - | - | Post-MVP |
| **Multi-user support** | - | - | - | - | - | - | Post-MVP |

### 10.3 Gaps Identified Per Use Case

| Use Case | Gap | Severity | Notes |
|----------|-----|----------|-------|
| UC-01 | Aperture API specification | High | Needed for first release |
| UC-01 | Game-specific knowledge | Medium | How does Executive know Minecraft? |
| UC-01 | Game actuator capability | Medium | For proactive actions (B2c, B2d, B3b) |
| UC-02 | RuneLite plugin details | Medium | Dependency on third-party |
| UC-03 | Sensor approach undecided | High | Multiple options, none validated |
| UC-04 | Motion false positive learning | Low | Can defer to post-MVP |
| UC-05 | Sensor threshold configuration | Medium | When is temperature "noteworthy"? |
| UC-05 | Skill input routing | Medium | How does analyzer get multi-sensor data? |
| UC-06 | Lock confirmation UX | High | Safety-critical, needs design |
| UC-09 | Email sensor plugin | Medium | Not in current plugin list |
| UC-10 | Power state sensor | Medium | Not explicitly specified |
| UC-11 | Wake word / VAD | High | Not specified in any ADR |

### 10.4 Design Validation Questions

Questions raised by use case analysis that need answers:

1. **UC-01/UC-02**: How does the Executive gain domain knowledge (Minecraft, RuneScape)? Options:
   - Pre-trained in the LLM
   - Knowledge skill plugins
   - RAG over game wikis
   - Hardcoded in game sensor

2. **UC-05**: How does a multi-sensor skill (Comfort Analyzer) receive inputs from multiple sensors?
   - Option A: Skill polls Memory for recent readings
   - Option B: Orchestrator routes matching events to skill
   - Option C: Skill subscribes to specific sensor topics

3. **UC-11**: What handles wake word detection and voice activity detection (VAD)?
   - Part of audio sensor?
   - Separate preprocessor?
   - External service?

4. **UC-06**: What's the confirmation UX for security-tier actuators?
   - Mobile push notification?
   - Voice challenge-response?
   - Multi-factor?

### 10.5 Implementation Priority (Informed by Use Cases)

| Priority | Use Case | Why |
|----------|----------|-----|
| 1 | UC-04: Doorbell | Validates core pipeline, minimal complexity |
| 2 | UC-11: Voice Interaction | Enables all other use cases |
| 3 | UC-01: Minecraft | Primary launch target, heavy ADR exercise |
| 4 | UC-05: Climate | Validates actuator model |
| 5 | UC-06: Security | High value but high risk, needs maturity |
| 6 | UC-02: RuneScape | Similar to UC-01, less urgent |
| 7 | UC-07: Lighting | Simple actuator validation |
| 8 | UC-08: Appliances | Depends on device support |
| 9 | UC-09: Email | Requires new sensor type |
| 10 | UC-10: Power Recovery | Niche but valuable |
| 11 | UC-03: Evony | Speculative, technical challenges |

### 10.6 UC-to-ADR Trace (Selected Use Cases)

#### UC-01: Minecraft Companion

| Step | ADR | Section | Coverage |
|------|-----|---------|----------|
| Aperture sensor | ADR-0003 | §3.1 | Sensor plugin |
| Combat preprocessing | ADR-0003 | §3.2 | Preprocessor skill |
| Salience (threat dim) | ADR-0013 | §3.2 | threat dimension |
| Habituation | ADR-0013 | §3.4 | Exponential decay |
| Memory storage | ADR-0004 | §5.1 | episodic_events |
| Executive decision | ADR-0014 | §3 | Full decision framework |
| Personality filter | ADR-0015 | §3 | Response Model traits |
| TTS output | ADR-0003 | §3.4 | Output plugin |
| Preference learning | ADR-0007 | §3 | EWMA tracking |
| Proactive scheduling | ADR-0014 | §7 | Opportunity detection |

#### UC-04: Doorbell & Visitor Detection

| Step | ADR | Section | Coverage |
|------|-----|---------|----------|
| HA receives event | ADR-0003, ADR-0011 | §4 | Integration plugin model |
| Event to orchestrator | ADR-0005 | §3.2 | gRPC pub/sub |
| Salience evaluation | ADR-0013 | §3.1 | Heuristic eval sufficient |
| Memory storage | ADR-0004 | §5.1 | episodic_events |
| Executive decision | ADR-0014 | §3 | Simple routing |
| Desktop notification | ADR-0003 | §3.4 | Output plugin |
| Audit logging | ADR-0012 | §3.2 | audit_actions |
| Proactive detection | ADR-0014 | §7 | Motion-triggered |

#### UC-05: Climate Control

| Step | ADR | Section | Coverage |
|------|-----|---------|----------|
| HA sensors | ADR-0011 | §4 | Integration plugin |
| Comfort analyzer | ADR-0003 | §3.2 | Analyzer skill |
| Salience | ADR-0013 | §3 | Low salience for routine |
| Executive decision | ADR-0014 | §3 | Decide speak vs actuate |
| Thermostat actuator | ADR-0011 | §3 | Trust tier: comfort |
| Rate limiting | ADR-0011 | §3.4 | 1/minute max |
| Preference learning | ADR-0007 | §3 | Temperature preferences |

#### UC-06: Security Monitoring

| Step | ADR | Section | Coverage |
|------|-----|---------|----------|
| Motion sensors | ADR-0011 | §4 | Via HA integration |
| Person detection | ADR-0003 | §3.2 | Preprocessor |
| Threat salience | ADR-0013 | §3.2 | threat dimension high |
| Memory storage | ADR-0004 | §5.1 | episodic_events |
| Executive decision | ADR-0014 | §3 | Alert + optional action |
| Lock actuator | ADR-0011 | §3 | Trust tier: security |
| Confirmation | ADR-0011 | §3.5 | confirmation_required |
| Audit (Merkle) | ADR-0012 | §3.1 | audit_security table |

#### UC-11: Voice Interaction

| Step | ADR | Section | Coverage |
|------|-----|---------|----------|
| Audio capture | ADR-0003 | §3.1 | **Gap**: microphone sensor |
| Wake word | - | - | **Gap**: not specified |
| STT | ADR-0003 | §3.2 | Preprocessor |
| Salience | ADR-0013 | §3 | User speech = high |
| Executive | ADR-0014 | §3 | Full decision loop |
| Personality | ADR-0015 | §3 | Response Model |
| TTS | ADR-0003 | §3.4 | Output plugin |

---

## 11. Session Log

| Date | Session | ADRs Reviewed | Key Findings | Reviewer |
|------|---------|---------------|--------------|----------|
| 2026-01-19 | Setup | None | Created review framework | Claude |
| 2026-01-19 | 1 | All 15 ADRs | See executive summary; Memory and Learning over-engineered; Personality well-designed; 4 high-severity gaps; 4 contradictions | Claude |
| 2026-01-20 | 2 | None (UC focus) | Proactive is MVP-required (S-EXE-6 REJECTED); USE_CASES.md consolidated; Scott's UCs assessed; Analysis content migrated to this doc | Claude |

---

## Appendix: Review Notes

### A.1 ADRs by Complexity Concern

**High complexity (needs simplification):**
- ADR-0004 (Memory): 9 tables, 5 tiers, 6 background jobs
- ADR-0010 (Learning): 6 subsystems, 3 Bayesian models
- ADR-0007 (Adaptive): EWMA + Bayesian + gradient descent overlay

**Medium complexity (acceptable with minor simplification):**
- ADR-0013 (Salience): 9 dimensions reducible to 5
- ADR-0014 (Executive): 7 traits, 6 response types, proactive scheduling - all MVP-required

**Appropriate complexity:**
- ADR-0015 (Personality): Well-designed, Identity Model correctly deferred
- ADR-0011 (Actuator): Trust tiers, rate limiting appropriate
- ADR-0012 (Audit): Tiered integrity appropriate for risk profile
- ADR-0001, 0005, 0006, 0008: Infrastructure is solid

### A.2 Quick Reference: MVP vs Full

| What to build for MVP | What to defer |
|----------------------|---------------|
| episodic_events, entities, user_profile, feedback_events | semantic_facts, learned_patterns, heuristics, episodes, episode_events |
| L0 (context) + L3 (PostgreSQL) | L1 (cache), L2 (buffer), L4 (archive) |
| EWMA preference tracking | Bayesian confidence, System 1/2, Causal Modeler |
| 5 salience dimensions | 9 dimensions, deep evaluation |
| **Proactive + Reactive responses** | Cross-context routing |
| Cloud LLM API | Local LLM |
| Home Assistant only | Google Home, Amazon Alexa |
| SecUnit personality pack | Personality marketplace |
