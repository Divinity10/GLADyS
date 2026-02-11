# Confidence Analysis Harness

**Created**: 2026-02-01
**Status**: Design needed
**Related**: ADR-0010 (Learning), feedback-signal-decomposition.md, user-feedback-calibration.md

## Problem

Confidence model weights (feedback stage multipliers, LLM endorsement weight, user calibration) are currently guessed. Tuning them requires replaying historical feedback against different weight models to compare outcomes.

## Questions to Resolve

- What data must be captured per feedback event to enable offline replay? (heuristic state at time of feedback, confidence before/after, feedback stage, user feedback ratio)
- What does "good outcome" mean for comparing models? (Heuristics fire/don't-fire at the right times? Confidence stabilizes faster?)
- Should this be a standalone CLI tool or integrated into the dashboard?
- Can we reuse the convergence test infrastructure?

## Scope

- **Phase 2**: Ensure data capture is sufficient for later replay
- **Phase 3+**: Build the harness, run first comparisons

