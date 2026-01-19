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

### 3.11 Risk Tolerance

Risk tolerance is **user configuration**, NOT learned:

```yaml
risk_tolerance: 0.5  # 0 = conservative, 1 = aggressive
```

Rationale: User may want AI to compensate for their own tendencies (risk-averse person wants proactive AI, or vice versa).

### 3.12 Config vs Behavior Conflict

When learned behavior conflicts with explicit configuration:
1. Flag conflict to user once
2. Respect configuration
3. Don't nag repeatedly

Example: User configures "always suggest X" but consistently rejects X → notify once, then follow config.

### 3.13 Design Principles

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
