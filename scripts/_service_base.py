# Base abstractions for Service Management Scripts.
#
# This module defines the core ServiceManager, ServiceBackend, and Command patterns
# used to unify `docker.py` and `local.py`.

import abc
import argparse
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ServiceDefinition:
    """Definition of a manageable service."""
    name: str
    description: str
    port: int
    group: Optional[str] = None  # e.g., "memory" for memory-python/rust


class ServiceBackend(abc.ABC):
    """Abstract base for environment-specific operations (Docker vs Local)."""

    @abc.abstractmethod
    def start_service(self, names: List[str], wait: bool = True) -> bool:
        """Start one or more services. Returns True on success."""
        pass

    @abc.abstractmethod
    def stop_service(self, names: List[str]) -> bool:
        """Stop one or more services. Returns True on success."""
        pass

    @abc.abstractmethod
    def restart_service(self, names: List[str]) -> bool:
        """Restart one or more services. Returns True on success."""
        pass

    @abc.abstractmethod
    def get_service_status(self, name: str) -> Dict[str, Any]:
        """Get service status.
        Returns: {
            "running": bool,
            "healthy": bool,
            "status_text": str,
            "details": dict (optional)
        }
        """
        pass

    @abc.abstractmethod
    def get_logs(self, names: List[str], follow: bool = True, tail: Optional[int] = None) -> None:
        """Stream or view service logs."""
        pass

    @abc.abstractmethod
    def run_sql(self, sql: str, database: str = "gladys") -> int:
        """Run SQL command/query. Returns exit code."""
        pass
        
    @abc.abstractmethod
    def run_psql_shell(self, database: str = "gladys") -> int:
        """Open interactive database shell. Returns exit code."""
        pass

    @abc.abstractmethod
    def run_migration(self, file_filter: Optional[str] = None) -> int:
        """Run database migrations. Returns exit code."""
        pass
    
    @abc.abstractmethod
    def clean_db(self, target: str) -> int:
        """Clean database tables. Target: 'heuristics', 'events', 'all'."""
        pass

    @abc.abstractmethod
    def run_test(self, test_file: Optional[str] = None) -> int:
        """Run integration tests. Returns exit code."""
        pass

    @abc.abstractmethod
    def cache_stats(self) -> int:
        """Show cache statistics. Returns exit code."""
        pass

    @abc.abstractmethod
    def cache_list(self, limit: int = 0) -> int:
        """List cached heuristics. Returns exit code."""
        pass

    @abc.abstractmethod
    def cache_flush(self) -> int:
        """Flush entire cache. Returns exit code."""
        pass

    @abc.abstractmethod
    def cache_evict(self, heuristic_id: str) -> int:
        """Evict heuristic from cache. Returns exit code."""
        pass

    @abc.abstractmethod
    def queue_stats(self) -> int:
        """Show event queue statistics. Returns exit code."""
        pass

    @abc.abstractmethod
    def queue_list(self, limit: int = 0) -> int:
        """List events in the queue. Returns exit code."""
        pass

    @abc.abstractmethod
    def queue_watch(self, interval: float = 1.0) -> int:
        """Watch queue activity in real-time. Returns exit code."""
        pass

    @abc.abstractmethod
    def get_service_health(self, name: str, detailed: bool = False) -> Dict[str, Any]:
        """Get gRPC health status from a service.
        Returns: {
            "status": str (HEALTHY, UNHEALTHY, DEGRADED, UNKNOWN),
            "message": str,
            "uptime_seconds": int (if detailed),
            "details": dict (if detailed),
            "error": str (if connection failed)
        }
        """
        pass

    def build_service(self, names: List[str], no_cache: bool = False) -> bool:
        """Build Docker images for services. Returns True on success.

        Default implementation returns True (no-op for local backend).
        Override in DockerBackend.
        """
        print("Build not supported for this backend.")
        return True


class ServiceManager:
    """Main entry point for service management CLI."""

    def __init__(self, backend: ServiceBackend, services: Dict[str, ServiceDefinition]):
        self.backend = backend
        self.services = services
        self.groups = self._build_groups()
        self.parser = self._setup_parser()

    def _build_groups(self) -> Dict[str, List[str]]:
        """Index services by group."""
        groups: Dict[str, List[str]] = {}
        for name, svc in self.services.items():
            if svc.group:
                if svc.group not in groups:
                    groups[svc.group] = []
                groups[svc.group].append(name)
        return groups

    def resolve_services(self, name: str) -> List[str]:
        """Resolve 'all', groups, or individual service names."""
        if name == "all":
            return list(self.services.keys())
        if name in self.groups:
            return self.groups[name]
        if name in self.services:
            return [name]
        
        # Fallback: check if it's a comma-separated list
        if "," in name:
            parts = [p.strip() for p in name.split(",")]
            resolved = []
            for p in parts:
                resolved.extend(self.resolve_services(p))
            return resolved

        raise ValueError(f"Unknown service: {name}. Valid: all, {', '.join(self.groups.keys())}, {', '.join(self.services.keys())}")

    def _setup_parser(self) -> argparse.ArgumentParser:
        """Configure argparse with standard commands."""
        parser = argparse.ArgumentParser(
            description="Manage GLADyS services",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        subparsers = parser.add_subparsers(dest="command", required=True)

        # Service Commands
        self._add_service_command(subparsers, "start", "Start service(s)",
                                  [("--no-wait", "store_true", "Don't wait for healthy")])
        self._add_service_command(subparsers, "stop", "Stop service(s)")
        self._add_service_command(subparsers, "restart", "Restart service(s)")
        self._add_service_command(subparsers, "build", "Build Docker images (Docker only)",
                                  [("--no-cache", "store_true", "Rebuild without cache")])
        
        # Status
        status = subparsers.add_parser("status", help="Show service status")
        status.set_defaults(func=self.cmd_status)

        # Health (gRPC health check)
        health = subparsers.add_parser("health", help="Check gRPC health endpoints")
        health.add_argument("service", nargs="?", default="all", help="Service to check (default: all)")
        health.add_argument("-d", "--detailed", action="store_true", help="Show detailed health info")
        health.set_defaults(func=self.cmd_health)

        # Logs
        logs = subparsers.add_parser("logs", help="View service logs (local: ~/.gladys/logs/, docker: container logs)")
        logs.add_argument("service", help="Service to view (or 'all')")
        logs.add_argument("-f", "--follow", action="store_true", help="Follow log output (Docker only)")
        logs.add_argument("--tail", type=int, help="Number of lines to show")
        logs.set_defaults(func=self.cmd_logs)

        # Database
        psql = subparsers.add_parser("psql", help="Database shell")
        psql.add_argument("-c", "--command", help="Run single SQL command")
        psql.set_defaults(func=self.cmd_psql)

        query = subparsers.add_parser("query", help="Run SQL query")
        query.add_argument("sql", help="SQL query string")
        query.set_defaults(func=self.cmd_query)

        migrate = subparsers.add_parser("migrate", help="Run migrations")
        migrate.add_argument("-f", "--file", help="Filter migration file name")
        migrate.set_defaults(func=self.cmd_migrate)

        clean = subparsers.add_parser("clean", help="Clean database")
        clean.add_argument("target", choices=["heuristics", "events", "all"],
                          default="heuristics", nargs="?", help="Table set to clean")
        clean.set_defaults(func=self.cmd_clean)

        # Testing
        test = subparsers.add_parser("test", help="Run integration tests")
        test.add_argument("file", nargs="?", help="Specific test file")
        test.set_defaults(func=self.cmd_test)

        # Sync Check
        sync = subparsers.add_parser("sync-check", help="Check environment sync status")
        sync.set_defaults(func=self.cmd_sync_check)

        # Reset
        reset = subparsers.add_parser("reset", help="Full reset (stop, clean, start)")
        reset.set_defaults(func=self.cmd_reset)

        # Cache Management
        cache = subparsers.add_parser("cache", help="Cache management (memory-rust)")
        cache_sub = cache.add_subparsers(dest="cache_command", required=True)

        cache_stats = cache_sub.add_parser("stats", help="Show cache statistics")
        cache_stats.set_defaults(func=self.cmd_cache_stats)

        cache_list = cache_sub.add_parser("list", help="List cached heuristics")
        cache_list.add_argument("--limit", type=int, default=0, help="Max entries to show")
        cache_list.set_defaults(func=self.cmd_cache_list)

        cache_flush = cache_sub.add_parser("flush", help="Clear entire heuristic cache")
        cache_flush.set_defaults(func=self.cmd_cache_flush)

        cache_evict = cache_sub.add_parser("evict", help="Remove single heuristic from cache")
        cache_evict.add_argument("id", help="Heuristic ID to evict")
        cache_evict.set_defaults(func=self.cmd_cache_evict)

        # Queue Management (orchestrator event queue)
        queue = subparsers.add_parser("queue", help="Event queue management (orchestrator)")
        queue_sub = queue.add_subparsers(dest="queue_command", required=True)

        queue_stats = queue_sub.add_parser("stats", help="Show event queue statistics")
        queue_stats.set_defaults(func=self.cmd_queue_stats)

        queue_list = queue_sub.add_parser("list", help="List events in the queue")
        queue_list.add_argument("--limit", type=int, default=0, help="Max events to show (0=all)")
        queue_list.set_defaults(func=self.cmd_queue_list)

        queue_watch = queue_sub.add_parser("watch", help="Watch queue activity in real-time (Ctrl+C to stop)")
        queue_watch.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds (default: 1.0)")
        queue_watch.set_defaults(func=self.cmd_queue_watch)

        return parser

    def _add_service_command(self, subparsers, name, help_text, extra_args=None):
        p = subparsers.add_parser(name, help=help_text)
        p.add_argument("service", help=f"Service to {name} (or 'all', 'memory')")
        if extra_args:
            for flag, action, help_msg in extra_args:
                p.add_argument(flag, action=action, help=help_msg)
        p.set_defaults(func=getattr(self, f"cmd_{name}"))

    # --- Command Handlers ---

    def cmd_start(self, args):
        services = self.resolve_services(args.service)
        wait = not getattr(args, "no_wait", False)
        return 0 if self.backend.start_service(services, wait=wait) else 1

    def cmd_stop(self, args):
        services = self.resolve_services(args.service)
        return 0 if self.backend.stop_service(services) else 1

    def cmd_restart(self, args):
        services = self.resolve_services(args.service)
        return 0 if self.backend.restart_service(services) else 1

    def cmd_build(self, args):
        services = self.resolve_services(args.service)
        no_cache = getattr(args, "no_cache", False)
        return 0 if self.backend.build_service(services, no_cache=no_cache) else 1

    def _check_ollama_status(self) -> dict:
        """Check if Ollama LLM server is running.

        Uses OLLAMA_URL and OLLAMA_MODEL environment variables.
        Returns endpoint name, URL, model, and connection status.
        """
        import os
        ollama_url = os.environ.get("OLLAMA_URL")
        ollama_model = os.environ.get("OLLAMA_MODEL")
        endpoint_name = os.environ.get("OLLAMA_ENDPOINT")

        if not ollama_url:
            return {
                "running": False, "healthy": False,
                "status_text": "not configured",
                "url": None, "model": None, "endpoint": None
            }

        # Normalize URL (ensure it has /api/tags endpoint)
        base_url = ollama_url.rstrip("/")
        check_url = f"{base_url}/api/tags"

        try:
            req = urllib.request.Request(
                check_url,
                headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return {
                        "running": True, "healthy": True,
                        "status_text": "running",
                        "url": ollama_url, "model": ollama_model, "endpoint": endpoint_name
                    }
        except urllib.error.URLError:
            pass
        except Exception:
            pass
        return {
            "running": False, "healthy": False,
            "status_text": "unreachable",
            "url": ollama_url, "model": ollama_model, "endpoint": endpoint_name
        }

    def cmd_status(self, args):
        print(f"{ 'Service':<20} {'Status':<20} {'Port':<8} Description")
        print("-" * 80)
        for name, svc in self.services.items():
            st = self.backend.get_service_status(name)
            status_icon = "[OK]" if st.get("healthy") else ("[--]" if not st.get("running") else "[!!]")
            status_text = st.get("status_text", "unknown")
            print(f"{name:<20} {status_icon} {status_text:<15} {svc.port:<8} {svc.description}")

        # Check external dependencies
        print("-" * 80)
        print("External Dependencies:")
        ollama = self._check_ollama_status()
        ollama_icon = "[OK]" if ollama.get("healthy") else "[--]"
        ollama_text = ollama.get("status_text", "unknown")
        ollama_url = ollama.get("url")
        ollama_model = ollama.get("model")
        ollama_endpoint = ollama.get("endpoint")
        if ollama_url:
            # Extract host:port from URL for display
            from urllib.parse import urlparse
            parsed = urlparse(ollama_url)
            port_str = str(parsed.port) if parsed.port else "11434"
            endpoint_label = f"[{ollama_endpoint}] " if ollama_endpoint else ""
            model_label = f" model={ollama_model}" if ollama_model else ""
            desc = f"LLM {endpoint_label}({parsed.hostname}){model_label}"
        else:
            port_str = "-----"
            desc = "LLM Backend (set OLLAMA_URL)"
        print(f"{'ollama':<20} {ollama_icon} {ollama_text:<15} {port_str:<8} {desc}")
        return 0

    def cmd_health(self, args):
        """Check gRPC health endpoints."""
        services = self.resolve_services(args.service)
        detailed = args.detailed

        all_healthy = True
        for name in services:
            svc = self.services[name]
            health = self.backend.get_service_health(name, detailed=detailed)

            status = health.get("status", "UNKNOWN")
            if status == "HEALTHY":
                icon = "[OK]"
            elif status == "DEGRADED":
                icon = "[~~]"
                all_healthy = False
            elif status == "UNHEALTHY":
                icon = "[!!]"
                all_healthy = False
            else:
                icon = "[??]"
                all_healthy = False

            error = health.get("error")
            if error:
                print(f"{name:<20} {icon} {status:<12} (error: {error})")
            else:
                msg = health.get("message", "")
                uptime = health.get("uptime_seconds")
                uptime_str = f" uptime={uptime}s" if uptime is not None else ""
                msg_str = f" {msg}" if msg else ""
                print(f"{name:<20} {icon} {status:<12}{uptime_str}{msg_str}")

            if detailed and "details" in health:
                for k, v in health["details"].items():
                    print(f"    {k}: {v}")

        return 0 if all_healthy else 1

    def cmd_logs(self, args):
        services = self.resolve_services(args.service)
        self.backend.get_logs(services, follow=args.follow, tail=args.tail)
        return 0

    def cmd_psql(self, args):
        if args.command:
            return self.backend.run_sql(args.command)
        return self.backend.run_psql_shell()

    def cmd_query(self, args):
        return self.backend.run_sql(args.sql)

    def cmd_migrate(self, args):
        return self.backend.run_migration(args.file)

    def cmd_clean(self, args):
        return self.backend.clean_db(args.target)

    def cmd_test(self, args):
        return self.backend.run_test(args.file)

    def cmd_sync_check(self, args):
        """Run environment sync check."""
        from _sync_check import run_sync_check
        return run_sync_check()

    def cmd_reset(self, args):
        print("Resetting environment...")
        success = True
        
        if not self.backend.stop_service(list(self.services.keys())):
            print("Failed to stop services.")
            success = False
            
        if self.backend.clean_db("all") != 0:
            print("Failed to clean database.")
            success = False
            
        if not self.backend.start_service(list(self.services.keys())):
            print("Failed to start services.")
            success = False
            
        return 0 if success else 1

    def cmd_cache_stats(self, args):
        return self.backend.cache_stats()

    def cmd_cache_list(self, args):
        return self.backend.cache_list(args.limit)

    def cmd_cache_flush(self, args):
        return self.backend.cache_flush()

    def cmd_cache_evict(self, args):
        return self.backend.cache_evict(args.id)

    def cmd_queue_stats(self, args):
        return self.backend.queue_stats()

    def cmd_queue_list(self, args):
        return self.backend.queue_list(args.limit)

    def cmd_queue_watch(self, args):
        return self.backend.queue_watch(args.interval)

    def run(self):
        args = self.parser.parse_args()
        try:
            sys.exit(args.func(args))
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nInterrupted.")
            sys.exit(130)