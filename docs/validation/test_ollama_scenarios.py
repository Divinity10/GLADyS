#!/usr/bin/env python3
"""
Reusable Ollama scenario testing framework.

Reads test scenarios from a JSON file, runs them through Ollama,
evaluates results against expected ranges, and reports pass/fail.

Usage:
    python test_ollama_scenarios.py <scenarios.json> [--output results.json]
"""

import json
import sys
import argparse
import requests
from dataclasses import dataclass
from typing import Optional
import time
from pathlib import Path

# Ollama configuration (from .env)
OLLAMA_URL = "http://100.120.203.91:11435/api/generate"
DEFAULT_MODEL = "qwen3-vl:8b"
DEFAULT_TIMEOUT = 180  # seconds


def call_ollama(prompt: str, model: str = DEFAULT_MODEL) -> tuple[str, float]:
    """Call Ollama and return response + elapsed time."""
    start = time.time()
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
        },
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    result = response.json()
    elapsed = time.time() - start
    return result.get("response", ""), elapsed


def parse_json_response(text: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()

    # Remove markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in the response
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return None


def check_in_range(value: float, expected: dict) -> tuple[bool, str]:
    """Check if value is within expected range."""
    min_val = expected.get("min", 0.0)
    max_val = expected.get("max", 1.0)

    if value < min_val:
        return False, f"{value:.2f} < {min_val:.2f} (too low)"
    if value > max_val:
        return False, f"{value:.2f} > {max_val:.2f} (too high)"
    return True, f"{value:.2f} in [{min_val:.2f}, {max_val:.2f}]"


def evaluate_result(parsed: dict, expected: dict) -> dict:
    """Evaluate parsed response against expected values."""
    evaluation = {
        "fields_checked": [],
        "all_passed": True,
    }

    for field, expected_range in expected.items():
        if field not in parsed:
            evaluation["fields_checked"].append({
                "field": field,
                "passed": False,
                "reason": "field missing from response",
            })
            evaluation["all_passed"] = False
            continue

        value = parsed[field]
        if not isinstance(value, (int, float)):
            evaluation["fields_checked"].append({
                "field": field,
                "passed": False,
                "reason": f"expected number, got {type(value).__name__}",
            })
            evaluation["all_passed"] = False
            continue

        passed, reason = check_in_range(float(value), expected_range)
        evaluation["fields_checked"].append({
            "field": field,
            "value": value,
            "passed": passed,
            "reason": reason,
        })
        if not passed:
            evaluation["all_passed"] = False

    return evaluation


def format_prompt(template: str, inputs: dict) -> str:
    """Format prompt template with scenario inputs."""
    return template.format(**inputs)


def run_scenario(scenario: dict, prompt_template: str, model: str) -> dict:
    """Run a single test scenario."""
    scenario_id = scenario.get("id", "UNKNOWN")
    domain = scenario.get("domain", "Unknown")
    inputs = scenario.get("inputs", {})
    expected = scenario.get("expected", {})
    rationale = scenario.get("rationale", "")

    print(f"\n{'='*60}")
    print(f"Scenario: {scenario_id} ({domain})")
    print(f"Rationale: {rationale}")

    result = {
        "scenario_id": scenario_id,
        "domain": domain,
        "rationale": rationale,
        "inputs": inputs,
        "expected": expected,
    }

    try:
        prompt = format_prompt(prompt_template, inputs)
        raw_response, elapsed = call_ollama(prompt, model)

        result["elapsed_seconds"] = elapsed
        result["raw_response"] = raw_response

        print(f"Time: {elapsed:.2f}s")

        parsed = parse_json_response(raw_response)
        if parsed is None:
            result["parse_success"] = False
            result["passed"] = False
            result["error"] = "Failed to parse JSON from response"
            print(f"FAIL: Could not parse JSON")
            print(f"Raw: {raw_response[:200]}...")
            return result

        result["parse_success"] = True
        result["parsed"] = parsed

        # Evaluate against expected ranges
        evaluation = evaluate_result(parsed, expected)
        result["evaluation"] = evaluation
        result["passed"] = evaluation["all_passed"]

        # Print results
        status = "PASS" if evaluation["all_passed"] else "FAIL"
        print(f"Status: {status}")
        for check in evaluation["fields_checked"]:
            checkmark = "[OK]" if check["passed"] else "[X]"
            print(f"  {checkmark} {check['field']}: {check['reason']}")

        if "reasoning" in parsed:
            print(f"LLM reasoning: {parsed['reasoning'][:100]}...")

    except requests.exceptions.Timeout:
        result["passed"] = False
        result["error"] = "Request timed out"
        print(f"FAIL: Timeout")
    except requests.exceptions.RequestException as e:
        result["passed"] = False
        result["error"] = f"Request failed: {e}"
        print(f"FAIL: {e}")
    except Exception as e:
        result["passed"] = False
        result["error"] = f"Unexpected error: {e}"
        print(f"FAIL: {e}")

    return result


def run_test_suite(test_file: Path, output_file: Optional[Path] = None):
    """Run all scenarios from a test file."""
    print(f"Loading test scenarios from: {test_file}")

    with open(test_file, "r") as f:
        test_suite = json.load(f)

    test_name = test_suite.get("test_name", "Unnamed Test")
    model = test_suite.get("model", DEFAULT_MODEL)
    prompt_template = test_suite.get("prompt_template", "")
    scenarios = test_suite.get("scenarios", [])

    print(f"\n{'='*60}")
    print(f"Test Suite: {test_name}")
    print(f"Model: {model}")
    print(f"Scenarios: {len(scenarios)}")
    print(f"{'='*60}")

    if not prompt_template:
        print("ERROR: No prompt_template defined in test file")
        sys.exit(1)

    results = []
    for scenario in scenarios:
        result = run_scenario(scenario, prompt_template, model)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    passed = sum(1 for r in results if r.get("passed"))
    failed = len(results) - passed

    print(f"Passed: {passed}/{len(results)}")
    print(f"Failed: {failed}/{len(results)}")

    if results:
        avg_time = sum(r.get("elapsed_seconds", 0) for r in results) / len(results)
        print(f"Avg response time: {avg_time:.2f}s")

    print("\nResults by scenario:")
    for r in results:
        status = "PASS" if r.get("passed") else "FAIL"
        print(f"  [{status}] {r['scenario_id']}: {r.get('rationale', '')[:50]}")

    # Save results
    output = {
        "test_name": test_name,
        "model": model,
        "total_scenarios": len(results),
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / len(results) if results else 0,
        "results": results,
    }

    if output_file is None:
        # Default output path: same name as input with _results suffix
        output_file = test_file.parent / f"{test_file.stem}_results.json"

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {output_file}")

    # Return exit code based on results
    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="Run Ollama scenario tests from a JSON file"
    )
    parser.add_argument(
        "test_file",
        type=Path,
        help="Path to JSON file containing test scenarios"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output file for results (default: <test_file>_results.json)"
    )

    args = parser.parse_args()

    if not args.test_file.exists():
        print(f"ERROR: Test file not found: {args.test_file}")
        sys.exit(1)

    exit_code = run_test_suite(args.test_file, args.output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
