# ADR-0010: Learning and Inference

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Date** | 2026-01-18 |
| **Owner** | Mike Mulcahy (Divinity10), Scott (scottcm) |
| **Contributors** | |
| **Module** | Intelligence |
| **Tags** | learning, inference, bayesian, decay, patterns |
| **Depends On** | ADR-0001, ADR-0004, ADR-0007, ADR-0009 |

---

## 1. Context and Problem Statement

ADR-0007 covers learning *user preferences* via EWMA and Bayesian confidence. ADR-0009 covers *storing* episodic and semantic memory. Neither specifies:

- How semantic facts are *derived* from episodic data
- The learning pipeline: observation → pattern → belief
- Confidence decay over time for learned facts
- Environment change detection (concept drift)
- Different learning/decay strategies for different knowledge types

This ADR defines the learning and inference subsystem.

---

## 2. Decision Drivers

1. **Generalization**: Learn patterns from specific observations
2. **Adaptation**: Update beliefs when environment changes
3. **Stability**: Don't oscillate or overfit to noise
4. **Effectiveness**: System serves user; effectiveness over explainability
5. **Observability**: User can see current beliefs
6. **Correctability**: User can fix wrong beliefs
7. **Efficiency**: Learning shouldn't consume excessive resources
8. **Strategy flexibility**: Different memory types need different algorithms

---

## 3. Decision

### 3.1 Dual-Process Architecture (Kahneman-Inspired)

GLADyS uses a dual-process model inspired by Kahneman's System 1/System 2:

| System | Speed | Characteristics | When Used |
|--------|-------|-----------------|-----------|
| **System 1** | Fast | Heuristics, pattern matching, can short-circuit LLM | Familiar situations, high confidence |
| **System 2** | Slow | LLM deliberation, complex reasoning | Novel situations, low confidence, high stakes |

**Escalation triggers** (System 1 → System 2):
- Novelty detected ("Have I seen this before?" = no)
- Low confidence on available heuristics
- Conflicting heuristics suggest different actions
- High-stakes decision (security tier, safety-critical)

### 3.2 Learning Subsystems

GLADyS uses Complementary Learning Systems - multiple specialized subsystems rather than a monolithic learner:

| Subsystem | Role | Speed | Implementation |
|-----------|------|-------|----------------|
| **Heuristic Store** | Fast rules (learned + defined) | System 1 | Rule database with confidence scores |
| **Novelty Detector** | "Have I seen this before?" | System 1 | Embedding similarity to known patterns |
| **Episodic Store** | Raw event storage | Storage | Per ADR-0009 |
| **Pattern Detector** | Extract rules from episodes | System 2 (background) | Batch analysis during sleep mode |
| **Preference Tracker** | EWMA for likes/dislikes | System 1 | Per ADR-0007 |
| **Causal Modeler** | X causes Y beliefs | System 2 (background) | Correlation/causation analysis |
| **Executive (LLM)** | Deliberate reasoning | System 2 (on-demand) | When escalation triggered |

### 3.3 Bayesian Belief Models

Learned patterns are stored with Bayesian models that track uncertainty and update with new evidence.

#### 3.3.1 Strategy Pattern

Each pattern stores:
- `model_type`: Which Bayesian model to use
- `params`: Model-specific parameters (priors, observed counts, etc.)
- `last_observed`: Timestamp of last observation
- `observation_count`: Total observations
- `context_tags`: Optional context identifiers

Model is auto-selected from data shape, with explicit override available.

#### 3.3.2 MVP Models (All Required from Day 1)

| Model | Data Shape | Use Case | Parameters |
|-------|------------|----------|------------|
| **Beta-Binomial** | Binary outcomes | "Did user accept suggestion?" | α, β (pseudo-counts) |
| **Normal-Gamma** | Continuous values | "Preferred temperature" | μ, κ, α, β |
| **Gamma-Poisson** | Rate/count data | "Gathering completion rate" | α, β (shape, rate) |

**Dirichlet** (categorical) deferred - can be approximated with multiple Beta-Binomials initially.

#### 3.3.3 Model Selection

```yaml
# Auto-selection rules
data_shape:
  binary: Beta-Binomial
  continuous: Normal-Gamma
  count_or_rate: Gamma-Poisson
  categorical: Beta-Binomial[]  # Multiple binomials until Dirichlet implemented

# Explicit override
pattern:
  id: user_temperature_preference
  model_override: Normal-Gamma  # Force this model even if data looks different
```

#### 3.3.4 Staleness Detection

Patterns have an expected observation frequency. Staleness indicates how overdue an observation is:

```
staleness = (time_since_last - expected_period) / std_dev(period)
```

- `staleness < 1`: Normal, on schedule
- `staleness 1-2`: Slightly overdue, may need verification
- `staleness > 3`: Significantly stale, reduce confidence

High staleness triggers confidence decay (pattern may no longer be valid).

### 3.4 Conflicting Evidence Handling

When new evidence contradicts existing beliefs:

#### 3.4.1 Default: Bayesian Update

Conjugate priors naturally resist over-correction:
- Prior strength acts as "effective sample size"
- A strong prior (high pseudo-counts) barely moves on single observation
- Weak prior adapts quickly

#### 3.4.2 Context-Aware Updates

Before updating, check if context differs from stored pattern:
- If context is detectably different (guests present, weekend, etc.), store as separate context-specific belief
- If context matches, apply Bayesian update to main belief

#### 3.4.3 Regularization

Optional regularization parameter caps maximum belief shift per update:

```yaml
conflicting_evidence:
  prior_strength: moderate   # weak/moderate/strong
  regularization: 0.1        # 0 = disabled, higher = more resistant
  belief_propagation: false  # Deferred - design schema supports it
```

**Belief propagation** (Bayesian networks) is deferred - schema designed to support edges between beliefs, implementation when needed.

### 3.5 Learning Profiles

Hierarchical configuration allows per-domain tuning:

```yaml
learning:
  global:
    learning_rate: 0.5       # How quickly to update beliefs
    proactivity: 0.5         # How eager to act on uncertain beliefs
    action_threshold: 0.6    # Minimum confidence to act without asking

  domains:
    gaming:
      learning_rate: 0.8     # Faster adaptation for dynamic environment
      proactivity: 0.7       # More willing to offer suggestions
    home_automation:
      learning_rate: 0.3     # Slower, more stable
      action_threshold: 0.8  # Higher bar for autonomous action

  self_tuning:
    enabled: false           # Auto-adjust parameters
    suggest_only: true       # If enabled, suggest changes for user approval
    bounds:
      learning_rate: [0.1, 0.9]
      proactivity: [0.2, 0.8]
```

### 3.6 Meta-Learning (Self-Tuning)

System can track learning effectiveness metrics and propose parameter adjustments:

| Mode | Behavior |
|------|----------|
| **Disabled** (default) | User sets parameters manually |
| **Suggest-only** | System proposes changes, user must approve |
| **Auto** (within bounds) | System adjusts within configured bounds |

Metrics tracked:
- Prediction accuracy (did belief match outcome?)
- User correction rate (how often does user override?)
- Staleness distribution (are patterns staying current?)

### 3.7 Online vs Batch Learning

Hybrid model matching dual-process architecture:

| Processing Mode | Subsystems | When |
|-----------------|------------|------|
| **Online** (realtime) | Heuristic evaluation, Preference Tracker, Novelty Detector | Always active |
| **Background** (active mode) | Light pattern matching, simple updates | 5-10% CPU budget |
| **Batch** (sleep mode) | Pattern Detector, Causal Modeler, embedding generation | ~80% resources during idle |

**Sleep mode** activates when:
- User idle for configurable duration (default: 30 minutes)
- System load is low
- Sufficient episodic data accumulated since last batch

### 3.8 Cold Start Bootstrapping

New user with no data:

1. **Conservative defaults**: System asks before acting until confidence builds
2. **Template selection**: User picks personality template (e.g., "proactive assistant", "quiet helper")
3. **Optional onboarding**: Interview questions to seed initial preferences (per ADR-0007)
4. **No population defaults**: Privacy-first; no "users like you" bootstrapping

### 3.9 Computational Budget

User-configurable with reasonable defaults:

| Mode | Resource Budget | Rationale |
|------|-----------------|-----------|
| **Active** | 5-10% background | Don't compete with user's primary task |
| **Sleep** | ~80% | Leave headroom for wake events |
| **Minimum daily** | 1 hour | Warn if not hit; learning degrades gracefully |

Priority order: `realtime` > `conversational` > `comfort` > `background` > `learning`

**Workload distribution**:
- **GPU**: Pattern detection on large datasets, embedding generation
- **CPU**: Bayesian updates, heuristic evaluation, lightweight inference

### 3.10 Punishment Detection

System detects negative feedback through behavioral signals only (no emotion inference):

| Signal | Weight | Description |
|--------|--------|-------------|
| Explicit negative feedback | 1.0 | User says "no", "wrong", "stop" |
| Action undone within 60s | 0.8 | User immediately reverses GLADyS action |
| Suggestion ignored 3+ times | 0.3 | Consecutive ignores of same suggestion type |

**Explicitly disabled**: Tone/emotion analysis (unreliable, invasive per design philosophy)

Punishment adjusts confidence on the specific heuristic that led to the action, NOT global risk tolerance.

### 3.11 Outcome Evaluation (Reward Shaping)

**Status**: MVP Required

Domain-specific outcome evaluation is provided by **Packs**, not core system. This is reward shaping from reinforcement learning.

#### 3.11.1 Design Pattern

```
Pack provides: OutcomeEvaluator implementation
Core provides: Queue decisions, wait for signals, update based on comparison
```

The core system does NOT know what "good" or "bad" means in any domain. Packs define this through OutcomeEvaluator:

```yaml
# Pack manifest includes outcome_evaluator
pack:
  id: minecraft-companion
  outcome_evaluator:
    skill_type: outcome_evaluator
    signals:
      - event: player_death
        outcome: negative
        magnitude: 1.0
      - event: player_damage
        outcome: negative
        magnitude: 0.3
      - event: item_acquired
        outcome: positive
        magnitude: 0.1
      - event: level_up
        outcome: positive
        magnitude: 0.5
```

#### 3.11.2 Core System Responsibilities

1. **Queue** decisions with context (what triggered, what S1 decided, confidence)
2. **Wait** for outcome signals from sensors (game events, user feedback)
3. **Correlate** decisions to outcomes within a time window
4. **Update** heuristic confidence based on outcome evaluator scoring
5. **Log** for audit trail

#### 3.11.3 Rationale

This separates concerns cleanly:
- Core: Generic learning machinery
- Packs: Domain-specific reward knowledge

A home automation pack knows "user manually adjusts thermostat after GLADyS change = negative outcome."
A gaming pack knows "player death within 10 seconds of ignoring warning = GLADyS was right."

### 3.12 Deferred Validation Queue (Experience Replay)

**Status**: MVP Required

System 1 decisions are queued for LLM validation during idle time. This is **experience replay** from reinforcement learning.

#### 3.12.1 Motivation

- S1 makes fast decisions (<5ms) that may be wrong
- Immediate LLM validation is expensive (200-500ms)
- Local LLM = no per-query cost, but latency still matters
- Solution: Queue S1 decisions, validate in batch during sleep mode

#### 3.12.2 Three-Way Comparison

For each deferred decision:

| Component | Value | Timing |
|-----------|-------|--------|
| **S1 Decision** | What System 1 chose | Real-time |
| **LLM Decision** | What System 2 would choose | Deferred validation |
| **Actual Outcome** | What happened | From OutcomeEvaluator |

Learning signals:
- S1 = LLM = Good outcome: S1 heuristic reinforced
- S1 ≠ LLM, LLM = Good outcome: S1 heuristic needs correction
- S1 = LLM = Bad outcome: Both need calibration (rare edge case)
- S1 ≠ LLM, S1 = Good outcome: S1 heuristic may be better than LLM for this case

#### 3.12.3 Queue Structure (MVP)

Simple FIFO queue with configurable max size:

```yaml
deferred_validation:
  enabled: true
  max_queue_size: 1000
  retention_hours: 72  # Drop unvalidated decisions after this
  priority: fifo       # Post-MVP: prioritized replay
```

#### 3.12.4 Biological Inspiration

This mirrors **hippocampal replay during sleep** - the brain replays recent experiences during sleep to consolidate learning. GLADyS does the same during sleep mode.

### 3.13 RL-Inspired Techniques

Classification by implementation priority and triggers for when to add sophistication.

#### 3.13.1 MVP Required

| Technique | Implementation | Rationale |
|-----------|----------------|-----------|
| **Outcome Evaluator** | Pack-provided callbacks | Core learning needs domain signals |
| **Deferred Queue** | Simple FIFO | Experience replay is fundamental |
| **Context-dependent rates** | Per-domain learning_rate (§3.5) | Already designed |

#### 3.13.2 Post-MVP (Implement When Metrics Indicate)

| Technique | Description | Trigger Metric | Monitoring |
|-----------|-------------|----------------|------------|
| **Prioritized Replay** | Replay surprising events more often | S1 accuracy < 70% in domain after 1000+ decisions | Track accuracy per domain |
| **Prediction Error** | Adjust confidence based on expected vs actual | Confidence calibration error > 0.2 | Compare predicted vs actual outcome rates |
| **Exploration Epsilon** | Random S1 bypass to prevent local optima | S1 decision diversity < threshold | Track unique decisions per context |
| **Hebbian Association** | "Fire together, wire together" pattern discovery | Users frequently ask "how did you know?" | Track explanation queries |

#### 3.13.3 Deferred (Not Planned for Near-Term)

| Technique | Description | Why Deferred |
|-----------|-------------|--------------|
| **Eligibility Traces** | Credit assignment for multi-step sequences | Adds hot-path complexity; implement if multi-step credit is problematic |
| **Full TD(λ)** | Temporal difference with eligibility | Overkill for current scope |

#### 3.13.4 Implementation Notes

**All Post-MVP techniques have zero hot-path cost** - they run during sleep mode batch processing only.

**Prioritized Replay** changes queue from FIFO to priority queue ordered by TD-error magnitude (difference between predicted and actual outcome).

**Exploration Epsilon** adds a small probability (e.g., 5%) that S1 is bypassed even when confident, allowing discovery of better heuristics. User-configurable with default off.

### 3.14 Fine-Tuning Strategy

**Status**: Post-MVP, requires Leah input

In addition to online learning (EWMA + Bayesian), GLADyS may use periodic fine-tuning of the underlying LLM:

| Learning Type | Scope | Timing | What Changes |
|---------------|-------|--------|--------------|
| **EWMA + Bayesian** | Per-user | Online | Preference weights in memory |
| **Fine-tuning** | Global | Batch | Model weights |

#### 3.14.1 Fine-Tuning Use Cases

- Personality calibration (global response styles)
- Domain knowledge updates (new game mechanics)
- Pack-specific adaptations

#### 3.14.2 Relationship to Online Learning

Fine-tuning and online learning are **complementary**, not either/or:
- Fine-tuning updates the model's base capabilities
- Online learning personalizes for individual users
- RAG provides user-specific context at inference time

#### 3.14.3 Open Questions

1. What triggers fine-tuning runs? (Data volume, performance degradation, scheduled)
2. How to prevent catastrophic forgetting?
3. Hosting considerations for open-source models (GPT-OSS 20B/120B)

### 3.15 Implementation Language

**Status**: Design decision

The learning subsystem has two layers:

| Layer | Language | Rationale |
|-------|----------|-----------|
| **Fast Path** | Rust | Novelty detection, heuristic matching, L0 cache - called on every event |
| **Storage Path** | Python | PostgreSQL queries, embedding generation - I/O bound |

This matches the System 1 / System 2 split:
- Rust handles the hot path where latency matters (<5ms target)
- Python handles the slower path where I/O dominates anyway

### 3.16 Risk Tolerance

Risk tolerance has **two components**:

```yaml
risk_tolerance:
  configured: 0.5     # User's stated preference (0 = conservative, 1 = aggressive)
  observed: null      # Learned from behavior (null until sufficient data)
  weight_observed: 0.7  # How much to trust observed vs configured
```

#### 3.16.1 Rationale

People lie and misunderstand themselves. A user who says "I'm risk-tolerant" but consistently rejects proactive suggestions reveals a different preference through behavior. **Revealed preference trumps stated preference** (per design philosophy).

#### 3.16.2 Learning Risk Tolerance

Observed risk tolerance is inferred from:
- Acceptance rate of uncertain suggestions
- Time-to-override for GLADyS actions
- Explicit feedback patterns
- Domain-specific variation (may be risk-seeking in gaming, risk-averse in home automation)

#### 3.16.3 Conflict Resolution

When configured and observed diverge significantly:
1. Flag to user once: "Your stated preference is X but your behavior suggests Y"
2. Offer to update configured value
3. If user maintains configured value, respect it (they may want GLADyS to compensate for their tendencies)
4. Continue tracking observed value for future reference

#### 3.16.4 Cold Start

Until sufficient behavioral data exists (`observed: null`), use `configured` value only. This is why template selection during onboarding matters - it sets reasonable defaults until learning kicks in.

### 3.17 Config vs Behavior Conflict

When learned behavior conflicts with explicit configuration:
1. Flag conflict to user once
2. Respect configuration
3. Don't nag repeatedly

Example: User configures "always suggest X" but consistently rejects X → notify once, then follow config.

### 3.18 Implementation Monitoring

Metrics to track for triggering Post-MVP enhancements.

#### 3.18.1 Core Metrics (MVP)

| Metric | Description | Storage |
|--------|-------------|---------|
| `s1_accuracy_by_domain` | % of S1 decisions validated correct by LLM | Per-domain counter |
| `s1_confidence_calibration` | Correlation between S1 confidence and actual correctness | Rolling histogram |
| `decision_diversity` | Unique S1 decisions per context type | Per-context set |
| `outcome_rate_by_heuristic` | Success rate for each learned heuristic | Per-heuristic counter |

#### 3.18.2 Triggering Sophistication

| Metric Threshold | Triggered Enhancement | Rationale |
|------------------|----------------------|-----------|
| `s1_accuracy < 70%` after 1000 decisions | Prioritized Replay | S1 is making too many mistakes; need smarter replay |
| `calibration_error > 0.2` | Prediction Error Calibration | S1 is over/under confident |
| `diversity_ratio < 0.1` | Exploration Epsilon | S1 is stuck in local optima |
| `explanation_query_rate > 0.05` | Hebbian Association | Users frequently ask how GLADyS knew something |

#### 3.18.3 Dashboard Queries

These metrics should be exposed in observability dashboards (per ADR-0006):

```sql
-- S1 accuracy by domain (last 7 days)
SELECT domain,
       COUNT(*) FILTER (WHERE s1_correct) * 100.0 / COUNT(*) as accuracy
FROM deferred_validation_results
WHERE validated_at > NOW() - INTERVAL '7 days'
GROUP BY domain;

-- Confidence calibration
SELECT confidence_bucket,
       AVG(CASE WHEN correct THEN 1.0 ELSE 0.0 END) as actual_accuracy
FROM deferred_validation_results
GROUP BY FLOOR(s1_confidence * 10) / 10.0 as confidence_bucket;
```

### 3.19 Design Principles

| Principle | Implication |
|-----------|-------------|
| **Black box OK** | Neural/opaque methods acceptable where appropriate |
| **Revealed preference** | Learn from behavior, not stated preferences |
| **Effectiveness > explainability** | System serves user, doesn't justify itself |
| **Observability required** | User can see current beliefs (but doesn't have to) |
| **Correctability required** | User can fix wrong beliefs |

---

## 4. Open Questions

*Resolved questions moved to Section 3.*

### Remaining

1. **Heuristic representation**: Exact schema for stored heuristics (rule format, conditions, actions)
2. **Novelty threshold**: What embedding distance counts as "novel"?
3. **Pattern promotion**: When does a pattern graduate from episodic observation to semantic belief?
4. **Causal vs correlational**: Specific algorithms for distinguishing causation from correlation
5. **Belief visualization**: How does user inspect current beliefs? (UI concern)
6. **Multi-user households**: Whose preferences win? Per-user profiles? Household consensus?
7. **Fine-tuning triggers**: What triggers fine-tuning runs? (Data volume, performance degradation, scheduled) - requires Leah input
8. **Catastrophic forgetting**: How to prevent fine-tuning from degrading existing capabilities?
9. **Model hosting**: Infrastructure for GPT-OSS 20B/120B fine-tuning and deployment
10. **Outcome correlation window**: How long to wait for outcome signals after a decision? (Domain-specific?)
11. **Deferred queue overflow**: What happens when validation backlog exceeds queue size?

---

## 5. Consequences

### Positive

1. **Adaptive**: System improves with use without explicit training
2. **Principled uncertainty**: Bayesian models provide meaningful confidence intervals
3. **Stable**: Prior strength and regularization prevent wild swings
4. **Efficient**: Dual-process avoids LLM calls for familiar situations
5. **User control**: Hierarchical profiles and meta-learning keep user in charge
6. **Privacy-preserving**: No population data, no emotion inference

### Negative

1. **Complexity**: Multiple subsystems to implement and coordinate
2. **Cold start UX**: New users get conservative, less impressive experience
3. **Debugging difficulty**: Learned behavior harder to explain than explicit rules
4. **Storage overhead**: Per-pattern Bayesian parameters add storage requirements

### Risks

1. **Feedback loops**: System learns from its own suggestions → potential for reinforcement of bad patterns
2. **Context confusion**: Incorrectly attributing behavior to wrong context
3. **Sleep mode dependency**: If system never goes idle, batch learning never runs
4. **Staleness accumulation**: Patterns become outdated faster than system can verify
5. **User trust calibration**: Users may over-trust or under-trust system confidence

---

## 6. Related Decisions

- ADR-0007: Adaptive Algorithms (user preference learning via EWMA)
- ADR-0009: Memory Contracts (episodic storage layer)
- ADR-0011: Actuator Subsystem (learns from action outcomes)
- ADR-0012: Audit Logging (source data for learning analysis)

---

## 7. References

### Use Cases

This ADR supports the following use cases (see [USE_CASES.md](../design/USE_CASES.md)):

| Use Case | Learning Relevance |
|----------|-------------------|
| UC-02: Minecraft | All 3 Bayesian models; System 1 for combat warnings |
| UC-03: RuneScape | Rate learning (Gamma-Poisson) for XP tracking |
| UC-04: Evony | Pattern learning for gathering cycles |
| UC-05: Climate | Temperature preferences (Normal-Gamma) |
| UC-06: Security | Anomaly detection via Novelty Detector |

### Bayesian Model Cheat Sheet

**Beta-Binomial** (binary):
- Prior: Beta(α, β) where α = pseudo-successes, β = pseudo-failures
- Update: α' = α + successes, β' = β + failures
- Mean: α / (α + β)

**Normal-Gamma** (continuous):
- Prior: Normal-Gamma(μ, κ, α, β)
- Tracks mean and precision (inverse variance)
- Update: standard conjugate formulas

**Gamma-Poisson** (rates):
- Prior: Gamma(α, β) for rate parameter λ
- Update: α' = α + Σcounts, β' = β + n (observations)
- Mean rate: α / β
