# Theoretical Foundations

GLADyS draws from neuroscience, cognitive science, and reinforcement learning to build an AI assistant that genuinely learns from experience — not just retrieves past conversations.

This document explains the theoretical basis, how we operationalize it, and where we need expert input. If you have background in any of these areas and see something wrong or improvable, we want to hear from you.

## Guiding Principles

**GLADyS is inspired by neuroscience, not a model of the brain.**

We borrow concepts — dual-process cognition, memory consolidation, salience networks, prediction error learning — because they solve real engineering problems. We don't borrow them because we're trying to simulate biology. If a simpler non-biological approach works better for a given problem, we use that instead.

The test for adopting a brain-inspired mechanism: does it concretely improve learning quality, response appropriateness, routing accuracy, or system performance? If not, it's intellectually interesting but not useful to us.

**GLADyS optimizes for correctness, not user comfort.**

The system should make the *right* prediction and take the *right* action, measured by expected value and outcome accuracy — not by whether the user liked the result. A correct warning that gets ignored is a success (the heuristic was right). A pleasant response based on a wrong prediction is a failure (the heuristic was wrong).

This is a deliberate departure from how the brain works. Human cognition is riddled with well-documented biases — loss aversion, confirmation bias, anchoring, status quo bias — that distort decision-making in predictable ways. Faithfully reproducing the brain's architecture risks reproducing these failure modes. We prefer approaches that **structurally avoid** cognitive biases rather than approaches that reproduce them and then try to filter them out.

In practice, this means:
- **Expected value over prospect theory**: Heuristic selection should use E(X) = probability × magnitude, not human-like loss aversion where losses loom larger than equivalent gains
- **Prediction accuracy over user agreement**: The learning signal is "was the prediction correct?" not "did the user like it?" A user override means intent disagreement, not heuristic failure
- **Bayesian updating over anchoring**: Beliefs update proportionally to evidence, not disproportionately anchored to first observations
- **Evidence-proportional confidence over confirmation bias**: Contradicting evidence reduces confidence as much as confirming evidence increases it — no asymmetric weighting

## The Core Idea

Most AI assistants are stateless: every interaction starts from scratch (or from retrieved context). GLADyS is different. It builds **behavioral heuristics** from experience — fast rules that let it act without consulting an LLM for familiar situations.

The key question: **Can a system learn reliable behavioral heuristics from minimal, noisy human feedback?**

## Dual-Process Cognition (Kahneman)

GLADyS uses a dual-process model inspired by Daniel Kahneman's *Thinking, Fast and Slow*:

| | System 1 (Fast) | System 2 (Slow) |
|---|---|---|
| **In the brain** | Intuition, pattern recognition | Deliberate reasoning |
| **In GLADyS** | Heuristic matching via embeddings | LLM inference |
| **Speed** | <20ms | 200-2000ms |
| **When used** | Familiar situations, high confidence | Novel situations, low confidence |

**How it works in practice:**

```
Event arrives (e.g., "player health at 15%")
    │
    ├─ System 1: Check heuristics → "Low health in PvP → warn immediately" (confidence: 0.92)
    │   └─ Match found, high confidence → Execute action, skip LLM
    │
    └─ System 1 fails (no match, low confidence, or conflicting heuristics)
        └─ Escalate to System 2 (LLM) → Reason about situation → Produce response
```

**Escalation triggers** (System 1 → System 2):
- Novelty: no similar situation in memory
- Low confidence on matching heuristics
- Conflicting heuristics suggest different actions
- High-stakes decision (safety-critical events)

### Where we need input

- Is the escalation model cognitively plausible? In Kahneman's framework, System 2 engagement is partly driven by "cognitive strain" — are we modeling the right triggers?
- What happens when System 1 is *confidently wrong*? Biological systems have metacognitive monitoring. Should GLADyS?

## Hippocampal Memory Consolidation

GLADyS's memory hierarchy (L0-L4) is modeled on how the hippocampus processes memories:

| GLADyS Level | Brain Analog | Function |
|---|---|---|
| L0: Context Window | Working memory | Current situation, limited capacity |
| L1: Hot Cache | Short-term hippocampal buffer | Recent events, fast access |
| L2: Warm Buffer | Hippocampal consolidation queue | Pending transfer to long-term |
| L3: Database (Hot) | Recent long-term memory | Indexed, queryable, days to weeks |
| L4: Database (Cold) | Remote long-term memory | Compressed, summarized, archival |

The biological insight: **memories aren't stored once — they're consolidated**. The hippocampus replays recent experiences during sleep, extracting patterns and transferring knowledge to the neocortex.

GLADyS implements this as a "sleep cycle" — a batch processing phase during idle time that:
1. Summarizes old episodes into semantic facts
2. Extracts patterns from repeated observations
3. Updates learned beliefs with accumulated evidence
4. Compresses and archives raw events

### Complementary Learning Systems

The architecture draws from McClelland et al.'s Complementary Learning Systems theory: the brain uses two learning systems with different properties.

| Property | Hippocampal (Fast) | Neocortical (Slow) |
|---|---|---|
| Learning speed | One-shot | Gradual |
| Representation | Specific episodes | General patterns |
| Interference | Low (sparse) | High (overlapping) |
| **GLADyS analog** | Episodic event store | Heuristics + semantic facts |

New events are stored immediately in the episodic store (hippocampal-like). Over time, patterns are extracted and become heuristics or semantic facts (neocortical-like). This prevents catastrophic interference — new specific memories don't overwrite general knowledge.

### Where we need input

- Is L0-L4 a reasonable operationalization of memory consolidation, or are we cargo-culting the terminology?
- The "sleep cycle" is a simplified model of offline replay. Real hippocampal replay is selective and influenced by emotional salience. Should consolidation priority be salience-weighted?
- How should we handle reconsolidation? When a retrieved memory is modified by new context, does the original change?

## Event Segmentation Theory

The brain doesn't store experience as a continuous stream — it segments it into discrete episodes. **Event Segmentation Theory** (Zacks et al., 2007) explains the mechanism: the brain maintains an **Event Model** (a running prediction of what happens next). When prediction error exceeds a threshold, the brain triggers an **Event Boundary**, flushes working memory into episodic storage, and starts a new model.

For GLADyS, this means converting raw sensor streams into bounded episodes rather than storing events individually. Boundary detection, episode summarization, and cross-episode pattern extraction are all open design questions.

**Deep dive**: [Event Segmentation Theory](event-segmentation-theory.md) — detailed mapping to GLADyS, implementation strategy, open questions, and research papers.

## Salience and Attention (The "Amygdala")

The Salience Gateway determines what deserves attention from a continuous stream of events. It's modeled on the brain's salience network (Seeley et al., 2007).

**Key insight from neuroscience**: Salience is not a single score — it's a vector of dimensions. What's "salient" depends on context and current goals.

GLADyS evaluates events across multiple dimensions:

| Dimension | Biological Basis |
|---|---|
| Threat | Amygdala threat detection |
| Opportunity | Reward circuitry (nucleus accumbens) |
| Novelty | Hippocampal novelty detection |
| Goal relevance | Prefrontal goal maintenance |
| Habituation | Sensory adaptation / GABA inhibition |

**Habituation** is particularly important: repeated exposure to the same stimulus reduces response. GLADyS implements this as exponential decay:

```
sensitivity(t) = 1 - (1 - min_sensitivity) * e^(-t / tau)
```

This matches biological habituation recovery — fast initial recovery, slow asymptotic return to full sensitivity. A minimum sensitivity floor (10%) ensures even heavily habituated patterns can break through if they become extreme.

**Context-aware evaluation**: Gaming mode amplifies threat detection (lower thresholds). Home automation mode amplifies novelty detection. The system switches contexts based on active sensors and applications.

### Where we need input

- The salience dimensions were chosen pragmatically, not derived from a formal model. Are we missing critical dimensions? Are some redundant?
- Habituation tau values are hand-tuned per domain. Is there a principled way to set these, or are empirical values the right approach?
- Cross-context salience (e.g., doorbell during gaming) uses a "max across contexts" rule. Is this biologically plausible? The brain seems to use something more nuanced.

## Bayesian Learning

Learned patterns are stored with Bayesian models that track uncertainty and update with evidence.

| Model | Data Shape | Example |
|---|---|---|
| Beta-Binomial | Binary outcomes | "User accepts proactive suggestions" (alpha=15, beta=5 → ~75% acceptance) |
| Normal-Gamma | Continuous values | "Preferred thermostat temperature" (mu=72, kappa=20 → high confidence around 72F) |
| Gamma-Poisson | Rate/count data | "Weekly gaming sessions" (alpha=3, beta=1 → ~3 sessions/week) |

**Why Bayesian?** The models naturally represent uncertainty. A Beta(2,2) prior says "I don't know" — it takes many observations to shift. A Beta(100,10) says "I'm quite sure" — single contradictions barely register. This prevents oscillation from noisy feedback.

**Confidence updates** use Temporal Difference learning:
```
delta = actual_outcome - predicted_outcome
new_confidence = old_confidence + learning_rate * delta
```

This mirrors the brain's dopamine prediction error signal: learning is driven by *surprise* (better or worse than expected), not by absolute outcomes.

### Where we need input

- Are conjugate priors the right tool here, or would we be better served by something like Thompson Sampling for the exploration/exploitation tradeoff?
- Confidence decay for stale patterns uses a staleness heuristic. Is there a more principled approach from the Bayesian literature?
- How should we handle context-dependent beliefs? Currently a pattern can have context_tags, but there's no formal model for how context partitions the belief space.

## Heuristic Formation (Case-Based Reasoning)

Heuristics are formed through a process inspired by Case-Based Reasoning:

```
1. Novel event arrives → no heuristic matches
2. Escalate to LLM (System 2) → LLM reasons and responds
3. User provides positive feedback
4. LLM extracts generalizable pattern from the reasoning trace
5. Pattern stored as new heuristic (condition embedding + action) with low confidence (0.3)
6. Next similar event → heuristic matches via embedding similarity → LLM skipped
7. Feedback loop adjusts confidence up or down over time
```

Matching uses **embedding similarity** (cosine distance via pgvector), not keyword matching. This means "player health critical" matches "HP is dangerously low" even though the words are different.

The matching score combines similarity and confidence: `score = similarity * confidence`. The highest-scoring heuristic wins, but only if it exceeds the similarity threshold (0.7).

### Where we need input

- Is a single similarity threshold correct, or should it be adaptive (per-heuristic or per-domain)?
- How should conflicting heuristics be resolved? Currently highest score wins. Should there be a deliberation mechanism?
- What's the right initial confidence for new heuristics? Too low and they never fire. Too high and untested rules act with unearned authority.

## Experience Replay

System 1 decisions are queued for LLM validation during idle time — a direct analog of **hippocampal replay during sleep**.

For each deferred decision, a three-way comparison runs:

| Component | Value | Timing |
|---|---|---|
| S1 Decision | What the heuristic chose | Real-time |
| LLM Decision | What System 2 would have chosen | Deferred (sleep mode) |
| Actual Outcome | What happened | From feedback or outcome signals |

This produces learning signals:
- S1 = LLM = Good outcome → reinforce heuristic
- S1 ≠ LLM, LLM was right → correct heuristic
- S1 ≠ LLM, S1 was right → heuristic may be *better* than LLM for this case

### Where we need input

- Biological replay is selective — high-salience and high-surprise events are replayed more often. Should we implement prioritized replay from the start, or is FIFO sufficient for early use?
- How long should the replay window be? 72 hours currently. Is there evidence for optimal replay timing?

## Personality as a Learning Variable

GLADyS has a configurable personality system (see ADR-0015). Personality is not cosmetic — it affects how the system interprets events, what it considers salient, and how it communicates.

The critical insight: **personality interacts with learning**. A sarcastic personality might interpret user silence differently than a cautious one. A risk-tolerant personality might let heuristics fire at lower confidence thresholds. This means personality doesn't just shape output — it shapes what gets learned.

We deliberately avoided the Big Five personality model (OCEAN). Big Five describes human personality variance across a population. GLADyS is a single agent whose personality is configured, not measured. The dimensions that matter are behavioral ones: how proactive to be, how verbose, how much humor, how much deference to user override. These map to system parameters, not psychological constructs.

**Personality heuristics** are an experimental concept: heuristics whose conditions or actions are influenced by the active personality configuration. For example:
- A "cautious" personality might require higher confidence before acting autonomously
- A "proactive" personality might lower the salience threshold for opportunity events
- A "terse" personality might suppress informational-only notifications

### The personality-learning interaction problem

This creates two specific concerns:

**Personality switch contamination**: If a user runs a "bold" personality for a month, heuristics form around bold behavior — acting on low-confidence patterns, tolerating more false positives. If the user then switches to a "cautious" personality, those heuristics are wrong for the new personality. They were learned in one behavioral context and applied in another.

This is analogous to **domain shift** in machine learning: the training distribution no longer matches the deployment distribution. Possible approaches:
- Tag heuristics with the personality that produced them
- Decay confidence on personality-influenced heuristics when personality changes
- Separate personality-dependent heuristics from personality-independent ones

**Confirmation bias in learning**: A personality that's biased toward action will generate more feedback data (because it acts more often). A cautious personality generates less data. This means aggressive personalities learn faster — but they may also learn the wrong things, because they're acting on less certain information and treating the results as signal.

This is a form of **selection bias** or **feedback loop bias**: the system's own behavior influences the data it learns from, and personality modulates that behavior. In RL terms, personality affects the exploration policy, which affects what experiences are available for learning.

### Where we need input

- How should heuristic confidence be adjusted when personality changes? Full reset is wasteful. No adjustment risks contamination. Is there a principled middle ground?
- Is there a way to factor out the personality component of a learned heuristic, keeping the domain knowledge while discarding the behavioral bias?
- How do we measure whether personality is improving or degrading learning quality? What metrics would distinguish "personality-appropriate behavior" from "personality-induced bias"?

## What We're Not Doing

Transparency about the boundaries of our approach:

- **No emotion inference**: We don't analyze tone or sentiment to guess emotional state. Unreliable and invasive.
- **No population-level learning**: No "users like you" recommendations. All learning is per-user, local.
- **No deep reinforcement learning**: We use RL-inspired techniques (TD learning, experience replay) but not full RL training. The state/action spaces are too poorly defined for that.
- **No graph neural networks for knowledge**: Semantic memory uses PostgreSQL with simple entity-relationship queries, not graph algorithms. A personal assistant has hundreds of entities, not millions.

## References

### Cognitive Science
- Kahneman, D. (2011). *Thinking, Fast and Slow*
- McClelland, J. L., McNaughton, B. L., & O'Reilly, R. C. (1995). Why there are complementary learning systems in the hippocampus and neocortex
- Seeley, W. W., et al. (2007). Dissociable intrinsic connectivity networks for salience processing and executive control

### Event Segmentation
- Zacks, J. M., Speer, N. K., Swallow, K. M., Braver, T. S., & Reynolds, J. R. (2007). Event Segmentation in Perception and Memory
- Franklin, N. T., Norman, K. A., Ranganath, C., Zacks, J. M., & Gershman, S. J. (2020). Structured Event Memory: A neuro-symbolic model of event cognition

### Reinforcement Learning
- Sutton, R. S., & Barto, A. G. (2018). *Reinforcement Learning: An Introduction* (2nd ed.)
- Schaul, T., et al. (2015). Prioritized Experience Replay

### Case-Based Reasoning
- Kolodner, J. (1993). *Case-Based Reasoning*
- Aamodt, A., & Plaza, E. (1994). Case-Based Reasoning: Foundational Issues

### Technical Details
- [ADR-0004: Memory Schema](../adr/ADR-0004-Memory-Schema-Details.md) — Full schema and hierarchy design
- [ADR-0010: Learning and Inference](../adr/ADR-0010-Learning-and-Inference.md) — Dual-process architecture, Bayesian models, learning pipeline
- [ADR-0013: Salience Subsystem](../adr/ADR-0013-Salience-Subsystem.md) — Attention management, habituation, context-aware filtering