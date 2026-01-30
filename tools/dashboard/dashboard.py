import os
import random
import socket
import subprocess
import sys
import time
import argparse
from pathlib import Path

# Configuration
PORT = 8502
# Resolve root from tools/dashboard/run.py -> ../../
PROJECT_ROOT = Path(__file__).parent.parent.parent
DASHBOARD_DIR = PROJECT_ROOT / "src" / "services" / "dashboard"
CMD = [
    "uv", "run",
    "uvicorn", "backend.main:app",
    "--host", "0.0.0.0",
    "--port", str(PORT),
    "--reload",
]

def is_windows():
    return sys.platform == "win32"

def find_pid_by_port(port):
    """Find the PID of a process listening on a port."""
    try:
        if is_windows():
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        return int(parts[-1])
        else:
            result = subprocess.run(
                ["lsof", "-t", f"-i:{port}"],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                return int(result.stdout.strip().split()[0])
    except Exception as e:
        print(f"Error finding PID: {e}")
    return None

def start():
    pid = find_pid_by_port(PORT)
    if pid and _pid_exists(pid):
        print(f"Dashboard is already running on port {PORT} (PID {pid})")
        return
    if not _port_is_free(PORT):
        print(f"Port {PORT} is in use (stale socket). Waiting...")
        if not _wait_for_port_free(PORT, timeout=10):
            print(f"Port {PORT} still unavailable. Try again shortly.")
            return

    print(f"Starting Dashboard on port {PORT}...")
    try:
        if is_windows():
            # Open in a new window so we can see logs
            subprocess.Popen(
                CMD,
                cwd=DASHBOARD_DIR,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            log_file = PROJECT_ROOT / "dashboard.log"
            with open(log_file, "w") as f:
                subprocess.Popen(
                    CMD,
                    cwd=DASHBOARD_DIR,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
            print(f"Logs redirected to {log_file}")
            
        print("Server starting...")
        # Wait for it to come up
        for _ in range(10):
            if find_pid_by_port(PORT):
                print("Dashboard started successfully.")
                return
            time.sleep(1)
        print("Warning: Server process started but port is not yet open.")
            
    except Exception as e:
        print(f"Failed to start server: {e}")

def _pid_exists(pid):
    """Check if a process is actually running (not just a stale netstat entry)."""
    try:
        if is_windows():
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, Exception):
        return False


def _kill_pid(pid):
    """Kill a process (tree on Windows). Returns True if kill command succeeded."""
    try:
        if is_windows():
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, text=True
            )
            output = (result.stdout + result.stderr).strip()
            if output:
                print(f"  taskkill: {output}")
        else:
            os.kill(pid, 15)  # SIGTERM
            time.sleep(1)
            try:
                os.kill(pid, 9)  # SIGKILL
            except OSError:
                pass
        return True
    except Exception as e:
        print(f"Error killing PID {pid}: {e}")
        return False


def _port_is_free(port):
    """Try to bind to the port. More reliable than netstat for stale entries."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", port))
            return True
    except OSError:
        return False


def _wait_for_port_free(port, timeout=10):
    """Poll until port is free. Returns True if freed within timeout."""
    for _ in range(timeout):
        if _port_is_free(port):
            return True
        time.sleep(1)
    return False


def stop():
    pid = find_pid_by_port(PORT)
    if not pid:
        print(f"Dashboard is not running on port {PORT}")
        return True

    print(f"Killing PID {pid}...")
    _kill_pid(pid)

    # Process is dead — stop() succeeded. Port release is start()'s concern.
    if not _pid_exists(pid):
        print("Process killed.")
        return True

    # PID still alive — retry kill
    for attempt in range(2, 4):
        wait = random.uniform(0.3, 0.8)
        print(f"Retry {attempt}/3 after {wait:.1f}s...")
        time.sleep(wait)

        pid = find_pid_by_port(PORT)
        if not pid:
            print("Stopped.")
            return True

        print(f"Killing PID {pid}...")
        _kill_pid(pid)

        if not _pid_exists(pid):
            print("Process killed.")
            return True

    print(f"Failed: port {PORT} still in use after 3 attempts.")
    return False

def restart():
    if not stop():
        print("Restart aborted — could not stop the running instance.")
        return
    start()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage GLADyS Dashboard")
    parser.add_argument("action", choices=["start", "stop", "restart"], help="Action to perform")
    args = parser.parse_args()

    if args.action == "start":
        start()
    elif args.action == "stop":
        stop()
    elif args.action == "restart":
        restart()
