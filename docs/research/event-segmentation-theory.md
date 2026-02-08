# Event Segmentation Theory (EST)

**Status**: Research / pre-design
**Relevant subsystems**: Orchestrator, Memory, Salience
**Parent**: [THEORETICAL_FOUNDATIONS.md](THEORETICAL_FOUNDATIONS.md)

## The Theory

**Event Segmentation Theory** (Zacks et al., 2007) posits that the brain perceives continuous information as discrete "chunks" or events.

- **Event Model**: The brain maintains a working prediction of what happens next
- **Prediction Error**: When sensor state changes unexpectedly, a goal is reached, or context shifts, the brain detects a mismatch
- **Event Boundary**: The prediction error triggers a boundary — working memory is flushed into episodic storage and a new Event Model begins

The result: experience is indexed as bounded episodes, not a continuous log.

## Mapping to GLADyS

| EST Concept | GLADyS Analog | Status |
|---|---|---|
| Event Model | Current context/state maintained by Orchestrator | Implicit (no explicit model yet) |
| Prediction Error | Deviation from expected sensor patterns | Not implemented |
| Event Boundary | Episode delimiter — triggers flush to episodic storage | Not implemented |
| Episode | Bounded sequence of events with summary embedding | Design candidate |

Currently, every sensor event is stored individually in `episodic_events`. EST suggests a richer model where events are grouped into episodes, each with a summary embedding and relational metadata.

## Implementation Strategy

1. **Event Buffer (Working Memory)**: Accumulate incoming sensor events in a temporary state rather than storing each independently
2. **Boundary Detection**: Monitor for context shifts (user switches domains, significant state change, goal completion) as episode delimiters
3. **Episode Snapshot**: On boundary, summarize the buffer and store the summary embedding alongside relational metadata (timespan, sensors involved, outcome)
4. **Heuristic Extraction**: Query episodic clusters to find cross-episode patterns (e.g., "whenever the doorbell rings during a game session, user ignores it")

## Open Questions

- Is boundary detection an Orchestrator responsibility (it sees all events) or a Salience responsibility (it evaluates significance)?
- Should boundaries be purely reactive (prediction error) or also time-based (max episode duration)?
- How does EST interact with multi-sensor operation? A context shift in one sensor domain doesn't necessarily mean a boundary for another.
- Episode granularity: too fine and we're back to individual events; too coarse and we lose temporal resolution. What's the right heuristic?

## Research Papers

### Foundational

- **Zacks, J. M., Speer, N. K., Swallow, K. M., Braver, T. S., & Reynolds, J. R. (2007)**. Event Segmentation in Perception and Memory. *PMC*.
  The foundational paper — explains the cognitive mechanics of prediction error and event boundaries.

- **Franklin, N. T., Norman, K. A., Ranganath, C., Zacks, J. M., & Gershman, S. J. (2020)**. Structured Event Memory: A neuro-symbolic model of event cognition.
  Neural network model of when to retrieve and encode episodic memories. Discusses the "snapshot" approach to episodic encoding.

### Computational

- **Predictive event segmentation and representation with neural networks** (*ScienceDirect*).
  Technical look at simulating EST in AI agents. Closest to what GLADyS would need.

- **Perceptual Segmentation of Natural Events** (*Cambridge University Press*).
  Research on how task shifts serve as boundaries in software interaction.

### Applied / Implementation

- **Episodic Memory for RAG with Generative Semantic Workspaces** (*arXiv*).
  Using LLMs to map raw data to episodic structures. Advanced RAG pattern.

- **LangMem: Extracting Episodic Memories** (*LangChain docs*).
  Software patterns for extracting "learnings" from interaction logs.

- **Building AI Agents with Persistent Memory** (*TigerData*).
  Unified approach for relational and vector-based memory in Postgres.

- **Deep Dive into Cognitive Architecture** (*Towards AI*).
  Guide on vector-based episodic storage for AI memory systems.
