# Integration Test Scenarios (Option C)

**Date**: 2026-01-24
**Topic**: Validation of the Full Learning Loop (System 2 → System 1 Handoff)

## Overview
These scenarios validate the "Killer Feature": the ability of the system to learn from LLM reasoning and user feedback, converting slow, expensive reasoning into fast, cheap heuristics.

Each scenario assumes the PoC environment is running (Python Memory, Rust Salience, Executive Stub).

---

## Configuration Note: Confidence Threshold
The default confidence threshold for cache hits is assumed to be **0.5**.
Tests should ideally read this value from the system configuration (e.g., `HEURISTIC_CONFIDENCE_THRESHOLD`) rather than hardcoding it, to ensure consistency with the environment.

---

## Scenario 1: The "Happy Path" Learning Loop
**Goal**: Prove the system learns a new heuristic from a novel event and positive feedback.

*   **Initial State**:
    *   Memory is empty (no heuristics).
*   **Step 1 (Novel Event)**:
    *   Send Event: `[minecraft] Player health 10% after skeleton arrow.`
    *   **Expect**: Cache Miss -> LLM Reasoning -> Response ("Hide/Heal").
*   **Step 2 (Feedback)**:
    *   Send Feedback: `Positive` for Step 1 response.
    *   **Expect**: Background job extracts pattern `condition="low health combat"`, stores Heuristic H1 (conf=0.3).
*   **Step 3 (Reinforcement)**:
    *   Send Event (Same): `[minecraft] Player health 10%...`
    *   **Expect**: **Cache Miss** (Confidence 0.3 < Threshold 0.5) -> LLM Reasoning.
    *   Send Feedback: `Positive`.
    *   **Expect**: H1 confidence increases to ~0.4.
*   **Step 4 (Validation)**:
    *   Manually boost H1 confidence to 0.6 (to skip grinding).
    *   Send Event (Same): `[minecraft] Player health 10%...`
    *   **Expect**: **Cache Hit** (Fast Path). Response matches H1 action.

---

## Scenario 2: The "Correction" Loop (Unlearning)
**Goal**: Prove the system stops using a bad heuristic after negative feedback.

*   **Initial State**:
    *   Heuristic H2 exists: `condition="night time"`, `action="turn on lights"`, `confidence=0.6`.
*   **Step 1 (Bad Action)**:
    *   Send Event: `[home] It is 2 AM.`
    *   **Expect**: Cache Hit (H2) -> Action "Turn on lights".
*   **Step 2 (Correction)**:
    *   Send Feedback: `Negative` (User undo/complain).
    *   **Expect**: H2 confidence drops (e.g., 0.6 -> 0.45).
*   **Step 3 (Verification)**:
    *   Send Event: `[home] It is 3 AM.`
    *   **Expect**: **Cache Miss** (Confidence 0.45 < Threshold 0.5). Fallback to LLM.

---

## Scenario 3: Fuzzy Matching (Generalization)
**Goal**: Prove embedding-based matching works for semantically similar (but textually distinct) events.

*   **Initial State**:
    *   Heuristic H3 exists: `condition="player died in lava"`, `confidence=0.9`.
*   **Step 1 (Semantically Similar Event)**:
    *   Send Event: `[minecraft] Character fell into magma pool and perished.`
    *   *Note*: No shared words with condition except "into". Relying on vector similarity ("magma"~"lava", "perished"~"died").
*   **Expect**:
    *   **Cache Hit** (Fast Path).
    *   Log shows `similarity > 0.8`.

---

## Scenario 4: Domain Safety (Prefix Separation)
**Goal**: Ensure heuristics are scoped to their domain via condition prefixes.

*   **Initial State**:
    *   Heuristic H4 exists: `condition="gaming: high score achieved"`, `confidence=0.8`.
*   **Step 1 (Cross-Domain Event)**:
    *   Send Event: `[work] Credit Score report: 800.`
*   **Expect**:
    *   **Cache Miss**.
    *   Even if "Credit Score 800" is semantically similar to "high score", the "gaming:" vs "work:" prefixes in the embedding space should ensure sufficient distance to prevent a match.

---

## Scenario 5: Confidence Clamping & Saturation
**Goal**: Verify mathematical stability of the learning algorithm.

*   **Initial State**:
    *   Heuristic H5 exists with `confidence=0.95`.
*   **Step 1 (Saturation)**:
    *   Send Positive Feedback for H5.
    *   **Expect**: Confidence becomes `1.0` (not 1.05).
*   **Step 2 (Clamping)**:
    *   Heuristic H6 exists with `confidence=0.05`.
    *   Send Negative Feedback for H6.
    *   **Expect**: Confidence becomes `0.0` (not -0.05).

---

## Scenario 6: Ambiguous Attribution (Credit/Blame Assignment)
**Goal**: Define how feedback is distributed when multiple heuristics fire in close proximity.

*   **Initial State**:
    *   H7 (`gaming: low health`) and H8 (`gaming: skeleton nearby`) both fired within the last 30 seconds.
*   **Step 1 (Feedback Event)**:
    *   Send Feedback: `Positive` for the recent sequence.
*   **Expect**:
    *   Both H7 and H8 receive a confidence boost.
    *   *Implementation Detail*: Credit/Blame is distributed equally or weighted by recency/contribution (to be defined in implementation, but both must be affected).

---

## Scenario 7: Instrumentation (Data Capture Verification)
**Goal**: Verify that predictions are recorded even before the system acts on them (Instrument Now, Analyze Later).

*   **Step 1 (Novel Event requiring LLM)**:
    *   Send Event: `[smart_home] Temperature rose 5 degrees in 10 minutes.`
*   **Expect**:
    *   LLM processes the event.
    *   Verify that the resulting episode/response in Memory contains `predicted_success` and `prediction_confidence` fields.
    *   No behavioral change required, only verification of data capture.

---

## Implementation Plan
1.  Use `src/integration/test_scenario_5_learning_loop.py` as the driver.
2.  Mock the LLM for predictability (or use the Stub if stable) for Scenarios 1 & 2.
3.  Directly manipulate the DB for "Initial States" (inject heuristics).
4.  Assert on the `from_cache` flag in the `EvaluateSalienceResponse`.
