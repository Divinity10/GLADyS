import re
import sys
import os
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple, Any

class DriftChecker:
    def __init__(self, root_dir: Path):
        self.root = root_dir.resolve()
        self.codebase_map_path = self.root / "CODEBASE_MAP.md"
        self.services_dir = self.root / "src" / "services"
        self.proto_dir = self.root / "proto"
        self.env_path = self.root / ".env"
        self.docker_yml = self.root / "docker" / "docker-compose.yml"
        
        self.map_services: Dict[str, Any] = {} # Name -> {port, docker_port, proto_service, path, rpcs, proto_file}
        self.categories: Dict[str, List[str]] = {
            "Stale Paths": [],
            "Missing Services": [],
            "Port Drift": [],
            "Proto Drift": []
        }

    def log_error(self, category: str, message: str):
        if category in self.categories:
            self.categories[category].append(message)
        else:
            self.categories["Other"] = self.categories.get("Other", []) + [message]

    def parse_codebase_map(self):
        if not self.codebase_map_path.exists():
            print("ERROR: CODEBASE_MAP.md not found", file=sys.stderr)
            sys.exit(1)

        content = self.codebase_map_path.read_text(encoding="utf-8")
        
        # 1. Parse Service Table
        table_match = re.search(r"## Port Reference.*?\| Service \|.*?\|.*?\|(.*?)(?:\n\n|\Z)", content, re.S)
        if table_match:
            rows = table_match.group(1).strip().split("\n")
            for row in rows:
                if "---" in row or "Local Port" in row:
                    continue
                parts = [p.strip() for p in row.split("|") if p.strip()]
                if len(parts) >= 4:
                    name = parts[0]
                    local_port = parts[1]
                    docker_port = parts[2]
                    proto_svc = parts[3].strip("`")
                    if proto_svc == "-": proto_svc = None
                    self.map_services[name] = {
                        "local_port": local_port,
                        "docker_port": docker_port,
                        "proto_service": proto_svc,
                        "rpcs": set(),
                        "implementation_path": None,
                        "proto_file": None
                    }

        # 2. Parse Service Sections for paths and RPCs
        sections = re.split(r"### `([^`]+)`(?:\s+Service)?\s*\(([^)]+\.proto)\)", content)
        for i in range(1, len(sections), 3):
            svc_id = sections[i] # This might be the proto service name
            proto_file = sections[i+1]
            svc_content = sections[i+2]
            
            impl_match = re.search(r"\*\*Implemented by\*\*: `([^`]+)`", svc_content)
            impl_path = impl_match.group(1) if impl_match else None
            
            rpc_table_match = re.search(r"\| RPC \|.*?\|.*?\|(.*?)(?:\n\n|\Z)", svc_content, re.S)
            if rpc_table_match:
                rpc_matches = re.findall(r"\| `([^`]+)` \|", rpc_table_match.group(1))
            else:
                rpc_matches = []
            
            # Match this section to a service in the map
            found_svc = None
            for name, data in self.map_services.items():
                if data.get("proto_service") == svc_id or svc_id in name:
                    found_svc = name
                    break
            
            if found_svc:
                self.map_services[found_svc]["implementation_path"] = impl_path
                self.map_services[found_svc]["proto_file"] = proto_file
                for rpc in rpc_matches:
                    if rpc != "RPC":
                        self.map_services[found_svc]["rpcs"].add(rpc)
            else:
                # Service section exists but not in table
                self.map_services[svc_id] = {
                    "implementation_path": impl_path,
                    "proto_file": proto_file,
                    "rpcs": set(rpc for rpc in rpc_matches if rpc != "RPC"),
                    "proto_service": svc_id
                }

    def check_stale_paths(self):
        for name, data in self.map_services.items():
            path_str = data.get("implementation_path")
            if path_str:
                full_path = self.root / path_str
                if not full_path.exists():
                    self.log_error("Stale Paths", f"{name}: Referenced path `{path_str}` does not exist")

    def check_missing_services(self):
        if not self.services_dir.exists():
            return
            
        actual_services = {d.name for d in self.services_dir.iterdir() if d.is_dir()}
        
        mapped_service_dirs = set()
        for data in self.map_services.values():
            path_str = data.get("implementation_path")
            if path_str:
                parts = Path(path_str).parts
                if len(parts) >= 3 and parts[0] == "src" and parts[1] == "services":
                    mapped_service_dirs.add(parts[2])
                    
        # Also check name matches for common service names
        for svc in actual_services:
            if svc in mapped_service_dirs:
                continue
                
            found_by_name = False
            for name in self.map_services.keys():
                if svc.lower() in name.lower() or name.lower() in svc.lower():
                    found_by_name = True
                    break
            
            if not found_by_name:
                self.log_error("Missing Services", f"src/services/{svc} is not accounted for in CODEBASE_MAP.md")

    def check_port_drift(self):
        env_ports = {}
        if self.env_path.exists():
            env_content = self.env_path.read_text()
            matches = re.findall(r"([A-Z_]+PORT)\s*=\s*(\d+)", env_content)
            for key, val in matches:
                env_ports[key] = val

        docker_ports = {}
        if self.docker_yml.exists():
            docker_content = self.docker_yml.read_text()
            matches = re.findall(r"\"?(\d+):(\d+)\"?", docker_content)
            for host_p, cont_p in matches:
                docker_ports[cont_p] = host_p

        # Mapping of common service name parts to ENV prefixes
        service_to_prefix = {
            "Memory": "MEMORY",
            "Orchestrator": "ORCHESTRATOR",
            "Executive": "EXECUTIVE",
            "Salience": "SALIENCE",
            "Dashboard": "DASHBOARD",
            "Fun": "FUN_API",
            "Postgres": "DB"
        }

        for name, data in self.map_services.items():
            local_port = data.get("local_port")
            docker_port = data.get("docker_port")
            
            if not local_port: continue
            
            # Check ENV
            prefix = None
            for key_part, pref in service_to_prefix.items():
                if key_part.lower() in name.lower():
                    prefix = pref
                    break
            
            if prefix:
                env_key = f"{prefix}_PORT"
                if env_key in env_ports:
                    if env_ports[env_key] != local_port:
                        self.log_error("Port Drift", f"{name}: Map says {local_port}, .env `{env_key}` says {env_ports[env_key]}")
            
            # Check Docker
            if local_port in docker_ports and docker_ports[local_port] != docker_port:
                self.log_error("Port Drift", f"{name}: Map says Docker host port {docker_port}, docker-compose.yml says {docker_ports[local_port]} for internal port {local_port}")

    def check_proto_drift(self):
        # 1. Map existing .proto files and their services/RPCs
        all_proto_services: Dict[str, Dict[str, Set[str]]] = {} # filename -> {svc_name -> {rpcs}}
        
        if self.proto_dir.exists():
            for proto_file in self.proto_dir.glob("*.proto"):
                content = proto_file.read_text()
                services = {}
                # Find all services in file
                svc_blocks = re.findall(r"service\s+(\w+)\s*\{(.*?)\}", content, re.S)
                for svc_name, svc_body in svc_blocks:
                    rpcs = set(re.findall(r"rpc\s+(\w+)\s*\(", svc_body))
                    services[svc_name] = rpcs
                all_proto_services[proto_file.name] = services

        # 2. Check Map vs Actual
        for name, data in self.map_services.items():
            proto_svc_name = data.get("proto_service")
            proto_file = data.get("proto_file")
            
            if not proto_svc_name: continue
            
            if not proto_file:
                self.log_error("Proto Drift", f"{name}: Proto service `{proto_svc_name}` listed but no proto file specified")
                continue
                
            if proto_file not in all_proto_services:
                self.log_error("Proto Drift", f"{name}: Proto file `{proto_file}` not found in proto/")
                continue
                
            if proto_svc_name not in all_proto_services[proto_file]:
                self.log_error("Proto Drift", f"{name}: Service `{proto_svc_name}` not found in `{proto_file}`")
                continue
                
            actual_rpcs = all_proto_services[proto_file][proto_svc_name]
            mapped_rpcs = data.get("rpcs", set())
            
            missing_in_map = actual_rpcs - mapped_rpcs
            if missing_in_map:
                self.log_error("Proto Drift", f"{name}: RPCs in `{proto_file}` missing from map: {', '.join(sorted(missing_in_map))}")
                
            stale_in_map = mapped_rpcs - actual_rpcs
            if stale_in_map:
                self.log_error("Proto Drift", f"{name}: Stale RPCs in map for `{proto_file}`: {', '.join(sorted(stale_in_map))}")

        # 3. Check Actual vs Map (Bidirectional)
        for proto_file, services in all_proto_services.items():
            for svc_name in services:
                found_in_map = False
                for data in self.map_services.values():
                    if data.get("proto_service") == svc_name:
                        found_in_map = True
                        break
                if not found_in_map:
                    self.log_error("Proto Drift", f"Proto service `{svc_name}` in `{proto_file}` is missing from CODEBASE_MAP.md")

    def run(self) -> int:
        self.parse_codebase_map()
        self.check_stale_paths()
        self.check_missing_services()
        self.check_port_drift()
        self.check_proto_drift()
        
        total_issues = sum(len(msgs) for msgs in self.categories.values())
        
        if total_issues == 0:
            print("No drift detected.")
            return 0
        else:
            print(f"{total_issues} issues found\n")
            for category, msgs in self.categories.items():
                if msgs:
                    print(f"## {category}")
                    for msg in msgs:
                        print(f"- {msg}")
                    print()
            return 1

def main():
    root = Path(__file__).parent.parent.parent
    checker = DriftChecker(root)
    sys.exit(checker.run())

if __name__ == "__main__":
    main()