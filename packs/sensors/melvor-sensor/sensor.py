"""
Melvor Idle Sensor for GLADyS

Receives events from the Melvor Idle driver via HTTP POST and streams them to the orchestrator.
"""

import argparse
import asyncio
import json
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
# Add common lib to path for logging
sys.path.insert(0, str(Path(__file__).parents[3] / "src" / "lib" / "gladys_common"))

from gladys_orchestrator.generated import (
    common_pb2,
    orchestrator_pb2,
    orchestrator_pb2_grpc,
)
from gladys_common import setup_logging, get_logger, bind_trace_id, generate_trace_id

SENSOR_ID = "melvor-sensor"
DEFAULT_PORT = 8702
DEFAULT_ORCHESTRATOR_ADDR = "localhost:50050"
DOCKER_ORCHESTRATOR_ADDR = "localhost:50060"

# Initialize logging (will be configured in main)
logger = get_logger()

class MelvorSensor:
    def __init__(
        self,
        orchestrator_addr: str,
        http_port: int,
        trace_id: str,
        mock_file: Path | None = None,
        dry_run: bool = False
    ):
        self.orchestrator_addr = orchestrator_addr
        self.http_port = http_port
        self.trace_id = trace_id
        self.mock_file = mock_file
        self.dry_run = dry_run
        self.event_queue = asyncio.Queue()
        self.running = False
        
    def dict_to_struct(self, d: dict) -> struct_pb2.Struct:
        """Convert a Python dict to a protobuf Struct."""
        s = struct_pb2.Struct()
        try:
            s.update(d)
        except Exception as e:
            logger.warning("Struct conversion warning, serializing complex fields", error=str(e))
            clean_d = {}
            for k, v in d.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    clean_d[k] = json.dumps(v)
                else:
                    clean_d[k] = v
            s.update(clean_d)
        return s

    def datetime_to_timestamp(self, dt_str: str) -> timestamp_pb2.Timestamp:
        """Convert ISO string to protobuf Timestamp."""
        ts = timestamp_pb2.Timestamp()
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            ts.FromDatetime(dt)
        except ValueError:
            ts.FromDatetime(datetime.now())
        return ts

    def create_event_message(self, event_data: dict) -> common_pb2.Event:
        """Create a gRPC Event from driver data."""
        event_type = event_data.get("event_type", "unknown")
        data = event_data.get("data", {})
        timestamp_str = event_data.get("timestamp", datetime.now().isoformat())

        # Generate natural language description
        raw_text = f"Melvor event: {event_type}"
        
        if event_type == "combat_started":
            monster = data.get("monster_name", "Unknown")
            area = data.get("combat_area", "Unknown Area")
            raw_text = f"Started fighting a {monster} in {area}"
            
        elif event_type == "combat_killed":
            monster = data.get("monster_name", "Enemy")
            xp = data.get("xp_gained", 0)
            loot = data.get("loot", [])
            loot_str = ", ".join([f"{i.get('qty',1)} {i.get('item','?')}" for i in loot]) if loot else "no loot"
            raw_text = f"Killed a {monster}, got {loot_str} and {xp} combat XP"
            
        elif event_type == "combat_died":
            monster = data.get("monster_name", "Enemy")
            raw_text = f"Died to a {monster}"
            
        elif event_type == "level_up":
            skill = data.get("skill_name", "?")
            lvl = data.get("new_level", "?")
            unlocks = data.get("unlocks", [])
            unlock_str = f", unlocked {', '.join(unlocks)}" if unlocks else ""
            raw_text = f"{skill} reached level {lvl}{unlock_str}"
            
        elif event_type == "item_equipped":
            item = data.get("item_name", "?")
            slot = data.get("slot", "?")
            raw_text = f"Equipped {item} in {slot}"
            
        elif event_type == "skill_started":
            skill = data.get("skill_name", "?")
            action = data.get("action", "?")
            raw_text = f"Started {skill}: {action}"
            
        elif event_type == "skill_milestone":
            skill = data.get("skill_name", "?")
            milestone = data.get("milestone", "?")
            raw_text = f"{skill} milestone: {milestone}"
            
        elif event_type == "shop_purchase":
            item = data.get("item_name", "?")
            cost = data.get("cost", 0)
            currency = data.get("currency", "GP")
            raw_text = f"Bought {item} for {cost} {currency}"

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
            logger.info("Received HTTP event", event_type=data.get('event_type'))
            await self.event_queue.put(data)
            return web.json_response({"status": "accepted"})
        except Exception as e:
            logger.error("Error handling HTTP event", error=str(e))
            return web.json_response({"error": str(e)}, status=400)

    async def start_http_server(self):
        """Start the HTTP server for driver POSTs."""
        app = web.Application()
        app.router.add_post('/event', self.handle_http_event)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', self.http_port)
        await site.start()
        logger.info("HTTP server listening", port=self.http_port)
        return runner

    async def run_mock_generator(self):
        """Generate mock events from file."""
        if not self.mock_file or not self.mock_file.exists():
            logger.error("Mock file not found", path=str(self.mock_file))
            return

        with open(self.mock_file, "r") as f:
            events = json.load(f)

        logger.info("Loaded mock events", count=len(events))
        
        for event in events:
            if not self.running: 
                break
                
            event["timestamp"] = datetime.now().isoformat()
            logger.info("Queueing mock event", event_type=event['event_type'])
            await self.event_queue.put(event)
            await asyncio.sleep(2)

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
                ),
                metadata=[('x-gladys-trace-id', self.trace_id)]
            )
            if response.success:
                logger.info("Registered with orchestrator", assigned_id=response.assigned_id or SENSOR_ID)
                return True
            else:
                logger.error("Registration failed", error=response.error_message)
                return False
        except grpc.aio.AioRpcError as e:
            logger.error("Failed to register", code=e.code(), details=e.details())
            return False

    async def stream_events(self, stub):
        """Generator that yields events from the queue to the gRPC stream."""
        while self.running:
            event_data = await self.event_queue.get()
            event_msg = self.create_event_message(event_data)
            
            if self.dry_run:
                print(f"[DRY RUN] Would emit: {event_msg.raw_text}")
                self.event_queue.task_done()
                continue
            
            logger.info("Emitting event", text=event_msg.raw_text)
            yield event_msg
            self.event_queue.task_done()

    async def run(self):
        """Main execution loop with connection resilience."""
        self.running = True
        
        http_runner = None
        mock_task = None
        
        if self.mock_file:
            mock_task = asyncio.create_task(self.run_mock_generator())
        else:
            http_runner = await self.start_http_server()

        if self.dry_run:
            logger.info("Starting dry run (no orchestrator connection)")
            async def dry_run_loop():
                async for _ in self.stream_events(None):
                    pass
            await dry_run_loop()
            return

        backoff = 1
        while self.running:
            channel = None
            try:
                logger.info("Connecting to orchestrator", addr=self.orchestrator_addr)
                channel = grpc.aio.insecure_channel(self.orchestrator_addr)
                stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)

                if await self.register(stub):
                    backoff = 1 
                    async for ack in stub.PublishEvents(
                        self.stream_events(stub),
                        metadata=[('x-gladys-trace-id', self.trace_id)]
                    ):
                        if ack.accepted:
                            logger.debug("Event accepted", event_id=ack.event_id[:8])
                        else:
                            logger.warning("Event rejected", event_id=ack.event_id[:8], error=ack.error_message)
                
            except grpc.aio.AioRpcError as e:
                logger.error("gRPC error", code=e.code(), details=e.details())
            except Exception as e:
                logger.error("Unexpected error", error=str(e))
            finally:
                if channel:
                    await channel.close()
                
            if self.running:
                logger.info("Reconnecting", delay=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

        if http_runner:
            await http_runner.cleanup()
        if mock_task:
            await mock_task

async def main():
    parser = argparse.ArgumentParser(description="GLADyS Melvor Sensor")
    parser.add_argument("--mock", action="store_true", help="Use mock events from local JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Print events to stdout, no orchestrator")
    parser.add_argument("--docker", action="store_true", help="Connect to Docker orchestrator (port 50060)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"HTTP listen port (default: {DEFAULT_PORT})")
    parser.add_argument("--orchestrator", type=str, help="Orchestrator address")
    
    args = parser.parse_args()

    # Configure logging and trace ID per standard
    setup_logging(SENSOR_ID)
    trace_id = generate_trace_id()
    bind_trace_id(trace_id)

    # Issue #3: Explicit start log
    mode = "mock" if args.mock else "live"
    logger.info("Sensor started", mode=mode, dry_run=args.dry_run, trace_id=trace_id)

    if args.orchestrator:
        addr = args.orchestrator
    elif args.docker:
        addr = DOCKER_ORCHESTRATOR_ADDR
    else:
        addr = DEFAULT_ORCHESTRATOR_ADDR

    mock_file = None
    if args.mock:
        mock_file = Path(__file__).parent / "events.json"

    sensor = MelvorSensor(
        orchestrator_addr=addr,
        http_port=args.port,
        trace_id=trace_id,
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
