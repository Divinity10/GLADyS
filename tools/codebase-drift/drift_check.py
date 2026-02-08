import re
import sys
from pathlib import Path
from typing import List, Set


class DriftChecker:
    """Validates CONCEPT_MAP.md against the actual codebase.

    Checks that every directory listed in the map exists, and that every
    service directory under src/services/ appears in the map.

    All derived data (ports, RPCs, schema, routers) is validated by
    ``codebase-info`` which reads authoritative sources directly.
    """

    def __init__(self, root_dir: Path):
        self.root = root_dir.resolve()
        self.codebase_map_path = self.root / "CONCEPT_MAP.md"
        self.services_dir = self.root / "src" / "services"
        self.issues: List[str] = []

    def parse_mapped_paths(self) -> Set[str]:
        """Extract backtick-enclosed directory paths from CONCEPT_MAP.md.

        Convention: directory paths end with ``/``.  Non-path backtick text
        (command names, file references) does not and is ignored.
        """
        if not self.codebase_map_path.exists():
            print("ERROR: CONCEPT_MAP.md not found", file=sys.stderr)
            sys.exit(1)

        content = self.codebase_map_path.read_text(encoding="utf-8")
        return set(re.findall(r"`([^`]+/)`", content))

    def check_paths_exist(self, mapped_paths: Set[str]):
        """Verify every mapped directory actually exists."""
        for path_str in sorted(mapped_paths):
            if not (self.root / path_str).exists():
                self.issues.append(f"Mapped path does not exist: `{path_str}`")

    def check_unmapped_services(self, mapped_paths: Set[str]):
        """Check that all src/services/ directories appear in the map."""
        if not self.services_dir.exists():
            return

        mapped_svc_dirs = set()
        for p in mapped_paths:
            parts = Path(p).parts
            if len(parts) >= 3 and parts[0] == "src" and parts[1] == "services":
                mapped_svc_dirs.add(parts[2])

        actual = {d.name for d in self.services_dir.iterdir() if d.is_dir()}
        for svc in sorted(actual - mapped_svc_dirs):
            self.issues.append(f"Service directory not in map: `src/services/{svc}/`")

    def run(self) -> int:
        mapped_paths = self.parse_mapped_paths()
        self.check_paths_exist(mapped_paths)
        self.check_unmapped_services(mapped_paths)

        if not self.issues:
            print("No drift detected.")
            return 0
        else:
            print(f"{len(self.issues)} issues found\n")
            for issue in self.issues:
                print(f"- {issue}")
            return 1


def main():
    root = Path(__file__).parent.parent.parent
    checker = DriftChecker(root)
    sys.exit(checker.run())


if __name__ == "__main__":
    main()
