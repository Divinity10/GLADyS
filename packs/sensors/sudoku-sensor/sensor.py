"""
Sudoku Sensor for GLADyS

Receives events from the Websudoku driver via HTTP POST and streams them to the orchestrator.
Supports mock mode and dry-run for testing.

Usage:
    # Live mode (starts HTTP server at port 8701)
    python sensor.py

    # Mock mode (reads from events.json)
    python sensor.py --mock

    # Dry run (print to stdout, no orchestrator connection)
    python sensor.py --dry-run
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from aiohttp import web

import grpc
from google.protobuf import struct_pb2, timestamp_pb2

# Add orchestrator to path for proto imports
sys.path.insert(0, str(Path(__file__).parents[3] / "src" / "services" / "orchestrator"))

from gladys_orchestrator.generated import (
    common_pb2,
    orchestrator_pb2,
    orchestrator_pb2_grpc,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("sudoku-sensor")

SENSOR_ID = "sudoku-sensor"
DEFAULT_PORT = 8701
DEFAULT_ORCHESTRATOR_ADDR = "localhost:50050"
DOCKER_ORCHESTRATOR_ADDR = "localhost:50060"

class SudokuSensor:
    def __init__(
        self,
        orchestrator_addr: str,
        http_port: int,
        mock_file: Path | None = None,
        dry_run: bool = False
    ):
        self.orchestrator_addr = orchestrator_addr
        self.http_port = http_port
        self.mock_file = mock_file
        self.dry_run = dry_run
        self.event_queue = asyncio.Queue()
        self.running = False
        
    def dict_to_struct(self, d: dict) -> struct_pb2.Struct:
        """Convert a Python dict to a protobuf Struct."""
        s = struct_pb2.Struct()
        s.update(d)
        return s

    def datetime_to_timestamp(self, dt_str: str) -> timestamp_pb2.Timestamp:
        """Convert ISO string to protobuf Timestamp."""
        ts = timestamp_pb2.Timestamp()
        try:
            # Handle timestamps with Z or offset
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            ts.FromDatetime(dt)
        except ValueError:
            # Fallback to now if parsing fails
            ts.FromDatetime(datetime.now())
        return ts

    def create_event_message(self, event_data: dict) -> common_pb2.Event:
        """Create a gRPC Event from driver data."""
        event_type = event_data.get("event_type", "unknown")
        data = event_data.get("data", {})
        timestamp_str = event_data.get("timestamp", datetime.now().isoformat())

        # Generate natural language description
        raw_text = f"Sudoku event: {event_type}"
        
        if event_type == "puzzle_start":
            diff_map = {1: "Easy", 2: "Medium", 3: "Hard", 4: "Evil"}
            diff_val = data.get("difficulty", 1)
            diff_str = diff_map.get(diff_val, str(diff_val))
            raw_text = f"Started a new {diff_str} sudoku puzzle"
        elif event_type == "cell_filled":
            row = data.get("row")
            col = data.get("col")
            val = data.get("value")
            is_correct = data.get("is_correct")
            correct_str = "(correct)" if is_correct else "(incorrect)"
            raw_text = f"Filled row {row} col {col} with {val} {correct_str}"
        elif event_type == "puzzle_complete":
            minutes = data.get("time_seconds", 0) // 60
            seconds = data.get("time_seconds", 0) % 60
            errors = data.get("error_count", 0)
            raw_text = f"Completed sudoku in {minutes}m {seconds}s with {errors} errors"
        elif event_type == "request_hint":
            raw_text = f"User is stuck, requesting hint"
            if "row" in data and "col" in data:
                raw_text += f" for row {data['row']} col {data['col']}"

        # Combine type into structured data
        structured_data = dict(data)
        structured_data["event_type"] = event_type

        return common_pb2.Event(
            id=str(uuid.uuid4()),
            timestamp=self.datetime_to_timestamp(timestamp_str),
            source=SENSOR_ID,
            raw_text=raw_text,
            structured=self.dict_to_struct(structured_data)
        )

    async def handle_http_event(self, request):
        """Handle incoming HTTP POST from driver."""
        try:
            data = await request.json()
            logger.info(f"Received HTTP event: {data.get('event_type')}")
            await self.event_queue.put(data)
            return web.json_response({"status": "accepted"})
        except Exception as e:
            logger.error(f"Error handling HTTP event: {e}")
            return web.json_response({"error": str(e)}, status=400)

    async def start_http_server(self):
        """Start the HTTP server for driver POSTs."""
        app = web.Application()
        app.router.add_post('/event', self.handle_http_event)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', self.http_port)
        await site.start()
        logger.info(f"HTTP server listening on localhost:{self.http_port}")
        return runner

    async def run_mock_generator(self):
        """Generate mock events from file."""
        if not self.mock_file or not self.mock_file.exists():
            logger.error("Mock file not found")
            return

        with open(self.mock_file, "r") as f:
            events = json.load(f)

        logger.info(f"Loaded {len(events)} mock events")
        
        for event in events:
            if not self.running: 
                break
                
            # Update timestamp to now to look real
            event["timestamp"] = datetime.now().isoformat()
            
            logger.info(f"Queueing mock event: {event['event_type']}")
            await self.event_queue.put(event)
            await asyncio.sleep(2)  # Simulate delay between events

    async def register(self, stub):
        """Register sensor with orchestrator."""
        if self.dry_run:
            return True

        try:
            response = await stub.RegisterComponent(
                orchestrator_pb2.RegisterRequest(
                    component_id=SENSOR_ID,
                    component_type="sensor",
                    address="", 
                    capabilities=orchestrator_pb2.ComponentCapabilities(
                        transport_mode=orchestrator_pb2.TRANSPORT_MODE_STREAMING,
                        batch_size=1,
                        batch_interval_ms=0
                    )
                )
            )
            if response.success:
                logger.info(f"Registered with orchestrator as '{response.assigned_id or SENSOR_ID}'")
                return True
            else:
                logger.error(f"Registration failed: {response.error_message}")
                return False
        except grpc.aio.AioRpcError as e:
            logger.error(f"Failed to register: {e.code()} - {e.details()}")
            return False

    async def stream_events(self, stub):
        """Generator that yields events from the queue to the gRPC stream."""
        while self.running:
            # Wait for an event
            event_data = await self.event_queue.get()
            event_msg = self.create_event_message(event_data)
            
            if self.dry_run:
                print(f"[DRY RUN] Would emit: {event_msg.raw_text}")
                print(f"          Structured: {event_msg.structured}")
                self.event_queue.task_done()
                continue
            
            logger.info(f"Emitting: {event_msg.raw_text}")
            yield event_msg
            self.event_queue.task_done()

    async def run(self):
        """Main execution loop with connection resilience."""
        self.running = True
        
        # Start input source
        http_runner = None
        mock_task = None
        
        if self.mock_file:
            mock_task = asyncio.create_task(self.run_mock_generator())
        else:
            http_runner = await self.start_http_server()

        # If dry run, just process queue without gRPC connection
        if self.dry_run:
            logger.info("Starting dry run (no orchestrator connection)")
            # Create a fake stub helper for the stream loop
            async def dry_run_loop():
                async for _ in self.stream_events(None):
                    pass
            await dry_run_loop()
            return

        # Main connection loop
        backoff = 1
        while self.running:
            channel = None
            try:
                logger.info(f"Connecting to orchestrator at {self.orchestrator_addr}...")
                channel = grpc.aio.insecure_channel(self.orchestrator_addr)
                stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)

                if await self.register(stub):
                    backoff = 1 # Reset backoff on success
                    
                    # Start bidirectional stream
                    # We send events via stream_events() generator
                    # We receive ACKs from the server
                    async for ack in stub.PublishEvents(self.stream_events(stub)):
                        if ack.accepted:
                            logger.debug(f"Event {ack.event_id[:8]} accepted")
                        else:
                            logger.warning(f"Event {ack.event_id[:8]} rejected: {ack.error_message}")
                
            except grpc.aio.AioRpcError as e:
                logger.error(f"gRPC error: {e.code()} - {e.details()}")
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
            finally:
                if channel:
                    await channel.close()
                
            if self.running:
                logger.info(f"Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

        # Cleanup
        if http_runner:
            await http_runner.cleanup()
        if mock_task:
            await mock_task

async def main():
    parser = argparse.ArgumentParser(description="GLADyS Sudoku Sensor")
    parser.add_argument("--mock", action="store_true", help="Use mock events from local JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Print events to stdout, no orchestrator")
    parser.add_argument("--docker", action="store_true", help="Connect to Docker orchestrator (port 50060)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"HTTP listen port (default: {DEFAULT_PORT})")
    parser.add_argument("--orchestrator", type=str, help="Orchestrator address")
    
    args = parser.parse_args()

    # Determine orchestrator address
    if args.orchestrator:
        addr = args.orchestrator
    elif args.docker:
        addr = DOCKER_ORCHESTRATOR_ADDR
    else:
        addr = DEFAULT_ORCHESTRATOR_ADDR

    mock_file = None
    if args.mock:
        mock_file = Path(__file__).parent / "events.json"

    sensor = SudokuSensor(
        orchestrator_addr=addr,
        http_port=args.port,
        mock_file=mock_file,
        dry_run=args.dry_run
    )

    try:
        await sensor.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sensor.running = False

if __name__ == "__main__":
    asyncio.run(main())