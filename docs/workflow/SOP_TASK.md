# Task Execution SOP

This protocol ensures that agents (Claude/Gemini) work safely and verify their results against the actual system state, rather than just local files.

## 1. Ingress (Starting a Task)

Before implementing logic or modifying code:

- **State Verification**: Don't just trust `.proto` or `.sql` files. Probe the **actual runtime state**.
    - **Database**: If your task depends on a specific schema, run a probe query (e.g., `SELECT column_name FROM information_schema.columns...`) to confirm the columns exist in the target environment.
    - **API/gRPC**: If you depend on a service, check if the port is open and the service is responsive (`python scripts/local.py status` or `python scripts/docker.py status`).
- **Resource Constraints**:
    - Identify which ports and service instances are for **Local Dev** vs. **Docker/Integration**. 
    - **NEVER** modify or connect to ports outside your specific task scope (e.g., don't step on local dev ports `5432` if working on Docker `5433`).
- **Isolation Check**: Verify `docker ps` to ensure you are talking to the correct container.

## 2. Progress

- **Incremental updates**: Update `memory.md` (Claude) or `gemini_memory.md` (Gemini) after every significant decision or technical discovery.
- **Fail Fast**: If a runtime check fails (e.g., missing column), stop and report it immediately rather than building on a broken assumption.

## 3. Egress (Turnover / Completion)

Before declaring a task "DONE":

- **Live Verification**: You MUST run the code (or a probe script) against the live target environment. 
    - "It builds" or "the logic looks correct" is insufficient.
    - If you cannot run the code (e.g., system is down), state this clearly as a blocker.
- **Dependency Checklist**: Explicitly state any external actions required for your work to function (e.g., "Requires Migration 005 to be applied").
- **Artifact Inventory**: List all files created or modified.
- **Cleanup**: 
    - Stop any background processes you started.
    - Delete any temporary test data or tables created during verification.
    - Ensure `memory.md` or `gemini_memory.md` contains the final state and next steps.
