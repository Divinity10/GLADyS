"""
Calendar Sensor for GLADyS

Monitors upcoming calendar events and emits notifications to the orchestrator.
Supports mock mode (local JSON file) for testing without OAuth setup.

Usage:
    # Mock mode (reads from events.json in same directory)
    python sensor.py --mock

    # Google Calendar mode (requires credentials.json)
    python sensor.py --google
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import grpc
from google.protobuf import struct_pb2, timestamp_pb2

# Add orchestrator to path for proto imports
sys.path.insert(0, str(Path(__file__).parents[3] / "src" / "orchestrator"))

from gladys_orchestrator.generated import (
    common_pb2,
    orchestrator_pb2,
    orchestrator_pb2_grpc,
)

SENSOR_ID = "calendar-sensor"
DEFAULT_ORCHESTRATOR_ADDR = "localhost:50050"  # Local mode
DOCKER_ORCHESTRATOR_ADDR = "localhost:50060"   # Docker mode

# Notification thresholds (minutes before event)
NOTIFICATION_THRESHOLDS = [
    (60, "upcoming"),      # 1 hour before
    (15, "starting_soon"), # 15 minutes before
    (5, "starting_soon"),  # 5 minutes before
    (0, "started"),        # Event starting now
]


def load_mock_events(mock_file: Path) -> list[dict]:
    """Load calendar events from a JSON file."""
    if not mock_file.exists():
        # Create sample events file
        sample_events = [
            {
                "event_id": "meeting-1",
                "summary": "Team Standup",
                "start_time": (datetime.now() + timedelta(minutes=10)).isoformat(),
                "end_time": (datetime.now() + timedelta(minutes=25)).isoformat(),
                "location": "Zoom",
                "organizer": "team-lead@example.com",
                "attendees": ["dev1@example.com", "dev2@example.com"],
                "is_all_day": False
            },
            {
                "event_id": "meeting-2",
                "summary": "1:1 with Manager",
                "start_time": (datetime.now() + timedelta(hours=2)).isoformat(),
                "end_time": (datetime.now() + timedelta(hours=2, minutes=30)).isoformat(),
                "location": "Office Room 3",
                "organizer": "manager@example.com",
                "attendees": [],
                "is_all_day": False
            },
            {
                "event_id": "meeting-3",
                "summary": "Project Review",
                "start_time": (datetime.now() + timedelta(hours=4)).isoformat(),
                "end_time": (datetime.now() + timedelta(hours=5)).isoformat(),
                "location": "Conference Room A",
                "organizer": "pm@example.com",
                "attendees": ["team-lead@example.com", "designer@example.com"],
                "is_all_day": False
            }
        ]
        with open(mock_file, "w", encoding="utf-8") as f:
            json.dump(sample_events, f, indent=2)
        print(f"Created sample events file: {mock_file}")

    with open(mock_file, "r", encoding="utf-8") as f:
        return json.load(f)


def dict_to_struct(d: dict) -> struct_pb2.Struct:
    """Convert a Python dict to a protobuf Struct."""
    s = struct_pb2.Struct()
    s.update(d)
    return s


def datetime_to_timestamp(dt: datetime) -> timestamp_pb2.Timestamp:
    """Convert Python datetime to protobuf Timestamp."""
    ts = timestamp_pb2.Timestamp()
    ts.FromDatetime(dt)
    return ts


def create_event(
    event_data: dict,
    notification_type: str,
    minutes_until: int
) -> common_pb2.Event:
    """Create a gRPC Event from calendar event data."""

    # Parse start time
    start_time = datetime.fromisoformat(event_data["start_time"].replace("Z", "+00:00"))

    # Generate natural language description
    if notification_type == "upcoming":
        raw_text = f"Upcoming meeting in {minutes_until} minutes: {event_data['summary']}"
    elif notification_type == "starting_soon":
        raw_text = f"Meeting starting in {minutes_until} minutes: {event_data['summary']}"
    elif notification_type == "started":
        raw_text = f"Meeting starting now: {event_data['summary']}"
    else:
        raw_text = f"Calendar event: {event_data['summary']}"

    if event_data.get("location"):
        raw_text += f" at {event_data['location']}"

    # Build structured data
    structured = {
        "event_id": event_data["event_id"],
        "summary": event_data["summary"],
        "start_time": event_data["start_time"],
        "end_time": event_data.get("end_time", ""),
        "location": event_data.get("location", ""),
        "organizer": event_data.get("organizer", ""),
        "attendees": event_data.get("attendees", []),
        "is_all_day": event_data.get("is_all_day", False),
        "minutes_until_start": minutes_until,
        "notification_type": notification_type
    }

    return common_pb2.Event(
        id=str(uuid.uuid4()),
        timestamp=datetime_to_timestamp(datetime.now()),
        source=SENSOR_ID,
        raw_text=raw_text,
        structured=dict_to_struct(structured)
    )


class CalendarSensor:
    """Calendar sensor that monitors events and publishes to orchestrator."""

    def __init__(
        self,
        orchestrator_addr: str,
        mock_file: Path | None = None,
        poll_interval: int = 30
    ):
        self.orchestrator_addr = orchestrator_addr
        self.mock_file = mock_file
        self.poll_interval = poll_interval
        self.notified_events: dict[str, set[str]] = {}  # event_id -> set of notification types sent
        self.running = False

    async def register(self, stub: orchestrator_pb2_grpc.OrchestratorServiceStub):
        """Register sensor with orchestrator."""
        try:
            response = await stub.RegisterComponent(
                orchestrator_pb2.RegisterRequest(
                    component_id=SENSOR_ID,
                    component_type="sensor",
                    address="",  # We're a client, not a server
                    capabilities=orchestrator_pb2.ComponentCapabilities(
                        transport_mode=orchestrator_pb2.TRANSPORT_MODE_STREAMING,
                        batch_size=1,
                        batch_interval_ms=0
                    )
                )
            )
            if response.success:
                print(f"Registered with orchestrator as '{response.assigned_id or SENSOR_ID}'")
            else:
                print(f"Registration failed: {response.error_message}")
        except grpc.aio.AioRpcError as e:
            print(f"Failed to register: {e.code()} - {e.details()}")

    def get_events_to_notify(self) -> list[tuple[dict, str, int]]:
        """Get calendar events that need notifications."""
        if self.mock_file:
            events = load_mock_events(self.mock_file)
        else:
            # TODO: Implement Google Calendar / Outlook API
            events = []

        now = datetime.now()
        to_notify = []

        for event in events:
            event_id = event["event_id"]
            start_time = datetime.fromisoformat(event["start_time"].replace("Z", "+00:00"))
            minutes_until = int((start_time - now).total_seconds() / 60)

            # Skip past events
            if minutes_until < -30:
                continue

            # Check each notification threshold
            for threshold_minutes, notification_type in NOTIFICATION_THRESHOLDS:
                notification_key = f"{event_id}:{notification_type}"

                # Already notified for this threshold?
                if event_id in self.notified_events:
                    if notification_type in self.notified_events[event_id]:
                        continue

                # Time to notify?
                if minutes_until <= threshold_minutes:
                    to_notify.append((event, notification_type, minutes_until))

                    # Mark as notified
                    if event_id not in self.notified_events:
                        self.notified_events[event_id] = set()
                    self.notified_events[event_id].add(notification_type)
                    break  # Only one notification per event per poll

        return to_notify

    async def event_generator(self):
        """Generate events to publish to orchestrator."""
        while self.running:
            to_notify = self.get_events_to_notify()

            for event_data, notification_type, minutes_until in to_notify:
                event = create_event(event_data, notification_type, minutes_until)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Emitting: {event.raw_text}")
                yield event

            await asyncio.sleep(self.poll_interval)

    async def run(self):
        """Main sensor loop."""
        print(f"Connecting to orchestrator at {self.orchestrator_addr}...")

        channel = grpc.aio.insecure_channel(self.orchestrator_addr)
        stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)

        # Register with orchestrator
        await self.register(stub)

        self.running = True
        print(f"Calendar sensor running (poll interval: {self.poll_interval}s)")
        print("Press Ctrl+C to stop")

        try:
            # Stream events to orchestrator
            async for ack in stub.PublishEvents(self.event_generator()):
                if ack.accepted:
                    print(f"  -> Event {ack.event_id[:8]} accepted")
                    if ack.response_text:
                        print(f"     Response: {ack.response_text[:100]}")
                else:
                    print(f"  -> Event {ack.event_id[:8]} rejected: {ack.error_message}")

        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.CANCELLED:
                print("Stream cancelled")
            else:
                print(f"gRPC error: {e.code()} - {e.details()}")
        finally:
            self.running = False
            await channel.close()


async def main():
    parser = argparse.ArgumentParser(description="GLADyS Calendar Sensor")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock events from local JSON file"
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Connect to Docker orchestrator (port 50060)"
    )
    parser.add_argument(
        "--orchestrator",
        type=str,
        help="Orchestrator address (default: localhost:50050)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Poll interval in seconds (default: 30)"
    )
    args = parser.parse_args()

    # Determine orchestrator address
    if args.orchestrator:
        addr = args.orchestrator
    elif args.docker:
        addr = DOCKER_ORCHESTRATOR_ADDR
    else:
        addr = DEFAULT_ORCHESTRATOR_ADDR

    # Determine event source
    mock_file = None
    if args.mock:
        mock_file = Path(__file__).parent / "events.json"
        print(f"Mock mode: reading events from {mock_file}")
    else:
        print("Warning: No calendar backend configured. Use --mock for testing.")
        mock_file = Path(__file__).parent / "events.json"

    sensor = CalendarSensor(
        orchestrator_addr=addr,
        mock_file=mock_file,
        poll_interval=args.interval
    )

    try:
        await sensor.run()
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    asyncio.run(main())
