# Confidence Bootstrapping: How Do New Heuristics Earn Trust?

**Created**: 2026-02-01
**Status**: Resolved → [CONFIDENCE_BOOTSTRAPPING.md](../CONFIDENCE_BOOTSTRAPPING.md)
**Related**: ADR-0010 (Learning), #55 (confidence catch-22), #56 (cross-domain filtering)

> **Resolved 2026-02-08**: Design promoted to full design doc. See [CONFIDENCE_BOOTSTRAPPING.md](../CONFIDENCE_BOOTSTRAPPING.md) for the complete design including evaluation prompt specification, concurrency model, confidence update mechanics, and executive contract.

## Problem

Learned heuristics start at confidence 0.3. The firing threshold is 0.7. A heuristic can only gain confidence through feedback on its fires. But it can't fire until it reaches the threshold. It never reaches the threshold because it never fires.

This was confirmed during Phase 1 hands-on testing. Every learned heuristic stayed at 0.3 forever, and every event routed to the LLM regardless of how many similar events had been successfully handled before.

## Proposed Solution: LLM-Informed Heuristic Evaluation

When a heuristic matches an event but is below the firing threshold, instead of ignoring it:

1. **Send the event to the LLM with the heuristic's response as context** — but frame it neutrally to avoid priming the LLM toward agreement
2. **The LLM generates its own response independently**
3. **Compare the LLM response to the heuristic response** to determine if the heuristic was on the right track
4. **Update confidence based on similarity** — LLM endorsement counts as a weaker signal than explicit user feedback

### Neutral Framing

LLMs have a documented sycophancy bias. Presenting a candidate response as "a learned pattern suggests X" primes the LLM to agree. The prompt should:

- Present the candidate response as one possible response without indicating its source
- Ask the LLM to generate its own response to the event
- Not ask the LLM to evaluate or judge the candidate

Example framing:
> Given this event, consider the following possible response: [heuristic response]. Generate your own response to this event. You may use, adapt, or completely disregard the provided response.

### What to Include in the LLM Request

- Event text (the event being evaluated)
- Heuristic condition_text (what pattern it claims to match)
- Heuristic response/action (the candidate response)
- Heuristic confidence and fire_count (how established it is)

Do NOT include: heuristic origin, internal system metadata, other candidate heuristics, or language indicating the response has been "learned" or "validated."

### Post-Comparison

After the LLM generates its response, compare it to the heuristic's response. This comparison is **not on the critical path** — the user already has their response (the LLM's). The comparison is a confidence bookkeeping task that can run asynchronously.

Options for comparison:
- Embedding similarity between the two responses (cheap, available via existing infrastructure)
- Lightweight LLM call asking "are these responses substantially similar?" (more nuanced, more expensive)

Start with embedding similarity. It's already built.

### Confidence Update Weights

LLM endorsement is weaker evidence than explicit user feedback. Proposed ordering:

| Signal | Weight | Rationale |
|--------|--------|-----------|
| Explicit positive feedback (user ðŸ‘) | 1.0 | Strongest — direct user validation |
| Implicit positive (silence after timeout) | 0.7 | User didn't complain, but may not have noticed |
| LLM endorsement (similar response) | 0.5 | LLM agrees, but LLMs have biases |
| LLM rejection (dissimilar response) | -0.5 | LLM disagrees — weak negative |
| Explicit negative feedback (user ðŸ‘Ž) | -1.0 | Strongest negative — direct user rejection |
| Ignored 3x (heuristic fired, user ignored) | -0.3 | Pattern of disengagement |

These weights are starting points. Tune based on observed behavior.

## Deferred Ideas

### Dynamic LLM Quality Scoring

The weight of LLM endorsement could vary based on how reliable the LLM has proven to be. A high-quality LLM's endorsement should count for more than a low-quality one's. This is a meta-learning problem — the system learning how much to trust its own reasoning engine.

Observations from Phase 1:
- `gemma3:1b` produced garbage condition_texts — its endorsement would be nearly worthless
- `gemma3:4b` produced usable generalizations — its endorsement is meaningful
- Diminishing returns likely apply: the jump from 1B→4B was transformative, 4B→70B would likely be marginal for pattern extraction tasks

Implementation: track LLM endorsement accuracy against eventual user feedback. If the LLM endorses a heuristic and the user later gives positive feedback, the LLM was right. Accumulate a quality score over time and use it to scale endorsement weight.

**Defer to**: Phase 3 or later. Requires sufficient data to be meaningful.

### Confidence Model Alternatives

The current Beta-Binomial model (ADR-0010) may not be the right fit once LLM endorsement is a signal. Beta-Binomial assumes binary success/failure observations. With weighted signals, an EMA (exponential moving average) or Bayesian update with variable observation weights might be more appropriate.

**Defer to**: After Phase 2 produces data on how the weighted signals behave in practice.

## Relationship to #56 (Cross-Domain Filtering)

The confidence bootstrapping problem is worse when combined with missing source-based filtering. A low-confidence heuristic that matches cross-domain (sudoku heuristic matching melvor events) would get sent to the LLM with irrelevant context. Source filtering should be resolved alongside or before this change.

## Implementation Scope (Phase 2)

1. When a heuristic matches below threshold: include it in the LLM request with neutral framing
2. LLM generates independently
3. Async post-comparison via embedding similarity
4. Confidence update with 0.5x weight for LLM endorsement
5. Origin does not affect confidence update weights — a heuristic is a heuristic regardless of how it was created

