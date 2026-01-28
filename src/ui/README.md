# GLADyS Evaluation Dashboard

A Streamlit dashboard to visualize and control the GLADyS learning loop.

## Features

### Sidebar
- **Environment Switcher**: Toggle between Docker and Local services
- **Service Health**: Compact display with status icons (🟢 healthy, 🟡 degraded, 🔴 unhealthy, ⚫ offline)
- **Service Selection**: Radio buttons to target individual services or all
- **Start/Stop/Restart**: Manage selected service(s) with confirmation for "Stop All"

### Tabs

| Tab | Purpose |
|-----|---------|
| **Laboratory** | Event simulator, response history, heuristics table |
| **Memory** | Query semantic/episodic memory directly |
| **Event Log** | Recent events with expandable detail rows |
| **Cache** | Rust salience gateway cache stats |
| **Flight Recorder** | Heuristic fires and outcomes for debugging |
| **Logs** | Command log and service log viewer |
| **Settings** | Time filters, testing tools, database operations, connection info |

### Event Log Features
- Expandable rows with +/- toggles
- Inline detail display showing salience scores, prediction, and response path
- Dark mode compatible styling

## Prerequisites
- Python 3.11+
- Services running (Docker or Local)

## Setup

1. **Install Dependencies** (using `uv` is recommended):
   ```bash
   cd src/ui
   uv pip install -r pyproject.toml
   ```

## Running the Dashboard

Start services first (from project root):
```bash
# Docker
python scripts/docker.py start

# Or Local
python scripts/local.py start
```

Run the dashboard:
```bash
cd src/ui
uv run streamlit run dashboard.py
```

The dashboard opens at `http://localhost:8501`.

## Environment Switching

Use the **Environment** radio button in the sidebar to switch between Docker and Local services. The dashboard auto-reconnects to the appropriate ports.

| Environment | Orchestrator | Memory Python | Memory Rust | Executive | DB Port |
|-------------|--------------|---------------|-------------|-----------|---------|
| Docker      | 50060        | 50061         | 50062       | 50063     | 5433    |
| Local       | 50050        | 50051         | 50052       | 50053     | 5432    |

## Logs Tab

The Logs tab provides visibility into system output:

- **Command Log**: Output from recent service management commands (start/stop/restart)
- **Service Logs**: View recent output from each GLADyS service
  - Memory (Python), Salience Gateway (Rust), Orchestrator, Executive
  - Configurable tail lines (50, 100, 200, 500)

### Log Sources by Environment

| Environment | Log Source |
|-------------|------------|
| Docker | `docker-compose logs` |
| Local | `~/.gladys/logs/<service>.log` |

Local logs use structured logging via `gladys_common` with:
- Rotating file handlers (10MB max, 5 backups)
- DEBUG level to file by default
- Trace ID correlation across services

## Settings Tab

The Settings tab contains:

- **Time Range Filter**: Last Hour, Last 24 Hours, All Time
- **Testing Tools**: Clear local history, queue stats
- **Database Operations**: Run migrations, clean database (with confirmation)
- **Connection Info**: Current service addresses and health status
