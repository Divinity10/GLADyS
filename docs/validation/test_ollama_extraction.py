#!/usr/bin/env python3
"""
Test heuristic extraction quality with actual Ollama calls.
"""

import json
import requests
from dataclasses import dataclass
from typing import Optional
import time

OLLAMA_URL = "http://100.120.203.91:11435/api/generate"
MODEL = "qwen3-vl:8b"

PATTERN_EXTRACTION_PROMPT = """You just helped with this situation:

Context: {context}
Your response: {response}
User feedback: positive

Extract a generalizable heuristic that can be applied to similar situations in the future.
- condition: A general description of when this pattern applies (avoid specific names/numbers)
- action: What to do when the condition matches

Be general enough to match similar situations, specific enough to be useful.
Output ONLY valid JSON with no other text: {{"condition": "...", "action": {{"type": "...", "message": "..."}}}}"""


@dataclass
class Scenario:
    id: str
    domain: str
    context: str
    response: str


SCENARIOS = [
    Scenario(
        id="MC-01",
        domain="Gaming",
        context="[minecraft-sensor]: Player health dropped to 3 hearts (15%) after creeper explosion. Nearby entities: [creeper, skeleton].",
        response="Watch out! You're critically low on health. Find shelter immediately.",
    ),
    Scenario(
        id="HOME-01",
        domain="Smart Home",
        context="[home-assistant]: Living room lights set to 100% brightness. User immediately manually set to 50%.",
        response="Noted. I'll keep the lights dimmer in the future.",
    ),
    Scenario(
        id="WORK-01",
        domain="Productivity",
        context="[calendar-sensor]: 'Team Sync' starts in 5 minutes. User status: 'Idle' for 10 minutes.",
        response="You have a meeting starting soon, but you seem to be away. Should I notify you on your phone?",
    ),
    Scenario(
        id="SOC-01",
        domain="Social",
        context="[discord-sensor]: User 'Steve' (friend) came online. Status: 'Playing Minecraft'. Last seen: 7 days ago.",
        response="Steve is online in Minecraft! He hasn't been on all week. Want to join him?",
    ),
    Scenario(
        id="SYS-01",
        domain="System",
        context="[system-monitor]: RAM usage at 95%. Chrome using 4GB. VS Code using 2GB.",
        response="Your memory is nearly full. You might want to close some Chrome tabs.",
    ),
    Scenario(
        id="GAME-02",
        domain="Gaming",
        context="[game-sensor]: Level completed. Score: 5000. New high score.",
        response="Great job on the new high score!",
    ),
    Scenario(
        id="DEV-01",
        domain="Development",
        context="[vscode-sensor]: Build failed. Error: 'segmentation fault' in main.rs line 42.",
        response="Looks like a segfault in main.rs. Check your pointer arithmetic.",
    ),
    Scenario(
        id="HOME-02",
        domain="Smart Home",
        context="[motion-sensor]: Motion detected in office at 2 AM. [glados]: (Silent).",
        response="(No response sent)",
    ),
]


def call_ollama(prompt: str) -> tuple[str, float]:
    """Call Ollama and return response + time taken."""
    start = time.time()
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    result = response.json()
    elapsed = time.time() - start
    return result.get("response", ""), elapsed


def parse_json_response(text: str) -> Optional[dict]:
    """Try to extract JSON from LLM response."""
    text = text.strip()
    # Remove markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON in the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                return None
    return None


def run_test(scenario: Scenario) -> dict:
    """Run extraction test for a single scenario."""
    prompt = PATTERN_EXTRACTION_PROMPT.format(
        context=scenario.context,
        response=scenario.response,
    )

    print(f"\n{'='*60}")
    print(f"Testing {scenario.id} ({scenario.domain})")
    print(f"Context: {scenario.context[:80]}...")

    try:
        raw_response, elapsed = call_ollama(prompt)
        parsed = parse_json_response(raw_response)

        print(f"Time: {elapsed:.2f}s")
        print(f"Raw response: {raw_response[:200]}...")

        if parsed:
            print(f"Condition: {parsed.get('condition', 'N/A')}")
            print(f"Action: {parsed.get('action', 'N/A')}")
        else:
            print("FAILED TO PARSE JSON")

        return {
            "scenario_id": scenario.id,
            "domain": scenario.domain,
            "raw_response": raw_response,
            "parsed": parsed,
            "elapsed_seconds": elapsed,
            "success": parsed is not None,
        }
    except Exception as e:
        print(f"ERROR: {e}")
        return {
            "scenario_id": scenario.id,
            "domain": scenario.domain,
            "error": str(e),
            "success": False,
        }


def main():
    print("Heuristic Extraction Quality Test")
    print(f"Model: {MODEL}")
    print(f"Scenarios: {len(SCENARIOS)}")

    results = []
    for scenario in SCENARIOS:
        result = run_test(scenario)
        results.append(result)

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    success_count = sum(1 for r in results if r.get("success"))
    print(f"Success rate: {success_count}/{len(results)}")

    avg_time = sum(r.get("elapsed_seconds", 0) for r in results) / len(results)
    print(f"Avg response time: {avg_time:.2f}s")

    print("\nExtracted Conditions:")
    for r in results:
        if r.get("parsed"):
            cond = r["parsed"].get("condition", "N/A")
            print(f"  {r['scenario_id']}: {cond}")
        else:
            print(f"  {r['scenario_id']}: FAILED")

    # Save results
    with open("docs/validation/ollama_extraction_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nResults saved to docs/validation/ollama_extraction_results.json")


if __name__ == "__main__":
    main()
