"""Docker backend implementation for Service Management Scripts."""

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from _gladys import DOCKER_PORTS, ROOT, get_test_env
from _service_base import ServiceBackend


class DockerBackend(ServiceBackend):
    """Docker-specific service operations."""

    def __init__(self, compose_file: Optional[Path] = None):
        self.compose_file = compose_file or (ROOT / "src" / "integration" / "docker-compose.yml")
        self.containers = {
            "memory-python": "gladys-integration-memory-python",
            "memory-rust": "gladys-integration-memory-rust",
            "orchestrator": "gladys-integration-orchestrator",
            "executive-stub": "gladys-integration-executive-stub",
            "db": "gladys-integration-db",
        }

    def _compose_cmd(self, args: List[str], capture: bool = False) -> subprocess.CompletedProcess:
        """Run a docker-compose command."""
        cmd = ["docker-compose", "-f", str(self.compose_file)] + args
        return subprocess.run(cmd, capture_output=capture, text=True, encoding="utf-8")

    def _exec_db(self, cmd: List[str], capture: bool = False) -> subprocess.CompletedProcess:
        """Execute command in database container."""
        full_cmd = ["docker", "exec", "-e", "PGPASSWORD=gladys", self.containers["db"]] + cmd
        return subprocess.run(full_cmd, capture_output=capture, text=True, encoding="utf-8")

    def start_service(self, names: List[str], wait: bool = True) -> bool:
        """Start services using docker-compose up -d."""
        # Ensure db is up first if starting app services
        if any(n != "db" for n in names):
            self._compose_cmd(["up", "-d", "postgres"])
            print("Waiting for database to be ready...")
            for _ in range(30):
                st = self.get_service_status("db")
                if st.get("healthy"):
                    print("Database ready.")
                    break
                time.sleep(1)
            else:
                print("Warning: Database start timed out or is unhealthy.")

        print(f"Starting DOCKER services: {', '.join(names)}...")
        # Map names to compose service names (postgres is named 'postgres' in yaml, 'db' in our abstraction)
        compose_names = [n if n != "db" else "postgres" for n in names]
        
        # 'up -d' handles creation and updates better than 'start'
        result = self._compose_cmd(["up", "-d"] + compose_names)
        
        if wait and result.returncode == 0:
            print("Waiting for services to be healthy...")
            # We use docker ps to wait/check? No, compose doesn't have a 'wait' command until V2.
            # We'll poll inspect manually for a few seconds
            for _ in range(30):
                unhealthy = []
                for name in names:
                    if name == "db" or name == "postgres": continue # DB takes longer, skip fast check
                    st = self.get_service_status(name)
                    if not st.get("healthy"):
                        unhealthy.append(name)
                
                if not unhealthy:
                    print("All services healthy.")
                    break
                
                print(f"Waiting for: {', '.join(unhealthy)}...")
                time.sleep(1)
                
        return result.returncode == 0

    def stop_service(self, names: List[str]) -> bool:
        compose_names = [n if n != "db" else "postgres" for n in names]
        print(f"Stopping DOCKER services: {', '.join(names)}...")
        result = self._compose_cmd(["stop"] + compose_names)
        return result.returncode == 0

    def restart_service(self, names: List[str]) -> bool:
        compose_names = [n if n != "db" else "postgres" for n in names]
        print(f"Restarting DOCKER services: {', '.join(names)}...")
        # Use up -d --force-recreate for robust restarts (picks up new images/config)
        result = self._compose_cmd(["up", "-d", "--force-recreate"] + compose_names)
        return result.returncode == 0

    def build_service(self, names: List[str], no_cache: bool = False) -> bool:
        """Build Docker images for specified services."""
        # Filter out 'db' - it uses a pre-built image
        buildable = [n for n in names if n != "db"]
        if not buildable:
            print("No buildable services specified (db uses pre-built image).")
            return True

        compose_names = [n if n != "db" else "postgres" for n in buildable]
        print(f"Building DOCKER images: {', '.join(buildable)}...")

        cmd = ["build"]
        if no_cache:
            cmd.append("--no-cache")
        cmd.extend(compose_names)

        result = self._compose_cmd(cmd)
        if result.returncode == 0:
            print("Build complete. Use 'restart' to apply new images.")
        return result.returncode == 0

    def get_service_status(self, name: str) -> Dict[str, Any]:
        container = self.containers.get(name)
        if not container:
            return {"running": False, "healthy": False, "status_text": "unknown"}

        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}|{{.State.Health.Status}}", container],
            capture_output=True, text=True
        )
        
        if result.returncode != 0:
            return {"running": False, "healthy": False, "status_text": "stopped"}

        parts = result.stdout.strip().split("|")
        status = parts[0] if parts else "unknown"
        health = parts[1] if len(parts) > 1 else ""
        
        is_running = status == "running"
        is_healthy = health == "healthy"
        
        status_text = status
        if health:
            status_text += f" ({health})"

        return {
            "running": is_running,
            "healthy": is_healthy,
            "status_text": status_text
        }

    def get_service_health(self, name: str, detailed: bool = False) -> Dict[str, Any]:
        """Get gRPC health status from a service."""
        # Map service names to ports
        port_map = {
            "memory-python": DOCKER_PORTS.memory_python,
            "memory-rust": DOCKER_PORTS.memory_rust,
            "orchestrator": DOCKER_PORTS.orchestrator,
            "executive-stub": DOCKER_PORTS.executive,
        }

        port = port_map.get(name)
        if not port:
            return {"status": "UNKNOWN", "error": "Unknown service or no health endpoint"}

        # Check if service is running first
        st = self.get_service_status(name)
        if not st.get("running"):
            return {"status": "UNKNOWN", "error": "Service not running"}

        # Use the health client script
        python_exe = ROOT / "src" / "memory" / "python" / ".venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            python_exe = ROOT / "src" / "memory" / "python" / ".venv" / "bin" / "python"
        if not python_exe.exists():
            print("Warning: Using system python fallback for health check")
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
        compose_names = [n if n != "db" else "postgres" for n in names]
        cmd = ["logs"]
        if follow:
            cmd.append("-f")
        if tail:
            cmd.extend(["--tail", str(tail)])
        
        cmd.extend(compose_names)
        self._compose_cmd(cmd)

    def run_sql(self, sql: str, database: str = "gladys") -> int:
        cmd = ["psql", "-U", "gladys", "-d", database, "-c", sql]
        result = self._exec_db(cmd)
        return result.returncode

    def run_psql_shell(self, database: str = "gladys") -> int:
        # Interactive mode requires direct subprocess call, not _exec_db wrapper which captures output
        cmd = ["docker", "exec", "-it", "-e", "PGPASSWORD=gladys", self.containers["db"], 
               "psql", "-U", "gladys", "-d", database]
        return subprocess.run(cmd).returncode

    def run_migration(self, file_filter: Optional[str] = None) -> int:
        # Reuse existing migration logic concept but simplified
        migrations_dir = ROOT / "src" / "memory" / "migrations"
        files = sorted(migrations_dir.glob("*.sql"))
        
        if file_filter:
            files = [f for f in files if file_filter in f.name]
            
        if not files:
            print("No migrations found.")
            return 0
            
        print(f"Applying {len(files)} migrations...")
        errors = 0
        for f in files:
            print(f"Applying {f.name}...")
            sql = f.read_text(encoding="utf-8")
            if self.run_sql(sql) != 0:
                print(f"Failed to apply {f.name}")
                errors += 1
        
        return 1 if errors else 0

    def clean_db(self, target: str) -> int:
        tables = {
            "heuristics": "heuristics",
            "events": "episodic_events",
            # Explicitly include heuristic_fires in 'all'
            "all": "heuristics, episodic_events, heuristic_fires" 
        }
        t = tables.get(target, "heuristics")
        sql = f"TRUNCATE {t} CASCADE;"
        print(f"Executing: {sql}")
        return self.run_sql(sql)

    def run_test(self, test_file: Optional[str] = None) -> int:
        test_dir = ROOT / "src" / "integration"
        env = {**os.environ, **get_test_env(DOCKER_PORTS)}
        
        cmd = ["uv", "run"]
        if test_file:
            cmd.extend(["python", test_file])
        else:
            cmd.extend(["pytest", "-v"])
            
        print(f"Running tests in DOCKER env...")
        return subprocess.run(cmd, cwd=test_dir, env=env).returncode

    def _run_cache_cmd(self, args: List[str]) -> int:
        address = f"localhost:{DOCKER_PORTS.memory_rust}"
        # We run it using the venv from memory-python which has grpcio
        python_exe = ROOT / "src" / "memory" / "python" / ".venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            print("Warning: Using system python fallback for cache command")
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

    def _run_queue_cmd(self, args: List[str]) -> int:
        """Run a queue client command against orchestrator."""
        address = f"localhost:{DOCKER_PORTS.orchestrator}"
        # Use orchestrator venv
        python_exe = ROOT / "src" / "orchestrator" / ".venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            # Fallback to memory-python venv
            python_exe = ROOT / "src" / "memory" / "python" / ".venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            print("Warning: Using system python fallback for queue command")
            python_exe = Path("python")

        cmd = [str(python_exe), str(ROOT / "scripts" / "_orchestrator.py"), "--address", address] + args
        return subprocess.run(cmd).returncode

    def queue_stats(self) -> int:
        return self._run_queue_cmd(["stats"])

    def queue_list(self, limit: int = 0) -> int:
        args = ["list"]
        if limit > 0:
            args.extend(["--limit", str(limit)])
        return self._run_queue_cmd(args)

    def queue_watch(self, interval: float = 1.0) -> int:
        args = ["watch", "--interval", str(interval)]
        return self._run_queue_cmd(args)
