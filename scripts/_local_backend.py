"""Local backend implementation for Service Management Scripts."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from _gladys import LOCAL_PORTS, ROOT, get_test_env, is_port_open, is_windows
from _service_base import ServiceBackend


# Service launch configurations for local environment
# All Python services use standardized `python -m <package> start` pattern
SERVICE_CONFIGS = {
    "memory-python": {
        "cwd": ROOT / "src" / "memory" / "python",
        "cmd": ["uv", "run", "python", "-m", "gladys_memory", "start"],
        "env": {},
        "depends_on": [],
    },
    "memory-rust": {
        "cwd": ROOT / "src" / "memory" / "rust",
        "cmd": ["cargo", "run", "--release"],
        "env": {"STORAGE_ADDRESS": f"http://localhost:{LOCAL_PORTS.memory_python}"},
        "depends_on": ["memory-python"],
    },
    "orchestrator": {
        "cwd": ROOT / "src" / "orchestrator",
        "cmd": ["uv", "run", "python", "-m", "gladys_orchestrator", "start"],
        "env": {},
        "depends_on": [],
    },
    "executive-stub": {
        "cwd": ROOT / "src" / "executive",
        "cmd": ["uv", "run", "python", "-m", "gladys_executive", "start"],
        "env": {},
        "depends_on": [],
    },
}

# Map service names to ports
SERVICE_PORTS = {
    "memory-python": LOCAL_PORTS.memory_python,
    "memory-rust": LOCAL_PORTS.memory_rust,
    "orchestrator": LOCAL_PORTS.orchestrator,
    "executive-stub": LOCAL_PORTS.executive,
    "db": LOCAL_PORTS.db,
}


def find_pid_by_port(port: int) -> Optional[int]:
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
    except Exception:
        pass
    return None


def kill_process(pid: int) -> bool:
    """Kill a process by PID."""
    try:
        if is_windows():
            subprocess.run(
                ["powershell", "-Command", f"Stop-Process -Id {pid} -Force"],
                capture_output=True,
            )
        else:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return True
    except Exception as e:
        print(f"  Error killing PID {pid}: {e}")
        return False


class LocalBackend(ServiceBackend):
    """Local process service operations."""

    def __init__(self):
        self.service_configs = SERVICE_CONFIGS
        self.service_ports = SERVICE_PORTS

    def _get_port(self, name: str) -> int:
        """Get port for a service."""
        return self.service_ports.get(name, 0)

    def _start_one(self, name: str, wait: bool = True) -> bool:
        """Start a single service."""
        if name not in self.service_configs:
            if name == "db":
                print(f"  {name}: Database must be started separately (use PostgreSQL service)")
                return True
            print(f"  {name}: Unknown service")
            return False

        config = self.service_configs[name]
        port = self._get_port(name)

        # Check if already running
        if is_port_open("localhost", port):
            print(f"  {name}: Already running on port {port}")
            return True

        # Start dependencies first
        for dep in config.get("depends_on", []):
            dep_port = self._get_port(dep)
            if not is_port_open("localhost", dep_port):
                print(f"  {name}: Starting dependency {dep} first...")
                if not self._start_one(dep, wait=True):
                    print(f"  {name}: Failed to start dependency {dep}")
                    return False

        print(f"  Starting {name}...")

        # Merge environment variables
        env = {**os.environ, **config.get("env", {})}

        # Start the process
        try:
            if is_windows():
                proc = subprocess.Popen(
                    config["cmd"],
                    cwd=config["cwd"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                )
            else:
                proc = subprocess.Popen(
                    config["cmd"],
                    cwd=config["cwd"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

            if wait:
                for _ in range(30):
                    if is_port_open("localhost", port):
                        print(f"  {name}: Started (port {port}, PID {proc.pid})")
                        return True
                    time.sleep(1)
                print(f"  {name}: Started but not responding on port {port}")
                return False
            else:
                print(f"  {name}: Started (PID {proc.pid})")
                return True

        except Exception as e:
            print(f"  {name}: Failed to start - {e}")
            return False

    def _stop_one(self, name: str) -> bool:
        """Stop a single service."""
        port = self._get_port(name)
        if not port:
            print(f"  {name}: Unknown service")
            return False

        pid = find_pid_by_port(port)
        if not pid:
            print(f"  {name}: Not running")
            return True

        print(f"  Stopping {name} (PID {pid})...")
        if kill_process(pid):
            for _ in range(10):
                if not is_port_open("localhost", port):
                    print(f"  {name}: Stopped")
                    return True
                time.sleep(0.5)
            print(f"  {name}: Killed but port {port} still in use")
            return False
        return False

    def start_service(self, names: List[str], wait: bool = True) -> bool:
        """Start one or more services."""
        # Run migrations first
        self.run_migration()

        print(f"Starting LOCAL services: {', '.join(names)}...")
        success = True
        for name in names:
            if not self._start_one(name, wait=wait):
                success = False
        return success

    def stop_service(self, names: List[str]) -> bool:
        """Stop one or more services."""
        print(f"Stopping LOCAL services: {', '.join(names)}...")
        success = True
        for name in names:
            if not self._stop_one(name):
                success = False
        return success

    def restart_service(self, names: List[str]) -> bool:
        """Restart one or more services."""
        print(f"Restarting LOCAL services: {', '.join(names)}...")
        self.stop_service(names)
        time.sleep(1)
        return self.start_service(names)

    def get_service_status(self, name: str) -> Dict[str, Any]:
        """Get service status."""
        port = self._get_port(name)
        if not port:
            return {"running": False, "healthy": False, "status_text": "unknown"}

        running = is_port_open("localhost", port)
        pid = find_pid_by_port(port) if running else None

        return {
            "running": running,
            "healthy": running,  # For local, running = healthy
            "status_text": f"running (PID {pid})" if running else "stopped",
            "pid": pid,
        }

    def get_service_health(self, name: str, detailed: bool = False) -> Dict[str, Any]:
        """Get gRPC health status from a service."""
        port = self._get_port(name)
        if not port:
            return {"status": "UNKNOWN", "error": "Unknown service"}

        if not is_port_open("localhost", port):
            return {"status": "UNKNOWN", "error": "Service not running"}

        # Use the health client script
        python_exe = ROOT / "src" / "memory" / "python" / ".venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            python_exe = ROOT / "src" / "memory" / "python" / ".venv" / "bin" / "python"
        if not python_exe.exists():
            python_exe = Path("python")

        address = f"localhost:{port}"
        args = [str(python_exe), str(ROOT / "scripts" / "_health_client.py"), "--address", address]
        if detailed:
            args.append("--detailed")

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
            else:
                return {"status": "UNKNOWN", "error": result.stderr.strip() or "Health check failed"}
        except subprocess.TimeoutExpired:
            return {"status": "UNKNOWN", "error": "Health check timed out"}
        except Exception as e:
            return {"status": "UNKNOWN", "error": str(e)}

    def get_logs(self, names: List[str], follow: bool = True, tail: Optional[int] = None) -> None:
        """Stream or view service logs.

        Note: Local services run detached without log files by default.
        This is a limitation - consider adding file-based logging.
        """
        print("Log viewing not yet implemented for local services.")
        print("Local services run detached. Consider:")
        print("  - Running services in foreground for debugging")
        print("  - Adding file-based logging to services")

    def run_sql(self, sql: str, database: str = "gladys") -> int:
        """Run SQL command/query."""
        env = os.environ.copy()
        env["PGPASSWORD"] = "gladys"

        result = subprocess.run(
            ["psql", "-h", "localhost", "-p", str(LOCAL_PORTS.db),
             "-U", "gladys", "-d", database, "-c", sql],
            env=env,
        )
        return result.returncode

    def run_psql_shell(self, database: str = "gladys") -> int:
        """Open interactive database shell."""
        env = os.environ.copy()
        env["PGPASSWORD"] = "gladys"

        return subprocess.run(
            ["psql", "-h", "localhost", "-p", str(LOCAL_PORTS.db),
             "-U", "gladys", "-d", database],
            env=env,
        ).returncode

    def run_migration(self, file_filter: Optional[str] = None) -> int:
        """Run database migrations."""
        migrations_dir = ROOT / "src" / "memory" / "migrations"

        if not migrations_dir.exists():
            print(f"Migrations directory not found: {migrations_dir}")
            return 1

        files = sorted(f for f in migrations_dir.glob("*.sql") if not f.name.endswith(".bak"))

        if file_filter:
            files = [f for f in files if file_filter in f.name]

        if not files:
            print("No migrations found.")
            return 0

        print(f"Applying {len(files)} migrations to LOCAL database...")
        env = os.environ.copy()
        env["PGPASSWORD"] = "gladys"
        errors = 0

        for f in files:
            print(f"  Applying {f.name}...", end=" ", flush=True)
            result = subprocess.run(
                ["psql", "-h", "localhost", "-p", str(LOCAL_PORTS.db),
                 "-U", "gladys", "-d", "gladys", "-f", str(f)],
                capture_output=True,
                text=True,
                env=env,
            )

            if result.returncode != 0:
                stderr = result.stderr.lower()
                if "already exists" in stderr or "does not exist, skipping" in stderr:
                    print("OK (already applied)")
                else:
                    print("FAILED")
                    print(f"    {result.stderr.strip()}")
                    errors += 1
            else:
                print("OK")

        return 1 if errors else 0

    def clean_db(self, target: str) -> int:
        """Clean database tables."""
        tables = {
            "heuristics": "heuristics",
            "events": "episodic_events",
            "all": "heuristics, episodic_events, heuristic_fires",
        }
        t = tables.get(target, "heuristics")
        sql = f"TRUNCATE {t} CASCADE;"
        print(f"Executing: {sql}")
        return self.run_sql(sql)

    def run_test(self, test_file: Optional[str] = None) -> int:
        """Run integration tests."""
        test_dir = ROOT / "src" / "integration"
        env = {**os.environ, **get_test_env(LOCAL_PORTS)}

        if test_file:
            cmd = ["uv", "run", "python", test_file]
        else:
            cmd = ["uv", "run", "pytest", "-v"]

        print("Running tests in LOCAL env...")
        return subprocess.run(cmd, cwd=test_dir, env=env).returncode

    def _run_cache_cmd(self, args: List[str]) -> int:
        address = f"localhost:{LOCAL_PORTS.memory_rust}"
        # We run it using the venv from memory-python which has grpcio
        python_exe = ROOT / "src" / "memory" / "python" / ".venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            python_exe = "python" # Fallback
            
        cmd = [str(python_exe), str(ROOT / "scripts" / "_cache_client.py"), "--address", address] + args
        return subprocess.run(cmd).returncode

    def cache_stats(self) -> int:
        return self._run_cache_cmd(["stats"])

    def cache_list(self, limit: int = 0) -> int:
        return self._run_cache_cmd(["list", "--limit", str(limit)])

    def cache_flush(self) -> int:
        return self._run_cache_cmd(["flush"])

    def cache_evict(self, heuristic_id: str) -> int:
        return self._run_cache_cmd(["evict", heuristic_id])
