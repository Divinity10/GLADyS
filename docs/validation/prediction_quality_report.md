# Validation Report: Prediction Quality (LLM Calibration)

**Date**: 2026-01-24
**Model**: qwen3-vl:8b (Ollama)
**Test Framework**: `test_ollama_scenarios.py`

## Overview

This test validates whether the LLM can produce reasonable outcome predictions and calibrated confidence levels for use in the "Instrument Now, Analyze Later" strategy (§27).

**Overall Assessment**: **PASS (7/8 = 87.5%)**

The LLM produces usable predictions with one notable weakness: **overconfidence in ambiguous situations**.

## Results Summary

| ID | Domain | Expected Prediction | Actual | Expected Confidence | Actual | Status |
|----|--------|---------------------|--------|---------------------|--------|--------|
| PRED-01 | Gaming | 0.70-0.99 | 0.95 | 0.55-0.95 | 0.90 | PASS |
| PRED-02 | Productivity | 0.65-0.95 | 0.90 | 0.50-0.90 | 0.90 | PASS |
| PRED-03 | Gaming | 0.00-0.25 | 0.00 | 0.60-0.95 | 0.90 | PASS |
| PRED-04 | Smart Home | 0.00-0.30 | 0.00 | 0.65-0.95 | 0.90 | PASS |
| PRED-05 | Gaming | 0.25-0.75 | 0.30 | 0.15-0.50 | 0.30 | **PASS** |
| PRED-06 | Productivity | 0.30-0.75 | 0.90 | 0.25-0.60 | 0.90 | **FAIL** |
| PRED-07 | Productivity | 0.60-0.90 | 0.90 | 0.45-0.80 | 0.80 | PASS |
| PRED-08 | Social | 0.70-0.95 | 0.95 | 0.60-0.90 | 0.90 | PASS |

## Key Findings

### 1. Calibration Works for Clear Cases

When the situation is unambiguous, the LLM correctly produces:
- **High confidence + high probability** for likely success (PRED-01, 02, 07, 08)
- **High confidence + low probability** for likely failure (PRED-03, 04)

### 2. Calibration Works for Uncertainty (PRED-05)

The LLM correctly expressed uncertainty for an unknown enemy:
- Prediction: 0.30 (conservative, acknowledging uncertainty)
- Confidence: 0.30 (appropriately low)

This demonstrates the LLM *can* express "I don't know" - it just doesn't do so consistently.

### 3. Overconfidence Confirmed (PRED-06)

The LLM was overconfident about an ambiguous situation:
- **Context**: User away 15 min, meeting in 20 min, no location info
- **Expected**: Medium uncertainty (0.30-0.75 prediction, 0.25-0.60 confidence)
- **Actual**: High confidence (0.90/0.90)
- **LLM Reasoning**: "The user will be back 5 minutes before the meeting"

The LLM made an **optimistic assumption** rather than acknowledging uncertainty about:
- Whether "away 15 minutes" means they'll return in 15 minutes
- Where the user actually is
- Whether they'll see the notification in time

### 4. JSON Compliance: 100%

All 8 scenarios returned parseable JSON, validating the prompt structure.

## Implications for Design

| Finding | Design Decision |
|---------|-----------------|
| Overconfidence in ambiguity | Use System 1 baseline (historical data), not LLM confidence |
| Calibration works when obvious | LLM predictions are useful data, worth collecting |
| Can express uncertainty | Not a fundamental limitation, may improve with prompt tuning |

## Validates §27 Decisions

1. **Hybrid baseline hierarchy** - LLM confidence is one signal, not the source of truth
2. **Instrument Now** - Predictions are useful to collect even if we don't act on them
3. **Gemini's warning** - LLM overconfidence is a real issue requiring mitigation

## Files

- **Test script**: `docs/validation/test_ollama_scenarios.py`
- **Scenarios**: `docs/validation/prediction_quality_scenarios.json`
- **Results**: `docs/validation/prediction_quality_scenarios_results.json`

## Recommendation

Proceed with adding prediction/confidence fields to the reasoning prompt. The data is useful for analysis even with the known overconfidence limitation.
