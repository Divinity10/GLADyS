#!/usr/bin/env python3
"""
Script to validate heuristic extraction quality (Option B).
Simulates the LLM extraction step for diverse scenarios and generates a report.
"""

import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# The exact prompt from src/executive/stub_server.py
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
    expected_quality: str = "Good"  # Expectation for the test

SCENARIOS = [
    # 1. Gaming (Minecraft) - Clear pattern
    Scenario(
        id="MC-01",
        domain="Gaming",
        context="[minecraft-sensor]: Player health dropped to 3 hearts (15%) after creeper explosion. Nearby entities: [creeper, skeleton].",
        response="Watch out! You're critically low on health. Find shelter immediately.",
    ),
    # 2. Smart Home - Explicit user correction
    Scenario(
        id="HOME-01",
        domain="Smart Home",
        context="[home-assistant]: Living room lights set to 100% brightness. User immediately manually set to 50%.",
        response="Noted. I'll keep the lights dimmer in the future.",
    ),
    # 3. Productivity - Meeting reminder
    Scenario(
        id="WORK-01",
        domain="Productivity",
        context="[calendar-sensor]: 'Team Sync' starts in 5 minutes. User status: 'Idle' for 10 minutes.",
        response="You have a meeting starting soon, but you seem to be away. Should I notify you on your phone?",
    ),
    # 4. Social - Rare event
    Scenario(
        id="SOC-01",
        domain="Social",
        context="[discord-sensor]: User 'Steve' (friend) came online. Status: 'Playing Minecraft'. Last seen: 7 days ago.",
        response="Steve is online in Minecraft! He hasn't been on all week. Want to join him?",
    ),
    # 5. System - Resource usage
    Scenario(
        id="SYS-01",
        domain="System",
        context="[system-monitor]: RAM usage at 95%. Chrome using 4GB. VS Code using 2GB.",
        response="Your memory is nearly full. You might want to close some Chrome tabs.",
    ),
    # 6. Gaming (Generic) - Ambiguous
    Scenario(
        id="GAME-02",
        domain="Gaming",
        context="[game-sensor]: Level completed. Score: 5000. New high score.",
        response="Great job on the new high score!",
    ),
    # 7. Development - Error log
    Scenario(
        id="DEV-01",
        domain="Development",
        context="[vscode-sensor]: Build failed. Error: 'segmentation fault' in main.rs line 42.",
        response="Looks like a segfault in main.rs. Check your pointer arithmetic.",
    ),
    # 8. Negative Feedback Context (Simulated as positive for extraction)
    # The user *liked* that we stayed silent.
    Scenario(
        id="HOME-02",
        domain="Smart Home",
        context="[motion-sensor]: Motion detected in office at 2 AM. [glados]: (Silent).",
        response="(No response sent)",
    ),
]

def simulate_llm_extraction(prompt: str) -> str:
    """
    Simulates the LLM's response to the extraction prompt.
    In a real run, this would call Ollama.
    Here, I (the AI running this script) generate the JSON directly based on the logic.
    """
    # NOTE: As an AI agent executing this code, I cannot "call myself" recursively 
    # via a Python function easily without external API keys. 
    # Instead, I will use a placeholder mechanism or require manual input?
    # Actually, the instructions say "manually run... or document what you'd expect".
    # I will generate "synthetic" outputs that represent realistic LLM behavior 
    # (including potential flaws) to test the *evaluation* logic.
    
    # ... Wait, the prompt says "Your Task... Create a report". 
    # I should simply GENERATE the report content directly using my own reasoning 
    # right now, rather than writing a python script to do it. 
    # Writing a script to "simulate" me is redundant. 
    # I will proceed to generate the report directly.
    return ""

if __name__ == "__main__":
    print("This script is a placeholder. The agent will generate the report directly.")
