# User Feedback Calibration

**Created**: 2026-02-01
**Status**: Design needed
**Related**: ADR-0010 (Learning), feedback-signal-decomposition.md

## Problem

Users have different feedback biases. Some approve most responses; others reject most. A neutral default prior means the first N feedback events are noisy — the system can't distinguish "user rejects everything" from "this heuristic is bad."

## Questions to Resolve

- Does a short initial calibration questionnaire reduce the feedback events needed to reach stable confidence scores?
- What would the questionnaire measure? (Feedback tendency, risk tolerance, domain expertise?)
- Should the system also learn calibration passively from accumulated feedback ratios?
- How to limit questionnaire frequency to avoid user fatigue?

## Approach

Two complementary strategies:

1. **Initial calibration**: Short questionnaire at onboarding to set a prior on the user's feedback bias
2. **Ongoing calibration**: Track positive/negative feedback ratio per user, adjust signal weights accordingly (no questionnaire needed)

## Dependencies

- Sufficient feedback volume to validate whether calibration improves outcomes
- Confidence analysis harness for offline comparison of calibrated vs uncalibrated models
