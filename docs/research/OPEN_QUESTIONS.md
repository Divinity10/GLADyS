# Open Research Questions

These are unsolved problems in GLADyS where expert input would make a meaningful difference. Each question is scoped enough to be addressable, but open enough to be interesting.

If any of these resonate with your expertise, open an issue or start a discussion. We'd rather get it right than get it fast.

**Looking for**: Literature research tasks are tracked separately in [RESEARCH_BACKLOG.md](RESEARCH_BACKLOG.md). Design decisions are in [docs/design/questions/](../design/questions/). This document contains only questions that benefit from domain expertise beyond what literature review can provide.

---

## Table of Contents

- [Learning and Prediction](#learning-and-prediction)
  - [How do we measure prediction success?](#how-do-we-measure-prediction-success)
  - [Does System 1 learning actually reduce LLM calls over time?](#does-system-1-learning-actually-reduce-llm-calls-over-time)
- [Personality and Bias](#personality-and-bias)
  - [What happens to heuristics when personality changes?](#what-happens-to-heuristics-when-personality-changes)
  - [How do we prevent personality from biasing the learning process?](#how-do-we-prevent-personality-from-biasing-the-learning-process)
- [Attention and Salience](#attention-and-salience)
  - [Are the salience dimensions correct?](#are-the-salience-dimensions-correct)
  - [Can salience be meaningfully reduced to a scalar?](#can-salience-be-meaningfully-reduced-to-a-scalar)
- [Interaction Design](#interaction-design)
  - [How should a proactive assistant communicate without being annoying?](#how-should-a-proactive-assistant-communicate-without-being-annoying)
  - [How should users understand and correct what the system has learned?](#how-should-users-understand-and-correct-what-the-system-has-learned)
- [Open-Ended](#open-ended)
  - [What brain models are we missing?](#what-brain-models-are-we-missing)

---

## Learning and Prediction

*Relevant expertise: reinforcement learning, online learning, decision theory*

### How do we measure prediction success?

TD learning requires computing prediction error: `error = actual_outcome - predicted_outcome`. But what counts as the "actual outcome" depends on intent that may not be stated.

**The problem in concrete terms:**

A heuristic fires and GLADyS lowers the thermostat by 2 degrees, predicting $100/month savings. Actual savings: $25. Is this:

- A failure (missed the prediction by 75%)?
- A weak success (saved money, just less than expected)?
- Depends on whether the user cared about the exact amount or just the direction?

A gaming heuristic fires and GLADyS warns about friendly fire. The player harms a teammate anyway. Is this:

- A failure (warning ignored)?
- Irrelevant (the player intended to harm the teammate)?
- A success (warning was delivered; player chose to override)?

**Design stance**: GLADyS optimizes for correctness, not user comfort (see [THEORETICAL_FOUNDATIONS.md](THEORETICAL_FOUNDATIONS.md#guiding-principles)). A correct prediction that gets overridden is a *success* — the heuristic was right, the user chose differently. This simplifies part of the problem: success = prediction accuracy, not user satisfaction. But it doesn't eliminate the question of *what* was predicted and how to measure it.

**What data would we need to track?**

- The prediction itself (what the heuristic expected to happen)
- The predicted magnitude (not just direction — "save money" vs "save $100")
- The actual outcome (measured from sensors or feedback)
- The variance between prediction and outcome
- Whether the user overrode the action (which signals intent disagreement, not necessarily failure)

**The research questions:**

- **Can we infer intent without asking?** Repeated overrides of a heuristic suggest the user's goals differ from what the heuristic assumes. But can we distinguish "I don't want this" from "not right now"? Can we detect non-intuitive intent (e.g., a player who *wants* to harm teammates) from behavioral patterns alone?
- **Should prediction error be magnitude-sensitive?** Saving $25 instead of $100 is qualitatively different from saving $0 or losing money. Should the learning rate scale with how wrong the prediction was, or just with the sign (better/worse than expected)?
- **Who defines the prediction?** Currently the heuristic's confidence serves as an implicit prediction. Should heuristics store explicit expected outcomes (structured predictions) that can be compared against measurements?
- **How should expected value be incorporated into heuristic selection?** The current scoring model (`similarity × confidence`) ignores the *magnitude* of the predicted outcome. A heuristic with 90% confidence of saving $10 (EV=$9) scores differently than one with 20% confidence of saving $100 (EV=$20). The design principle says optimize for E(X), not prospect theory — so loss aversion doesn't apply. But open questions remain: how do heuristics store predicted magnitude? When two actions have the same EV but different variance profiles, does personality modulate risk tolerance, or do we always prefer the higher-EV option?

**Relevant**: ADR-0010 Section 3.11 (Outcome Evaluation), design questions §27 (Prediction Baseline Strategy)

### Does System 1 learning actually reduce LLM calls over time?

The hypothesis: as heuristics accumulate and gain confidence, more events are handled by System 1, reducing expensive LLM calls. This is the core value proposition.

**The question**: How would we measure this rigorously? What's the expected learning curve shape? Is there a theoretical bound on how many interactions it takes before System 1 handles X% of events for a given domain?

**Relevant**: ADR-0010 Section 3.18 (monitoring metrics)

---

## Personality and Bias

*Relevant expertise: ML fairness, behavioral science, reinforcement learning*

### What happens to heuristics when personality changes?

Heuristics are learned under a specific personality configuration. A "bold" personality produces heuristics calibrated for low-confidence action. Switching to a "cautious" personality means those heuristics are mismatched — they were trained under a different behavioral policy.

**The question**: How should the system handle personality switches?

- Full confidence reset wastes all learning
- No adjustment applies bold-context heuristics in a cautious context
- Tagging heuristics with their source personality and decaying on switch is one approach, but how much decay?
- Can we factor out the personality component of a heuristic, keeping the domain knowledge (e.g., "low health is dangerous") while discarding the behavioral bias (e.g., "act immediately without confirmation")?

This is a variant of **domain shift** — the training distribution changes when personality changes.

**Relevant**: ADR-0015 (Personality Subsystem), ADR-0010 Section 3.16 (Risk Tolerance)

### How do we prevent personality from biasing the learning process?

A proactive personality acts more often, generating more feedback data. A cautious personality acts less. This means proactive personalities learn faster — but also risk learning from lower-quality actions (acting on weaker evidence and treating outcomes as signal).

**The question**: This is a form of selection bias or feedback loop bias. The system's own behavior (influenced by personality) determines what data is available for learning. How do we:

- Distinguish "this heuristic works well" from "this heuristic fires often because personality lowers the bar"?
- Measure whether a personality is improving or degrading learning quality?
- Prevent a runaway feedback loop where personality-driven actions reinforce personality-aligned heuristics, creating a self-confirming system?

In RL terms, personality modulates the exploration policy. Is there a principled way to correct for this in the learning updates?

**Design stance**: GLADyS prefers approaches that structurally avoid cognitive biases rather than reproducing them and filtering them out (see [THEORETICAL_FOUNDATIONS.md](THEORETICAL_FOUNDATIONS.md#guiding-principles)). The learning pipeline should ideally be personality-invariant — personality modulates behavioral parameters, not the evidence signal.

**Relevant**: ADR-0015 (Personality Subsystem), ADR-0010 Section 3.16 (Risk Tolerance)

---

## Attention and Salience

*Relevant expertise: cognitive science, neuroscience, attention research*

### Are the salience dimensions correct?

Current dimensions: threat, opportunity, humor, novelty, goal_relevance, social, emotional, actionability, habituation.

**The question**: These were chosen pragmatically. From a cognitive science perspective:

- Are any of these redundant (measuring the same underlying construct)?
- Are we missing critical dimensions? (e.g., urgency as distinct from threat, familiarity as distinct from novelty)
- Should dimensions be orthogonal, or is correlation between them expected and useful?

**Relevant**: ADR-0013 Section 5.2

### Can salience be meaningfully reduced to a scalar?

Salience is currently a vector of dimensions (threat, opportunity, novelty, etc.). Routing decisions, priority queuing, and threshold gating all need to compare events — which requires collapsing the vector into a comparable value at some point.

**The problem**: Is an event with 0.6 threat / 0.7 novelty / 0.4 opportunity "the same salience" as one with 0.4 threat / 0.7 novelty / 0.6 opportunity? Intuitively, no — a high-threat event demands a different response than a high-opportunity event, even if the magnitudes sum the same. But the routing system needs to decide which one gets attention first.

**Current approach**: Context-specific weights determine which dimensions matter more (gaming amplifies threat; home amplifies novelty), and the weighted sum produces a priority score. But this means the scalar is context-dependent — the same vector produces different priorities in different contexts.

**The research questions:**

- **Should some dimensions be non-compensatory?** In the current weighted-sum model, very high novelty can compensate for zero threat. But some dimensions may be qualitatively different — a safety-critical threat shouldn't be "compensated" by high humor. Should certain dimensions act as floors or overrides rather than additive components?
- **Does the learning pipeline need the vector or the scalar?** If heuristics learn from scalar salience, they can't distinguish *why* something was salient. If they learn from the vector, they can develop dimension-specific sensitivities. What's the right representation for learning?

**Relevant**: ADR-0013 Section 5.2 (dimension computation), ADR-0001 Section 7.1 (salience dimensions)

---

## Interaction Design

*Relevant expertise: human-computer interaction, UX research*

### How should a proactive assistant communicate without being annoying?

GLADyS can initiate actions based on heuristics and salience. But unsolicited advice is a known UX anti-pattern.

**The question**: What interaction patterns make proactive behavior welcome rather than intrusive?

- How does configurable personality (from sarcastic to helpful) affect tolerance for proactive suggestions?
- Should proactive behavior require earning trust through accuracy first?
- Is there a "suggestion budget" — a maximum rate of unsolicited communications?

### How should users understand and correct what the system has learned?

Heuristics, confidence scores, and learned patterns are inspectable (observability is a design principle). But presenting them in an understandable way is an open problem.

**The question**: What mental models do users form about learned AI behavior? How should GLADyS present:

- What heuristics exist and why
- Why a particular action was taken (or not taken)
- How to correct a wrong belief without requiring technical knowledge

---

## Open-Ended

### What brain models are we missing?

GLADyS draws from a specific set of neuroscience concepts: dual-process cognition, hippocampal consolidation, complementary learning systems, salience networks, habituation, and dopamine prediction error. These were chosen because they map well to engineering problems we already had.

**The question**: What models or mechanisms from neuroscience or cognitive science would benefit GLADyS's learning, routing, memory, recall, or performance — that we haven't considered?

Some candidates we're aware of but haven't explored:

- **Predictive coding** (Friston): The brain constantly generates predictions and processes only prediction errors. Could this replace or complement the salience model?
- **Spreading activation** (Anderson): Memory recall activates related concepts. Could this improve context retrieval beyond embedding similarity?
- **Somatic markers** (Damasio): Emotional tags on memories influence decision-making. GLADyS avoids emotion inference, but could non-emotional "outcome tags" serve a similar function?
- **Cognitive load theory** (Sweller): Working memory has structural limits. Does this suggest constraints on L0 context window management beyond token counts?
- **Chunking** (Miller): Information is grouped into meaningful units. Could event condensation be modeled as chunking rather than deduplication?

We're not trying to model the brain. We're looking for models that solve real engineering problems — better learning, faster routing, more accurate recall, more appropriate responses. If a brain model doesn't map to a concrete improvement, it's interesting but not useful to us.

---

## How to Contribute

If any of these questions interest you:

1. **Review the relevant ADRs** linked in each question — they contain the full technical context
2. **Read [THEORETICAL_FOUNDATIONS.md](THEORETICAL_FOUNDATIONS.md)** for the overall approach
3. **Open an issue or discussion** on GitHub with your thoughts
4. **Don't worry about implementation** — we're looking for theoretical and empirical input, not code

We're particularly interested in hearing from people with backgrounds in:

- Cognitive science / neuroscience
- Reinforcement learning / online learning
- Human-computer interaction
- Recommender systems
