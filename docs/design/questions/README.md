# Design Questions Index

This directory organizes design questions and decisions by category. Each file contains both **open questions** (still being explored) and **resolved decisions** (finalized, often with ADR references).

**Last reorganized**: 2026-01-25 (from monolithic OPEN_QUESTIONS.md)

---

## Quick Status Summary

| Category | File | Open | Resolved | Gaps |
|----------|------|------|----------|------|
| Learning | [learning.md](learning.md) | 5 | 5 | 0 |
| Memory | [memory.md](memory.md) | 3 | 1 | 1 |
| Plugins | [plugins.md](plugins.md) | 5 | 2 | 1 |
| Infrastructure | [infrastructure.md](infrastructure.md) | 2 | 1 | 1 |
| Data Types | [data-types.md](data-types.md) | 1 | 0 | 1 |
| Resource Allocation | [resource-allocation.md](resource-allocation.md) | 4 | 0 | 1 |
| Cross-Cutting | [cross-cutting.md](cross-cutting.md) | 8 | 3 | 2 |
| Bootstrapping | [confidence-bootstrapping.md](confidence-bootstrapping.md) | 0 | 1 | 0 |
| Feedback | [feedback-signal-decomposition.md](feedback-signal-decomposition.md) | 1 | 0 | 0 |
| Calibration | [user-feedback-calibration.md](user-feedback-calibration.md) | 1 | 0 | 0 |
| Analysis | [confidence-analysis-harness.md](confidence-analysis-harness.md) | 1 | 0 | 0 |
| Dashboard | [sensor-dashboard.md](sensor-dashboard.md) | 1 | 0 | 0 |
| PoC 1 Findings | [poc1-findings.md](poc1-findings.md) | 7 | 18 | 0 |
| Outcome Correlation | [outcome-correlation.md](outcome-correlation.md) | 2 | 0 | 0 |
| Urgency & Selection | [urgency-selection.md](urgency-selection.md) | 1 | 1 | 0 |
| Goal Identification | [goal-identification.md](goal-identification.md) | 1 | 0 | 0 |

**Legend**: Open = actively under discussion | Resolved = decision made (see ADR) | Gap = needs ADR

---

## Category Descriptions

### [learning.md](learning.md) - Heuristics, TD Learning, Pattern Formation
How GLADyS learns from experience. Includes heuristic matching, confidence updates, pattern extraction, and the TD learning loop.

**Key topics**:
- Heuristic data structure (CBR approach)
- TD learning for confidence updates
- Semantic matching via embeddings
- Prediction baselines for learning
- Credit assignment for feedback

### [memory.md](memory.md) - Storage, Schema, Semantic Memory
Database schema, memory hierarchy, entity/relationship storage, and architectural decisions about what goes where.

**Key topics**:
- ADR-0004 schema gaps and updates
- Semantic memory (entities + relationships)
- Graph DB vs relational decision

### [plugins.md](plugins.md) - Sensors, Skills, Actuators
Plugin architecture, integration models (Home Assistant), skill design patterns, and actuator safety.

**Key topics**:
- Actuator subsystem design
- Integration plugin model
- Skill architecture direction
- Plugin taxonomy (preprocessor vs query vs analyzer)

### [infrastructure.md](infrastructure.md) - Deployment, Latency, Operations
Deployment models, latency profiles, operational concerns, and code review action items.

**Key topics**:
- Latency profiles (realtime/conversational/comfort/background)
- Deployment model gaps
- Gemini code review action items

### [data-types.md](data-types.md) - Continuous vs Discrete Data
How to handle streaming sensor data (temperature, CO2) vs discrete events.

**Key topics**:
- Continuous data filtering strategies
- Metric vs event distinction

### [resource-allocation.md](resource-allocation.md) - Accuracy-Latency Tradeoff, Event Volume, Sensor Contract
How GLADyS allocates limited compute to maximize response quality and timeliness. Covers the accuracy-latency tension, dynamic heuristic behavior, concurrent event processing, and sensor event contract design.

**Key topics**:
- Accuracy-latency tradeoff (formal models, research areas)
- Dynamic heuristics (meta-heuristics, conditional suppression, event-response maps)
- Concurrent event processing (worker pools, async dispatch)
- Sensor event contract (JSON schema, driver→sensor→orchestrator interface)

### [cross-cutting.md](cross-cutting.md) - Integration, Audit, Output Routing
Topics that span multiple subsystems or don't fit cleanly elsewhere.

**Key topics**:
- Audit system design
- Output routing and user presence
- PoC vs ADR-0005 spec gaps
- Architectural gaps inventory

---

## File Structure

Each category file follows this format:

```markdown
# Category Name

## Open Questions
### Q: Short question title
**Status**: Open | Partial | In Progress
**Priority**: High | Medium | Low
**Created**: YYYY-MM-DD

[Question details, context, options considered...]

## Resolved
### R: Decision title
**Decision**: What was decided
**Rationale**: Why
**Date**: YYYY-MM-DD
**ADR**: ADR-00XX (if applicable)

[Details about the resolution...]
```

---

## How to Use

1. **Finding a topic**: Scan this README or use search in your editor
2. **Adding a new question**: Add to the appropriate category file under "Open Questions"
3. **Resolving a question**: Move from "Open Questions" to "Resolved" section, add date and rationale
4. **Creating an ADR**: When a question is significant enough, create an ADR and reference it

---

## Migration Notes

This structure was created from the original `OPEN_QUESTIONS.md` (2400+ lines). Section numbers (§1-§28) are preserved in the category files for historical reference.

The original file is archived at `OPEN_QUESTIONS.md.archive` and the main `OPEN_QUESTIONS.md` now redirects here.
