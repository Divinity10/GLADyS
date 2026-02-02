# Feedback Signal Decomposition

**Created**: 2026-02-01
**Status**: Design needed
**Related**: ADR-0010 (Learning), confidence-bootstrapping.md

## Problem

A like/dislike on a response conflates two independent signals:
1. **Match quality** — did the right heuristic fire for this event?
2. **Response quality** — was the response content appropriate?

A heuristic can match incorrectly but provide a useful response by coincidence. It can also match correctly but deliver a poor response.

## Questions to Resolve

- Should feedback update match confidence and response quality separately?
- Should confidence adjustments vary by feedback stage?
  - (a) First like that creates the heuristic (currently sets confidence to 0.3)
  - (b) First like on a heuristic-generated response (pattern confirmation)
  - (c) Subsequent likes (reinforcement)
  - Example curve: a→0.3, b→0.4, c→0.6, then +0.1 with cap
- What data do we need to capture now (PoC 2) to enable this analysis later?

## Dependencies

- Confidence analysis harness (see `confidence-analysis-harness.md`) — needed to evaluate different weight models offline
