#!/usr/bin/env python3
"""Claude Code hook: detect !think, !plan, !do, !review, !archive prefixes.

UserPromptSubmit hook that injects mode-specific instructions based on
message prefixes. Configured in .claude/settings.json.

Modes:
    !think   - Critical analysis, no code. Explore tradeoffs, identify gaps.
    !plan    - Break down into steps, get approval before implementing.
    !do      - Execute. Implementation mode, minimal discussion.
    !review  - Evaluate existing code/design. Be thorough and constructive.
    (none)   - Light reminder to consider approach before jumping to code.
"""
import json
import sys
import re

MEMORY_REMINDER = (
    "\n\nMEMORY: If you make a decision, discovery, or complete a task, "
    "update claude_memory.md before moving on."
)

MODES = {
    "think": (
        "MODE: THINK -Critical analysis only. Do NOT write or edit code.\n"
        "- Explore the problem from multiple angles before proposing anything\n"
        "- Identify assumptions, blind spots, and failure modes\n"
        "- Surface tradeoffs explicitly -every option has costs\n"
        "- Reference specific project files/ADRs to ground your reasoning\n"
        "- If you don't have enough context, say so and ask\n"
        "- Output: analysis and recommendations, NOT implementation"
    ),
    "plan": (
        "MODE: PLAN -Design the approach, do NOT implement yet.\n"
        "\n"
        "PLANNING PHASE (present to user for approval):\n"
        "1. Read current code -verify assumptions match reality before proposing anything\n"
        "2. Break into phases with clear scope and checkpoint criteria per phase\n"
        "3. Identify which files will be touched and why\n"
        "4. Call out risks, dependencies, and open questions\n"
        "5. Consider at least one alternative approach\n"
        "6. Present the plan for approval before writing any code\n"
        "\n"
        "EXECUTION (after user approves, for each phase):\n"
        "1. Read current code (verify assumptions still match)\n"
        "2. Implement changes\n"
        "3. Update claude_memory.md with progress and issues\n"
        "4. Test against the phase's checkpoint criteria\n"
        "5. Fix issues, update claude_memory.md\n"
        "6. Create/update automated tests\n"
        "7. Verify all tests pass\n"
        "8. Commit (format: type(scope): message -no Co-Authored-By)\n"
        "9. Update claude_memory.md (mark accomplished, cleanup stale info)"
    ),
    "do": (
        "MODE: DO -Implement efficiently.\n"
        "- The user has decided what to do. Execute it.\n"
        "- Focus on correctness and simplicity\n"
        "- Ask only if genuinely blocked, not for confirmation\n"
        "- Test as you go when possible"
        + MEMORY_REMINDER
    ),
    "review": (
        "MODE: REVIEW -Critically evaluate what exists.\n"
        "- Check for bugs, missing edge cases, security issues\n"
        "- Verify alignment with ADRs and documented requirements\n"
        "- Identify root causes, not just symptoms\n"
        "- Be specific: cite file paths and line numbers\n"
        "- Suggest concrete improvements, not vague observations"
    ),
}

DEFAULT_REMINDER = (
    "No mode prefix detected. Before acting, briefly consider:\n"
    "- Is this request asking for analysis, planning, implementation, or review?\n"
    "- For non-trivial work, confirm the approach before writing code.\n"
    "- Check known project context (CLAUDE.md, recent decisions) before pushing back on anything."
    + MEMORY_REMINDER
)


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        sys.exit(0)

    prompt = input_data.get("prompt", "").strip()
    if not prompt:
        sys.exit(0)

    # Check for !mode prefix
    match = re.match(r"^!(\w+)\s", prompt)
    if match:
        prefix = match.group(1).lower()
        if prefix in MODES:
            print(MODES[prefix])
            sys.exit(0)

    # No recognized prefix -exit silently (no delay)
    sys.exit(0)


if __name__ == "__main__":
    main()