# Calendar Sensor

A GLADyS sensor that monitors calendar events and emits notifications for upcoming meetings.

## Features

- Mock mode for testing (reads from local JSON file)
- Configurable notification thresholds (1 hour, 15 min, 5 min, now)
- Deduplicates notifications per event
- Supports both Local and Docker orchestrator

## Prerequisites

The sensor requires gRPC and protobuf. Run from the orchestrator's virtual environment:

```bash
cd src/orchestrator
uv run python ../../plugins/sensors/calendar-sensor/sensor.py --mock
```

Or install dependencies directly:

```bash
cd plugins/sensors/calendar-sensor
uv pip install -e .
python sensor.py --mock
```

## Usage

### Mock Mode (Testing)

```bash
# From project root, using orchestrator's venv
cd src/orchestrator
uv run python ../../plugins/sensors/calendar-sensor/sensor.py --mock
```

This creates/reads `events.json` with sample events. Edit this file to test different scenarios.

### With Docker Orchestrator

```bash
python sensor.py --mock --docker
```

### Custom Orchestrator Address

```bash
python sensor.py --mock --orchestrator localhost:50050
```

### Custom Poll Interval

```bash
python sensor.py --mock --interval 10  # Poll every 10 seconds
```

## Mock Events File

Edit `events.json` to customize test events:

```json
[
  {
    "event_id": "meeting-1",
    "summary": "Team Standup",
    "start_time": "2026-01-27T10:00:00",
    "end_time": "2026-01-27T10:15:00",
    "location": "Zoom",
    "organizer": "team-lead@example.com",
    "attendees": ["dev1@example.com", "dev2@example.com"],
    "is_all_day": false
  }
]
```

Set `start_time` to a few minutes from now to test upcoming notifications.

## Output

The sensor emits events like:

```
[10:15:32] Emitting: Meeting starting in 5 minutes: Team Standup at Zoom
  -> Event abc12345 accepted
     Response: I'll remind you when it's time to join.
```

## Notification Types

| Threshold | Type | Example Message |
|-----------|------|-----------------|
| 60 min | `upcoming` | "Upcoming meeting in 58 minutes: Team Standup" |
| 15 min | `starting_soon` | "Meeting starting in 14 minutes: Team Standup" |
| 5 min | `starting_soon` | "Meeting starting in 4 minutes: Team Standup" |
| 0 min | `started` | "Meeting starting now: Team Standup" |

## Future: Google Calendar Integration

To add Google Calendar support:

1. Create OAuth credentials in Google Cloud Console
2. Download `credentials.json` to this directory
3. Run `python sensor.py --google` (not yet implemented)

## Architecture

```
events.json / Google API
        |
        v
  CalendarSensor
        |
        | gRPC: PublishEvents(stream Event)
        v
   Orchestrator
        |
        v
  Salience Gateway → Executive
```
