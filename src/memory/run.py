#!/usr/bin/env python3
"""GLADyS Memory Subsystem - Helper Script

Usage: python run.py [command]

Commands:
    start   Start all services
    stop    Stop all services
    status  Show service status
    logs    Follow logs (Ctrl+C to exit)
    reset   Stop and delete all data
    build   Rebuild images
"""
import subprocess
import sys

def run(cmd: str) -> None:
    subprocess.run(cmd, shell=True)

def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    commands = {
        "start":  "docker compose up -d",
        "stop":   "docker compose down",
        "status": "docker compose ps",
        "logs":   "docker compose logs -f",
        "reset":  "docker compose down -v",
        "build":  "docker compose build --no-cache",
    }

    if cmd in commands:
        run(commands[cmd])
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
