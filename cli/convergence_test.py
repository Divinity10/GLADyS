#!/usr/bin/env python3
"""GLADyS PoC 1 Convergence Test — "the second time is faster."

Exercises the full closed loop:
1. Event → no heuristic → LLM responds
2. Positive feedback → heuristic created
3. Similar event → heuristic fires → fast response (no LLM)
4. Implicit feedback → confidence increases
5. Cross-domain: sudoku heuristic does NOT fire on melvor event

Usage:
    uv run cli/convergence_test.py
    uv run cli/convergence_test.py --env docker
"""

import argparse
import sys
import time
import uuid
from pathlib import Path

# Add paths for library imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "lib" / "gladys_client"))
sys.path.insert(0, str(ROOT / "src" / "lib" / "gladys_common"))
sys.path.insert(0, str(ROOT / "src" / "services" / "orchestrator"))

import grpc
from gladys_client.db import get_dsn, list_fires, list_heuristics
from gladys_client.health import check_health
from gladys_common.logging import get_logger, setup_logging
from gladys_orchestrator.generated import (
    common_pb2,
    executive_pb2,
    executive_pb2_grpc,
    orchestrator_pb2_grpc,
)

# -- Port configuration --------------------------------------------------

PORTS = {
    "local": {
        "orchestrator": 50050,
        "memory": 50051,
        "salience": 50052,
        "executive": 50053,
        "db": 5432,
    },
    "docker": {
        "orchestrator": 50060,
        "memory": 50061,
        "salience": 50062,
        "executive": 50063,
        "db": 5433,
    },
}

# ANSI helpers
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

logger = None  # initialised in main()


class StepFailed(Exception):
    """Raised when a test step fails."""

    def __init__(self, step: int, expected: str, actual: str):
        self.step = step
        self.expected = expected
        self.actual = actual
        super().__init__(f"Step {step}: expected {expected}, got {actual}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _addr(host: str, port: int) -> str:
    return f"{host}:{port}"


def _publish_event(stub, event_id: str, source: str, raw_text: str):
    """Publish one event via the streaming RPC and return the full EventAck."""

    def gen():
        yield common_pb2.Event(id=event_id, source=source, raw_text=raw_text)

    for ack in stub.PublishEvents(gen()):
        return ack
    return None


def _get_heuristic_by_id(dsn: str, heuristic_id: str) -> dict | None:
    """Query a single heuristic by ID."""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, condition, action, confidence, fire_count, "
            "success_count, frozen, origin, created_at, updated_at "
            "FROM heuristics WHERE id = %s",
            [heuristic_id],
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_fires_for_heuristic(dsn: str, heuristic_id: str) -> list[dict]:
    """Get fire records for a specific heuristic."""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, heuristic_id, event_id, fired_at, outcome, "
            "feedback_source, feedback_at, episodic_event_id "
            "FROM heuristic_fires WHERE heuristic_id = %s "
            "ORDER BY fired_at DESC",
            [heuristic_id],
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test steps
# ---------------------------------------------------------------------------

def step_01_health_check(ports: dict) -> None:
    """Check all four services are healthy."""
    services = {
        "Orchestrator": ports["orchestrator"],
        "Memory": ports["memory"],
        "Salience": ports["salience"],
        "Executive": ports["executive"],
    }
    for name, port in services.items():
        result = check_health(_addr("localhost", port))
        status = result.get("status", "UNKNOWN")
        if status not in ("HEALTHY", "SERVING"):
            raise StepFailed(1, f"{name} HEALTHY", f"{name} {status} ({result})")
        logger.debug("health_ok", service=name, port=port)


def step_02_submit_first_event(orch_stub) -> dict:
    """Submit sudoku event — expect LLM route (no heuristic)."""
    event_id = str(uuid.uuid4())
    ack = _publish_event(
        orch_stub,
        event_id=event_id,
        source="sensor:puzzle:sudoku",
        raw_text=(
            "The player is looking at a sudoku cell in row 3, column 5. "
            "Only one candidate remains: the number 7. This is a naked "
            "single — the cell can only be 7."
        ),
    )
    if ack is None:
        raise StepFailed(2, "EventAck received", "no ack returned")
    if not ack.routed_to_llm:
        raise StepFailed(2, "routed_to_llm=True", f"routed_to_llm={ack.routed_to_llm}")
    if not ack.response_text:
        raise StepFailed(2, "non-empty response_text", "empty response_text")

    logger.info("first_event_ok",
                event_id=event_id,
                response_id=ack.response_id,
                routed_to_llm=ack.routed_to_llm)
    return {
        "event_id": event_id,
        "response_id": ack.response_id,
        "response_text": ack.response_text,
    }


def step_03_submit_feedback(exec_stub, event_id: str, response_id: str) -> str:
    """Submit positive feedback — expect heuristic creation."""
    req = executive_pb2.ProvideFeedbackRequest(
        event_id=event_id,
        response_id=response_id,
        positive=True,
    )
    resp = exec_stub.ProvideFeedback(req)

    if not resp.accepted:
        raise StepFailed(3, "accepted=True", f"accepted=False, error={resp.error_message}")
    if not resp.created_heuristic_id:
        raise StepFailed(3, "created_heuristic_id non-empty", "empty created_heuristic_id")

    logger.info("feedback_ok", heuristic_id=resp.created_heuristic_id)
    return resp.created_heuristic_id


def step_04_verify_heuristic(dsn: str, heuristic_id: str) -> None:
    """Verify heuristic exists in DB with expected values."""
    h = _get_heuristic_by_id(dsn, heuristic_id)
    if h is None:
        raise StepFailed(4, "heuristic found in DB", "not found")
    if h["origin"] != "learned":
        raise StepFailed(4, "origin=learned", f"origin={h['origin']}")

    confidence = float(h["confidence"])
    if abs(confidence - 0.3) > 0.01:
        raise StepFailed(4, "confidence=0.3", f"confidence={confidence}")

    # Check condition_text quality
    import json
    condition = h["condition"]
    if isinstance(condition, str):
        condition = json.loads(condition)
    condition_text = condition.get("text", "")
    word_count = len(condition_text.split())
    if not (10 <= word_count <= 50):
        raise StepFailed(4, "condition_text 10-50 words",
                         f"condition_text {word_count} words: {condition_text!r}")

    logger.info("heuristic_verified",
                origin=h["origin"],
                confidence=confidence,
                condition_text=condition_text[:80])


def step_05_wait_cache_invalidation() -> None:
    """Wait for cache invalidation to propagate."""
    time.sleep(2)


def step_06_submit_similar_event(orch_stub, expected_heuristic_id: str) -> dict:
    """Submit similar sudoku event — expect heuristic match, no LLM."""
    event_id = str(uuid.uuid4())
    t0 = time.monotonic()
    ack = _publish_event(
        orch_stub,
        event_id=event_id,
        source="sensor:puzzle:sudoku",
        raw_text=(
            "In the current sudoku puzzle, row 7 column 2 has been narrowed "
            "down to a single possibility: 4. This naked single means the "
            "answer is determined."
        ),
    )
    latency_ms = (time.monotonic() - t0) * 1000

    if ack is None:
        raise StepFailed(6, "EventAck received", "no ack returned")
    if ack.matched_heuristic_id != expected_heuristic_id:
        raise StepFailed(
            6,
            f"matched_heuristic_id={expected_heuristic_id}",
            f"matched_heuristic_id={ack.matched_heuristic_id!r} "
            f"(routed_to_llm={ack.routed_to_llm})",
        )
    if ack.routed_to_llm:
        raise StepFailed(6, "routed_to_llm=False", "routed_to_llm=True")
    if latency_ms > 100:
        raise StepFailed(6, "latency < 100ms", f"latency={latency_ms:.0f}ms")

    logger.info("second_event_ok",
                event_id=event_id,
                matched=ack.matched_heuristic_id,
                latency_ms=round(latency_ms))
    return {"event_id": event_id, "latency_ms": latency_ms}


def step_07_verify_fire(dsn: str, heuristic_id: str) -> None:
    """Verify a fire record was created."""
    fires = _get_fires_for_heuristic(dsn, heuristic_id)
    if not fires:
        raise StepFailed(7, "fire record exists", "no fires found")
    logger.info("fire_verified", fire_id=fires[0]["id"], outcome=fires[0].get("outcome"))


def step_08_wait_implicit_feedback(dsn: str, heuristic_id: str,
                                   outcome_timeout: int) -> None:
    """Wait for implicit feedback (timeout-based positive signal).

    The outcome watcher expires pending expectations after outcome_timeout
    seconds, then the cleanup loop (every 30s) sends timeout-positive
    feedback. We wait long enough for both to complete.

    For fast testing, start orchestrator with OUTCOME_TIMEOUT_SEC=10
    OUTCOME_CLEANUP_INTERVAL_SEC=5 and pass --outcome-timeout 10.
    """
    fires = _get_fires_for_heuristic(dsn, heuristic_id)
    if not fires:
        raise StepFailed(8, "fire record exists for implicit feedback check", "no fires")

    latest = fires[0]
    outcome = latest.get("outcome")

    if outcome and outcome != "unknown":
        logger.info("implicit_feedback_already_resolved", outcome=outcome)
        return

    # Wait for: outcome timeout + cleanup interval + margin
    # Cleanup interval defaults to 30s; we add margin for scheduling jitter.
    wait_sec = outcome_timeout + 35
    logger.info("waiting_for_implicit_feedback",
                outcome_timeout=outcome_timeout, total_wait=wait_sec)

    # Poll periodically rather than blocking the full duration
    poll_interval = 5
    elapsed = 0
    while elapsed < wait_sec:
        time.sleep(poll_interval)
        elapsed += poll_interval

        fires = _get_fires_for_heuristic(dsn, heuristic_id)
        latest = fires[0]
        outcome = latest.get("outcome")
        if outcome and outcome not in ("unknown", None):
            logger.info("implicit_feedback_resolved",
                        outcome=outcome, elapsed_sec=elapsed)
            return

    raise StepFailed(8, "implicit feedback resolved within timeout",
                     f"outcome still '{outcome}' after {wait_sec}s")


def step_09_verify_confidence(dsn: str, heuristic_id: str) -> None:
    """Verify confidence increased from initial 0.3."""
    h = _get_heuristic_by_id(dsn, heuristic_id)
    if h is None:
        raise StepFailed(9, "heuristic found", "not found")

    confidence = float(h["confidence"])
    fire_count = h.get("fire_count", 0)

    if fire_count < 1:
        raise StepFailed(9, "fire_count >= 1", f"fire_count={fire_count}")
    if confidence <= 0.3:
        raise StepFailed(9, "confidence > 0.3", f"confidence={confidence}")

    logger.info("confidence_increased", confidence=confidence, fire_count=fire_count)


def step_10_cross_domain(orch_stub, sudoku_heuristic_id: str) -> None:
    """Submit melvor event — sudoku heuristic should NOT fire."""
    event_id = str(uuid.uuid4())
    ack = _publish_event(
        orch_stub,
        event_id=event_id,
        source="sensor:gaming:melvor",
        raw_text=(
            "The player's health dropped to 25% during combat with a dragon. "
            "Food is available in inventory."
        ),
    )
    if ack is None:
        raise StepFailed(10, "EventAck received", "no ack returned")

    if ack.matched_heuristic_id == sudoku_heuristic_id:
        raise StepFailed(
            10,
            "sudoku heuristic did NOT fire on melvor event",
            f"matched_heuristic_id={ack.matched_heuristic_id}",
        )
    logger.info("cross_domain_ok",
                matched=ack.matched_heuristic_id or "(none)",
                routed_to_llm=ack.routed_to_llm)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global logger

    parser = argparse.ArgumentParser(description="GLADyS PoC 1 Convergence Test")
    parser.add_argument("--env", choices=["local", "docker"], default="local",
                        help="Environment to test against (default: local)")
    parser.add_argument("--outcome-timeout", type=int, default=120,
                        help="Outcome timeout in seconds (must match orchestrator's "
                             "OUTCOME_TIMEOUT_SEC). Lower values make step 8/9 faster.")
    args = parser.parse_args()

    setup_logging("convergence-test")
    logger = get_logger()

    ports = PORTS[args.env]
    dsn = get_dsn(ports["db"])
    orch_addr = _addr("localhost", ports["orchestrator"])
    exec_addr = _addr("localhost", ports["executive"])

    orch_channel = grpc.insecure_channel(orch_addr)
    orch_stub = orchestrator_pb2_grpc.OrchestratorServiceStub(orch_channel)

    exec_channel = grpc.insecure_channel(exec_addr)
    exec_stub = executive_pb2_grpc.ExecutiveServiceStub(exec_channel)

    # State carried between steps
    state = {}

    print(f"\n{BOLD}=== GLADyS PoC 1 Convergence Test (env={args.env}) ==={RESET}\n")

    passed = 0
    total = 10

    def run_step(num: int, label: str, fn):
        nonlocal passed
        try:
            result = fn()
            passed += 1
            print(f"  {GREEN}[{num:>2}/10] {label}... PASS{RESET}")
            return result
        except StepFailed as e:
            print(f"  {RED}[{num:>2}/10] {label}... FAIL{RESET}")
            print(f"         Expected: {e.expected}")
            print(f"         Actual:   {e.actual}")
            return None
        except Exception as e:
            print(f"  {RED}[{num:>2}/10] {label}... ERROR{RESET}")
            print(f"         {type(e).__name__}: {e}")
            return None

    # Step 1
    result = run_step(1, "Health check all services", lambda: step_01_health_check(ports))
    if result is None and passed == 0:
        print(f"\n{RED}Services not healthy. Aborting.{RESET}")
        sys.exit(1)

    # Step 2
    s2 = run_step(2, "Submit sudoku event (first time)", lambda: step_02_submit_first_event(orch_stub))
    if s2 is None:
        print(f"\n{RED}Cannot continue without first event. Aborting.{RESET}")
        sys.exit(1)
    state.update(s2)

    # Step 3
    heur_id = run_step(3, "Submit positive feedback",
                       lambda: step_03_submit_feedback(exec_stub, state["event_id"], state["response_id"]))
    if heur_id is None:
        print(f"\n{RED}Cannot continue without heuristic. Aborting.{RESET}")
        sys.exit(1)
    state["heuristic_id"] = heur_id

    # Step 4
    run_step(4, "Verify heuristic in DB",
             lambda: step_04_verify_heuristic(dsn, state["heuristic_id"]))

    # Step 5
    run_step(5, "Wait for cache invalidation",
             lambda: step_05_wait_cache_invalidation())

    # Step 6
    s6 = run_step(6, "Submit similar event (second time)",
                  lambda: step_06_submit_similar_event(orch_stub, state["heuristic_id"]))

    # Step 7
    run_step(7, "Verify fire recorded",
             lambda: step_07_verify_fire(dsn, state["heuristic_id"]))

    # Step 8
    run_step(8, "Wait for implicit feedback",
             lambda: step_08_wait_implicit_feedback(dsn, state["heuristic_id"],
                                                    args.outcome_timeout))

    # Step 9
    run_step(9, "Verify confidence increased",
             lambda: step_09_verify_confidence(dsn, state["heuristic_id"]))

    # Step 10
    run_step(10, "Cross-domain specificity check",
             lambda: step_10_cross_domain(orch_stub, state["heuristic_id"]))

    # Cleanup
    orch_channel.close()
    exec_channel.close()

    # Summary
    print()
    if passed == total:
        print(f"{BOLD}{GREEN}=== RESULT: {passed}/{total} PASSED ==={RESET}")
        print(f"{GREEN}PoC 1 convergence test SUCCEEDED. The second time IS faster.{RESET}")
    else:
        print(f"{BOLD}{RED}=== RESULT: {passed}/{total} PASSED ==={RESET}")
        print(f"{RED}PoC 1 convergence test FAILED.{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
