# AGENTS.md

Instructions for AI agents (Codex, Gemini, Claude) working on GLADyS.
This file is auto-loaded by Codex and Gemini. Claude loads CLAUDE.md instead.

## First Steps

1. Read `CLAUDE.md` -- project principles, conventions, architecture
2. Read `docs/CONVENTIONS.md` -- code patterns and dependency management
3. Read your task prompt -- implementation instructions

## Platform

Windows. Use PowerShell or cross-platform commands. Do NOT use Unix-only syntax (`&&` chaining, `source`, `export`, Unix paths). Use `;` for command chaining.

## File Encoding

All files: UTF-8 **without BOM**, LF line endings (not CRLF). Never write a byte order mark. Enforced by `.editorconfig`.

## Commit Convention

Title line: `type(scope): message`
Types: `doc`, `feat`, `fix`, `refactor`, `test`, `chore`
Do NOT include `Co-Authored-By` or any AI attribution.

## Tools

Use `rg` (ripgrep) for code search. Do NOT use `Select-String` or `findstr`.

## Fail-Closed Protocol

These are hard gates. Violating any one makes your task INCOMPLETE.

### Gate 0: Requirement Extraction

Before writing code, extract a checklist of hard requirements from the task prompt.

- If any requirement is ambiguous and blocks implementation, ask clarifying questions before coding.
- Do not ask preference questions already answered by the prompt.
- Ask zero questions when no blocking ambiguity exists.

### Gate 1: Branch

**Do NOT write any code until you have created and verified the branch.**

Run the branch commands from your task prompt and paste their output.
If the prompt specifies a branch name but not commands, run:
`git checkout -b <branch>; git rev-parse --abbrev-ref HEAD`

If output does not show the required branch name, STOP and fix before proceeding.

If `git checkout -b` is blocked by sandbox/permissions, report:
```
BLOCKED: git checkout -b <branch> -- <reason>
```
and stop. Do not implement on `main`.

### Gate 2: Scope

Only modify files listed in the task prompt's "Files to Change" table. If you need to change an unlisted file, state the justification before doing so.

### Gate 3: Completion Evidence

**Your task is INCOMPLETE unless you paste verbatim output for every item below.** If any command is blocked, report `BLOCKED: <command> -- <reason>` instead of skipping it.

1. `python cli/fix_encoding.py --modified` -- paste output
2. `git log --oneline -1` -- paste output
3. Test command from task prompt -- paste output showing all pass
4. Handoff section (only if prompt requires a handoff/state update) -- paste exactly what you wrote

### Gate 4: Self-Audit

**Your task is INCOMPLETE unless this table is filled with actual command output.**

| Requirement | Evidence |
|-------------|----------|
| Correct branch | `git rev-parse --abbrev-ref HEAD` output |
| UTF-8 no BOM, LF | `python cli/fix_encoding.py --modified` output |
| Only listed files changed (working tree) | `git diff --name-only` output |
| Only listed files changed (committed) | `git diff --name-only HEAD~1 HEAD` output |

### If Blocked

If any required step cannot be executed due to sandbox, permissions, or tooling:
- Report `BLOCKED: <command> -- <reason>`
- Do NOT skip the step silently
- Do NOT claim completion without the evidence

### Completion Status Tokens

Use these exact status lines when applicable:

- `INCOMPLETE: missing protocol evidence`
- `BLOCKED: <command> -- <reason>`

Never claim completion without the Protocol Evidence section containing exact command outputs.

### Protocol Evidence Template

Use this exact structure in final responses for implementation tasks:

1. Branch Evidence
- Command: `<command>`
- Output:
```text
<verbatim output>
```

2. Encoding Evidence
- Command: `python cli/fix_encoding.py --modified`
- Output:
```text
<verbatim output>
```

3. Test Evidence
- Command: `<test command from prompt>`
- Output:
```text
<verbatim output>
```

4. Commit Evidence
- Command: `git log --oneline -1`
- Output:
```text
<verbatim output>
```

5. Scope Evidence
- Command: `git diff --name-only` and `git diff --name-only HEAD~1 HEAD`
- Output:
```text
<verbatim output>
```

6. Handoff Evidence (if required by prompt)
- File: `<path>`
- Text:
```text
<exact section content>
```

If `cli/protocol_guard.py` exists, run it in required mode before claiming completion.
