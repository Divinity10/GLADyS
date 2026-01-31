# Open Research Questions

These are unsolved problems in GLADyS where expert input would make a meaningful difference. Each question is scoped enough to be addressable, but open enough to be interesting.

If any of these resonate with your expertise, open an issue or start a discussion. We'd rather get it right than get it fast.

## Learning and Inference

### How should confidence decay when no feedback is received?

Heuristics have a confidence score that updates with feedback. But what happens when a heuristic simply stops being triggered? It could mean the situation no longer arises (the heuristic is stale), or it could mean the heuristic is working so well that events are handled silently.

Current approach: staleness detection based on expected observation frequency. If a pattern is significantly overdue (`staleness > 3 standard deviations`), confidence decays.

**The question**: Is this the right decay model? Should decay be monotonic, or should there be a "grace period" before decay begins? How do we distinguish "no longer relevant" from "still valid but dormant"?

**Relevant**: ADR-0010 Section 3.3.4, `learned_patterns.expected_period`

### What's the right similarity threshold for heuristic matching?

Heuristics match incoming events via embedding cosine similarity (pgvector). The current threshold is 0.7 globally.

**The question**: Should the threshold be:
- Global (one number for everything)?
- Per-heuristic (learned from feedback — heuristics that produce false positives tighten their threshold)?
- Per-domain (gaming may need tighter matching than home automation)?
- Adaptive (starts loose, tightens as confidence grows)?

At 0.7, "user wants ice cream" matches "user wants frozen dessert" (0.78) but not "email about meeting" (0.69). Is that the right boundary?

**Relevant**: ADR-0010 Section 3.2, `heuristics.similarity_threshold`

### How should conflicting heuristics be resolved?

When multiple heuristics match an event, the highest `similarity * confidence` score wins. This is a simple argmax.

**The question**: Is argmax the right strategy? Alternatives:
- Weighted voting across matching heuristics
- Escalate to System 2 when top-2 scores are close (deliberation trigger)
- Domain-specific resolution strategies
- Hierarchical heuristics (some override others)

**Relevant**: ADR-0010 Section 3.1 (escalation triggers)

### How do we define "success" for learning when outcomes are subjective?

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

**The core issue**: There is no absolute definition of success. Outcomes are evaluated against *intent*, and intent is often unspoken.

**What data would we need to track?**
- The prediction itself (what the heuristic expected to happen)
- The predicted magnitude (not just direction — "save money" vs "save $100")
- The actual outcome (measured from sensors or feedback)
- The variance between prediction and outcome
- Whether the user overrode the action (which signals intent disagreement, not necessarily failure)

**The research questions:**

- **Can we infer intent without asking?** Repeated overrides of a heuristic suggest the user's goals differ from what the heuristic assumes. But can we distinguish "I don't want this" from "not right now"? Can we detect non-intuitive intent (e.g., a player who *wants* to harm teammates) from behavioral patterns alone?
- **Should prediction error be magnitude-sensitive?** Saving $25 instead of $100 is qualitatively different from saving $0 or losing money. Should the learning rate scale with how wrong the prediction was, or just with the sign (better/worse than expected)?
- **How do we handle partial success?** Binary success/failure is easy to model (Beta-Binomial). But most outcomes are graded. What's the right model for "mostly worked but not as well as expected"?
- **Who defines the prediction?** Currently the heuristic's confidence serves as an implicit prediction. Should heuristics store explicit expected outcomes (structured predictions) that can be compared against measurements?

**Relevant**: ADR-0010 Section 3.11 (Outcome Evaluation), design questions §27 (Prediction Baseline Strategy)

### Does our TD learning model actually reduce LLM calls over time?

The hypothesis: as heuristics accumulate and gain confidence, more events are handled by System 1, reducing expensive LLM calls. This is the core value proposition.

**The question**: How would we measure this rigorously? What's the expected learning curve shape? Is there a theoretical bound on how many interactions it takes before System 1 handles X% of events for a given domain?

**Relevant**: ADR-0010 Section 3.18 (monitoring metrics)

## Memory and Consolidation

### Is the L0-L4 hierarchy a good model for memory consolidation?

The memory hierarchy maps CPU cache levels to memory consolidation stages. L0 (context window) through L4 (cold archive) have increasing latency and decreasing access frequency.

**The question**: Is this mapping principled, or is it a convenient metaphor? Specifically:
- The brain's consolidation is influenced by emotional salience and surprise. Should consolidation priority be salience-weighted rather than purely temporal?
- Reconsolidation (modifying memories when retrieved) is a real phenomenon. Should GLADyS update stored events when they're accessed in a new context?
- The "sleep cycle" runs during idle time. Real hippocampal replay is selective. Should we replay high-surprise events more?

**Relevant**: ADR-0004 Section 4, memory questions in `docs/design/questions/memory.md`

### How should semantic facts be derived from episodic events?

The current plan: LLM-based extraction during the sleep cycle. Feed batches of events to an LLM, ask it to extract subject-predicate-object facts.

**The question**: Is LLM-based extraction the right approach, or should we use more structured methods (information extraction, knowledge graph construction)? What quality controls are needed? How do we handle contradictory facts from different episodes?

**Relevant**: ADR-0004 Section 8.3, ADR-0010 Section 3.2

## Salience and Attention

### Are the salience dimensions correct?

Current dimensions: threat, opportunity, humor, novelty, goal_relevance, social, emotional, actionability, habituation.

**The question**: These were chosen pragmatically. From a cognitive science perspective:
- Are any of these redundant (measuring the same underlying construct)?
- Are we missing critical dimensions? (e.g., urgency as distinct from threat, familiarity as distinct from novelty)
- Should dimensions be orthogonal, or is correlation between them expected and useful?

**Relevant**: ADR-0013 Section 5.2

### Can salience be meaningfully reduced to a scalar, or must it remain a vector?

Salience is currently a vector of dimensions (threat, opportunity, novelty, etc.). Routing decisions, priority queuing, and threshold gating all need to compare events — which requires collapsing the vector into a comparable value at some point.

**The problem**: Is an event with 0.6 threat / 0.7 novelty / 0.4 opportunity "the same salience" as one with 0.4 threat / 0.7 novelty / 0.6 opportunity? Intuitively, no — a high-threat event demands a different response than a high-opportunity event, even if the magnitudes sum the same. But the routing system needs to decide which one gets attention first.

**Current approach**: Context-specific weights determine which dimensions matter more (gaming amplifies threat; home amplifies novelty), and the weighted sum produces a priority score. But this means the scalar is context-dependent — the same vector produces different priorities in different contexts.

**The research questions:**

- **Are the dimensions orthogonal?** If threat and opportunity are correlated (high-threat situations are often high-opportunity), the vector has redundant dimensions. If they're independent, the vector carries real information that a scalar destroys. Empirical data from running the system would answer this, but we don't have it yet.
- **Should some dimensions be non-compensatory?** In the current weighted-sum model, very high novelty can compensate for zero threat. But some dimensions may be qualitatively different — a safety-critical threat shouldn't be "compensated" by high humor. Should certain dimensions act as floors or overrides rather than additive components?
- **Is there a better reduction than weighted sum?** Alternatives: max across dimensions (simple but loses composition), L2 norm (preserves magnitude), learned projection (data-driven but requires training data). What does the attention/salience literature suggest?
- **Does the learning pipeline need the vector or the scalar?** If heuristics learn from scalar salience, they can't distinguish *why* something was salient. If they learn from the vector, they can develop dimension-specific sensitivities. What's the right representation for learning?

**Relevant**: ADR-0013 Section 5.2 (dimension computation), ADR-0001 Section 7.1 (salience dimensions)

### Is exponential decay the right model for habituation?

Habituation (reduced response to repeated stimuli) uses exponential decay with a configurable time constant (tau) per domain.

**The question**: Biological habituation has properties we may not be capturing:
- **Dishabituation**: A novel stimulus restores sensitivity to a habituated stimulus. Do we model this?
- **Sensitization**: Intense stimuli can increase (not decrease) sensitivity. Our model only decays.
- **Stimulus specificity**: Habituation is highly specific to the exact stimulus. Our pattern matching may be too broad.

**Relevant**: ADR-0013 Section 12

### How should cross-context salience work?

When a doorbell rings during a gaming session, two contexts apply: gaming (primary) and home (the doorbell's domain). Currently, we evaluate with both profiles and take the maximum salience.

**The question**: Is "max across contexts" correct? The brain doesn't simply take the maximum — it has attentional switching costs and can miss things during context transitions. Should we model:
- Switching cost (brief reduced sensitivity during context change)?
- Persistent background monitoring (some contexts always run)?
- Priority ordering (safety contexts always override)?

**Relevant**: ADR-0013 Section 5.3.1

## Event Volume and Deduplication

### How should high-volume repetitive events be condensed without losing learning signal?

Some sensors produce high-frequency data — a motion sensor firing hundreds of times per hour, a game emitting damage events every tick, a temperature sensor reporting every second. Most of these are repetitive. Storing and processing each one individually is wasteful, but naive deduplication destroys information the learning pipeline needs.

**The tension**: Condensing events improves performance. But the *pattern* of repetition is itself meaningful. "Doorbell motion detected once" and "doorbell motion detected 47 times in 10 minutes" are different situations with different salience. If we collapse them into one event, we lose the frequency signal. If we keep all 47, we waste compute and storage.

**Possible approaches (not mutually exclusive)**:

- **Sensor-level rate limiting**: Sensors fire on intervals, batching events. Repeated events include a list of timestamps rather than separate messages. Moves the problem upstream.
- **Orchestrator-level condensation**: Keep a recent event map. Identical events within a time window are merged into a single event with occurrence count and timestamps.
- **Storage-level compression**: Store identical events as one record with an array of timestamps.

**The research questions**:

- **What's the right condensation unit?** By exact event match? By embedding similarity? By source? The choice affects what patterns are visible to the learning pipeline.
- **Does condensation interact with habituation?** Habituation already reduces sensitivity to repeated stimuli. If we also condense the events, we're double-filtering — the learning pipeline sees neither the raw frequency nor the habituated response. Is there a model where condensation and habituation are the same mechanism?
- **What information is lost?** Temporal patterns (bursts, periodicity, acceleration) are destroyed by simple deduplication. A motion sensor that fires irregularly means something different from one that fires in a steady rhythm. Which temporal features matter enough to preserve?
- **Should condensation be a preprocessor function?** A preprocessor that detects repetitive bursts and condenses them before the salience gateway would need state (recent event history). This overlaps with the preprocessor state budget question below.

**Relevant**: ADR-0013 Section 6.3 (overload handling), ADR-0004 Section 4 (memory hierarchy)

## Preprocessing and Early Filtering

### Should sensors have preprocessor plugins, and what are the constraints?

Raw sensor data is often noisy. A doorbell camera fires on every motion event — bushes swaying, cars passing, shadows shifting. Most of these are irrelevant. Sending all of them through the full salience pipeline wastes compute and pollutes the event stream.

**The current thinking**: Preprocessors are optional plugins that sit between a sensor and the salience gateway. They must be:
- **Extremely fast** (sub-millisecond, no model inference)
- **Salience-affecting** (their only job is to annotate or adjust salience hints before the event reaches the gateway)

Example: a doorbell motion sensor fires. A preprocessor evaluates whether the detected motion is human-shaped. No → reduce salience hint. Yes → leave salience alone or boost it. The salience gateway still makes the final routing decision, but the preprocessor provides domain-specific signal that the gateway can't compute cheaply.

**The questions**:

- **Where's the boundary between preprocessor and sensor?** If the doorbell camera does its own human detection, is that a preprocessor or just a smarter sensor? Does the distinction matter architecturally, or is it just a deployment choice?

- **What can preprocessors know?** If they're stateless and fast, they can only do simple classification. But some useful preprocessing requires state (e.g., "this is the third motion event in 60 seconds from the same zone" — that's a pattern, not a single-event classification). How much state is acceptable before a "preprocessor" is really a subsystem?

- **Should preprocessors be able to drop events entirely?** Current thinking is no — they annotate salience, and the gateway decides. But if a doorbell fires 200 times per hour from wind, even annotated events are noise. Is there a case for preprocessor-level suppression, or does that violate the principle that the salience gateway owns all filtering decisions?

- **How do preprocessors interact with learning?** If a preprocessor incorrectly suppresses a real threat (human misclassified as bush), the salience gateway never sees it, so the learning pipeline never gets the feedback signal. The error is invisible. How do we detect and correct for preprocessing errors?

**Relevant**: ADR-0013 Section 4.1 (pipeline position), ADR-0003 (plugin architecture)

## Personality and Learning

### What happens to heuristics when personality changes?

Heuristics are learned under a specific personality configuration. A "bold" personality produces heuristics calibrated for low-confidence action. Switching to a "cautious" personality means those heuristics are mismatched — they were trained under a different behavioral policy.

**The question**: How should the system handle personality switches?
- Full confidence reset wastes all learning
- No adjustment applies bold-context heuristics in a cautious context
- Tagging heuristics with their source personality and decaying on switch is one approach, but how much decay?
- Can we factor out the personality component of a heuristic, keeping the domain knowledge (e.g., "low health is dangerous") while discarding the behavioral bias (e.g., "act immediately without confirmation")?

This is a variant of **domain shift** — the training distribution changes when personality changes.

### How do we prevent personality from biasing the learning process?

A proactive personality acts more often, generating more feedback data. A cautious personality acts less. This means proactive personalities learn faster — but also risk learning from lower-quality actions (acting on weaker evidence and treating outcomes as signal).

**The question**: This is a form of selection bias or feedback loop bias. The system's own behavior (influenced by personality) determines what data is available for learning. How do we:
- Distinguish "this heuristic works well" from "this heuristic fires often because personality lowers the bar"?
- Measure whether a personality is improving or degrading learning quality?
- Prevent a runaway feedback loop where personality-driven actions reinforce personality-aligned heuristics, creating a self-confirming system?

In RL terms, personality modulates the exploration policy. Is there a principled way to correct for this in the learning updates?

**Relevant**: ADR-0015 (Personality Subsystem), ADR-0010 Section 3.16 (Risk Tolerance)

## Interaction Design

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