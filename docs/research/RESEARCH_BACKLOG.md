# Research Backlog

Literature research tasks we can do ourselves. Each item has a clear question, what to look up, and where to apply the answer.

These are **not** open research questions — they're questions with likely answers in existing literature. We just haven't done the reading yet.

---

## Table of Contents

- [Habituation and Sensory Adaptation](#habituation-and-sensory-adaptation)
- [Bayesian Confidence and Staleness](#bayesian-confidence-and-staleness)
- [Experience Replay](#experience-replay)
- [Salience Reduction Methods](#salience-reduction-methods)
- [Graded Outcome Models](#graded-outcome-models)
- [TD Learning Convergence](#td-learning-convergence)

---

## Habituation and Sensory Adaptation

### What properties does biological habituation have that we're not modeling?

**What to look up**: Psychology literature on habituation (Thompson & Spencer, 1966 is the classic). Specifically:
- **Dishabituation**: A novel stimulus restores sensitivity to a habituated stimulus. We don't model this — should we?
- **Sensitization**: Intense stimuli can *increase* sensitivity. Our model only decays.
- **Stimulus specificity**: Habituation is highly specific to the exact stimulus. Our pattern matching via embeddings may be too broad — similar events habituate together when they shouldn't.

**Where to apply**: ADR-0013 Section 12, habituation decay formula in salience gateway.

**Current implementation**: Exponential decay with configurable tau per domain. Minimum sensitivity floor of 10%.

---

## Bayesian Confidence and Staleness

### What's the principled approach to confidence decay for stale beliefs?

**What to look up**: Bayesian literature on belief decay under missing data. Specifically:
- Is there a conjugate prior model that naturally handles "no observations" differently from "negative observations"?
- How do Bayesian filtering approaches (Kalman filters, particle filters) handle measurement dropout?
- Is there a formal distinction between "dormant but valid" and "stale and unreliable" in the Bayesian framework?

**Where to apply**: ADR-0010 Section 3.3.4, `learned_patterns.expected_period`, staleness heuristic.

**Current implementation**: Staleness detection based on expected observation frequency. Decay triggers when pattern is >3 standard deviations overdue.

---

## Experience Replay

### Should we use prioritized replay, and what's the optimal replay window?

**What to look up**: Schaul et al. (2015) "Prioritized Experience Replay" — this likely answers the prioritized vs FIFO question directly. Also:
- What does the neuroscience literature say about optimal replay timing? Is 72 hours (our current window) supported by evidence?
- Does replay frequency matter more than replay window length?
- Should high-surprise events be replayed more often than routine ones?

**Where to apply**: Sleep cycle implementation, experience replay queue.

**Current implementation**: FIFO replay within 72-hour window during idle time.

---

## Salience Reduction Methods

### What does the attention literature say about reducing multi-dimensional salience to a comparable value?

**What to look up**: Attention and salience literature for reduction methods beyond weighted sum:
- Are dimensions in attentional models typically orthogonal or correlated? Factor analysis results from empirical salience studies.
- L2 norm, max-across-dimensions, learned projection — what's used in practice?
- Multi-criteria decision making literature (MCDM) — how do they handle non-compensatory criteria?

**Where to apply**: ADR-0013 Section 5.2, salience gateway priority scoring.

**Current implementation**: Context-specific weighted sum. Gaming amplifies threat; home amplifies novelty.

---

## Graded Outcome Models

### What's the right model for partial success in learning?

**What to look up**: RL and Bayesian literature on graded/continuous outcomes:
- Beta-Binomial handles binary success/failure. What handles "mostly worked"?
- Are there conjugate prior models for bounded continuous outcomes?
- How do bandit algorithms handle continuous reward signals?

**Where to apply**: TD learning confidence updates, outcome evaluation.

**Current implementation**: Binary feedback (thumbs up/down). Graded outcomes are a post-PoC goal.

---

## TD Learning Convergence

### What are the theoretical bounds on learning curve shape for heuristic-based systems?

**What to look up**: RL convergence literature, specifically for tabular/case-based systems:
- How many interactions before a case-based system reaches X% coverage of a bounded domain?
- Does the learning curve follow a power law, exponential, or logarithmic shape?
- What's the relationship between domain complexity (number of distinct situations) and convergence rate?

**Where to apply**: Monitoring metrics, PoC success criteria for learning effectiveness.

**Current implementation**: No formal model — we measure S1 hit rate empirically.