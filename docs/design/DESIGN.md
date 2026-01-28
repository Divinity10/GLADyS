# GLADyS System Design

**Last updated**: 2026-01-27
**Status**: Living document - reflects current implementation

## How to Use This Document
- Each section covers one subsystem
- "Current Implementation" = what's actually built
- "PoC Deviations" = where we cut corners from ADRs
- "Open Questions" = unresolved issues
- For session-specific decisions, see claude_memory.md
- For conceptual overview and onboarding, see [SUBSYSTEM_OVERVIEW.md](SUBSYSTEM_OVERVIEW.md)

---

## Why GLADyS?

### What Makes GLADyS Different

| Capability | Alexa/Siri | ChatGPT | GLADyS |
|------------|------------|---------|--------|
| Responds to commands | ✅ | ✅ | ✅ |
| Learns preferences | ✅ shallow | ❌ | ✅ deep (behavioral patterns) |
| Proactive actions | ✅ notifications | ❌ | ✅ salience-driven, context-aware |
| Cross-domain awareness | ❌ siloed | ❌ no state | ✅ unified memory |
| Gets faster with use | ❌ | ❌ | ✅ heuristic learning |
| Local/private by default | ❌ cloud | ❌ cloud | ✅ local-first |
| Customizable personality | ❌ fixed | ❌ | ✅ configurable |

### Killer Features (Priority Order)

1. **"The Second Time is Faster"** (Heuristic Learning)
   - First request: LLM reasons through the problem (slow)
   - User feedback: "That was helpful"
   - Second request: Heuristic fires, skips LLM (instant)
   - *No existing assistant does this.*

2. **Proactive Intelligence**
   - Not just "reminder in 10 minutes"
   - "Steve just came online and you wanted to play — want me to message him?"
   - Requires salience evaluation + real sensors

3. **Cross-Domain Reasoning**
   - "Is Steve free for dinner?" checks Discord + Calendar + knows which Steve
   - Unified memory across all domains

---

## What the PoC Must Prove

| Feature | Requirement | Status |
|---------|-------------|--------|
| Heuristic creation | Explicit feedback → new heuristic stored | ⚠️ Needs validation |
| Heuristic matching | Similar event → heuristic fires | ✅ Proven |
| Heuristic confidence | Bayesian updates from feedback | ✅ Proven |
| Cross-domain query | Multi-hop reasoning works | ✅ Proven |
| Proactive action | Real sensor → system responds | 🔴 No real sensor yet |

---

## Memory Subsystem
### Architecture
A multi-tiered storage system for episodic (events), semantic (facts), and procedural (heuristics) memory. Designed with a hot/cold split: fast access for recent context, deep storage for long-term retention.
**Source**: [ADR-0004](../adr/ADR-0004-Memory-Schema-Details.md), [ADR-0009](../adr/ADR-0009-Memory-Contracts-and-Compaction-Policy.md)

### Current Implementation
- **Storage**: PostgreSQL with `pgvector` for embedding similarity search.
- **Language**: Python (`gladys_memory`) handles I/O bound storage; Rust (`gladys_memory` crate) handles fast-path caching.
- **Data Types**:
    - `episodic_events`: Raw event log with embeddings.
    - `entities` / `relationships`: Graph-like semantic memory.
    - `heuristics`: Learned rules with confidence scores.
- **Search**: Hybrid search using embedding similarity (cosine) + metadata filtering.

### PoC Deviations
- **L1/L2 Cache**: Skipped. System jumps from L0 (in-memory) to L3 (PostgreSQL).
- **Compaction**: Basic implementation. Advanced summarization pipelines are future work.

### Open Questions
- **Embedding Migration**: How to handle model upgrades without re-indexing everything?
- **Graph Traversal**: Efficiently querying >2 hop relationships in standard Postgres.

---

## Salience Subsystem
### Architecture
The "attention filter" of the brain. Determines if an event is important enough to wake the Executive (LLM).
**Source**: [ADR-0013](../adr/ADR-0013-Salience-Subsystem.md)

### Current Implementation
- **Gateway**: Rust service (`SalienceGateway`) acting as the first line of defense.
- **Heuristics**: Checks incoming events against cached heuristics (System 1).
- **Novelty**: Computes embedding distance to recent events to detect anomalies.
- **Scoring**: Calculates a `SalienceVector` (threat, opportunity, etc.). High scores trigger immediate routing.

### PoC Deviations
- **Deep Evaluation**: Skipped. No secondary ML model for complex salience; relies purely on heuristics + novelty.
- **Habituation**: Simple exponential decay based on repetition.

### Open Questions
- **Context Detection**: How to reliably detect "Context" (e.g., "Gaming" vs "Working") to switch active heuristic sets?

---

## Learning Subsystem
### Architecture
A dual-process learning engine. System 1 (Heuristics) learns from feedback to handle routine tasks fast. System 2 (LLM) handles novel situations and teaches System 1.
**Source**: [ADR-0010](../adr/ADR-0010-Learning-and-Inference.md), [ADR-0007](../adr/ADR-0007-Adaptive-Algorithms.md)

### Current Implementation
- **Mechanism**: **Bayesian Beta-Binomial** with Beta(1,1) prior.
- **Confidence**: Posterior mean = `(1 + success_count) / (2 + fire_count)`. New heuristics start at 0.5, converging with evidence.
- **Feedback**: Explicit (User Thumbs Up/Down) and Implicit (OutcomeWatcher).
- **Storage**: Heuristics stored with `confidence`, `fire_count`, `success_count` in Postgres.

### PoC Deviations
- **Full Bayesian**: ADR-0010 allows for more sophisticated modeling (e.g., hierarchical priors, context-dependent updates). PoC uses simple Beta-Binomial.
- **Pattern Extraction**: Manual or simple LLM prompting, rather than automated background batch processing.

### Open Questions
- **Attribution**: When feedback arrives 10 minutes later, which heuristic gets the credit/blame?
- **Unlearning**: How to degrade confidence effectively without making the system schizophrenic?

---

## Executive Subsystem
### Architecture
The decision-making core (System 2). Uses Large Language Models (LLMs) to reason about high-salience events that heuristics couldn't handle.
**Source**: [ADR-0014](../adr/ADR-0014-Executive-Decision-Loop.md)

### Current Implementation
- **Service**: Python stub (`executive-stub`) wrapping Ollama/LLM APIs.
- **Loop**: OODA-style loop (Observe, Orient, Decide, Act).
- **Context**: RAG-like retrieval of relevant Memory (Entities, Past Events) before prompting.

### PoC Deviations
- **Complexity**: "Stub" implementation is lighter than the full C# design in ADR-0001.
- **Planning**: Multi-step planning is nascent; mostly stimulus-response.

### Open Questions
- **Latency**: LLM inference (even local) is slow. How to mask this latency for the user?
- **Prompt Engineering**: Generalizing prompts across vastly different domains (Minecraft vs Home Automation).

---

## Orchestrator Subsystem
### Architecture
The central nervous system. Routes messages between Sensors, Salience, Executive, and Actuators. Manages the lifecycle of plugins.
**Source**: [ADR-0001](../adr/ADR-0001-GLADyS-Architecture.md)

### Current Implementation
- **Language**: Python (Refactored from Rust per recent design change).
- **Protocol**: gRPC for all internal communication.
- **Routing** (3-path model):
    - **Heuristic Shortcut (System 1)**: Event matches heuristic with confidence >= 0.7 → return action immediately, no LLM.
    - **Priority Queue**: No high-confidence match → queue by salience, process async via Executive.
    - **Timeout**: Events expire after 30s (configurable) with error response.
- **EventQueue**: Priority queue (heapq) ordered by salience. Background worker dequeues and calls Executive.

### PoC Deviations
- **Queues**: Using in-memory `EventQueue` instead of persistent brokers (RabbitMQ/Kafka). Events lost on restart is acceptable.
- **DAG**: Preprocessor DAG is linear/hardcoded rather than dynamic.

### Open Questions
- **Backpressure**: Handling event floods (e.g., combat logs) without dropping critical signals.
- **Priority Inversion**: High-salience events should preempt in-flight low-salience processing.
