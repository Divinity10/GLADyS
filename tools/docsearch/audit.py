import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

class DocAudit:
    EXCLUDED_DIRS = {
        "archive", "prompts", "coordination", "workflow", 
        "plans", "plan", "reviews"
    }

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.docs_dir = (self.project_root / "docs").resolve()
        self.index_path = (self.docs_dir / "INDEX.md").resolve()
        self.link_pattern = re.compile(r'\[.*?\]\((.*?)\)')
        self.section_pattern = re.compile(r'^##\s+(.*)')

    def get_all_md_files(self) -> Set[Path]:
        """Recursively find all .md files in docs/, respecting exclusions."""
        md_files = set()
        for root, dirs, files in os.walk(self.docs_dir):
            rel_root = Path(root).relative_to(self.docs_dir)
            
            # Skip excluded directories
            if any(part in self.EXCLUDED_DIRS for part in rel_root.parts):
                continue
            
            # Also skip hidden dirs like .git or .venv if they somehow end up in docs
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in self.EXCLUDED_DIRS]
            
            for file in files:
                if file.endswith(".md"):
                    md_files.add(Path(root) / file)
        
        return md_files

    def parse_index_links(self) -> Set[Path]:
        """Extract all markdown links from INDEX.md that resolve within docs/."""
        links = set()
        if not self.index_path.exists():
            return links

        content = self.index_path.read_text(encoding="utf-8")
        for match in self.link_pattern.finditer(content):
            path_str = match.group(1)
            # Ignore external links and anchors
            if path_str.startswith(("http", "mailto:")):
                continue
            if "#" in path_str:
                path_str = path_str.split("#")[0]
            if not path_str:
                continue

            # Resolve relative to docs/ (where INDEX.md lives)
            try:
                abs_path = (self.docs_dir / path_str).resolve()
                if abs_path.is_relative_to(self.docs_dir):
                    links.add(abs_path)
            except (ValueError, Exception):
                continue
        
        return links

    @staticmethod
    def heading_to_anchor(heading_text: str) -> str:
        """Convert a markdown heading to a GitHub-style anchor ID.

        GitHub's algorithm: strip inline markdown, lowercase, remove
        non-word/space/hyphen chars, replace each space with one hyphen.
        Unlike many implementations, GitHub does NOT collapse whitespace —
        ``Health & Wellness`` becomes ``health--wellness`` (& removed,
        two spaces become two hyphens).
        """
        text = heading_text.lower()
        # Strip inline markdown: **bold**, *italic*, `code`, [link](url)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
        text = re.sub(r'\[(.+?)\]\(.*?\)', r'\1', text)
        # Keep only word chars (letters, digits, underscore), spaces, hyphens
        text = re.sub(r'[^\w\s-]', '', text)
        text = text.strip()
        # Each whitespace char becomes one hyphen (no collapse)
        text = re.sub(r'\s', '-', text)
        return text

    def extract_anchors(self, file_path: Path) -> Set[str]:
        """Extract all valid anchor IDs from a markdown file's headings."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return set()

        anchors: Set[str] = set()
        heading_re = re.compile(r'^#{1,6}\s+(.+)', re.MULTILINE)
        counts: Dict[str, int] = {}

        for match in heading_re.finditer(content):
            raw = match.group(1).strip()
            anchor = self.heading_to_anchor(raw)
            if not anchor:
                continue
            # GitHub dedup: first is bare, subsequent get -1, -2, ...
            if anchor in counts:
                counts[anchor] += 1
                anchors.add(f"{anchor}-{counts[anchor]}")
            else:
                counts[anchor] = 0
                anchors.add(anchor)

        return anchors

    def check_broken_anchors(self) -> List[Tuple[Path, str, str]]:
        """Find broken anchor links across all markdown files.

        Scans docs/ (all subdirs) plus root-level .md files.
        Returns list of (source_file, link_target, anchor) tuples.
        """
        broken: List[Tuple[Path, str, str]] = []
        anchor_cache: Dict[Path, Set[str]] = {}

        # Collect files to scan — docs/ fully (no exclusions) + root .md
        scan_files: Set[Path] = set()
        if self.docs_dir.exists():
            for root, dirs, files in os.walk(self.docs_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for f in files:
                    if f.endswith(".md"):
                        scan_files.add((Path(root) / f).resolve())
        for f in self.project_root.iterdir():
            if f.is_file() and f.suffix == ".md":
                scan_files.add(f.resolve())

        for source in scan_files:
            try:
                content = source.read_text(encoding="utf-8")
            except Exception:
                continue

            for match in self.link_pattern.finditer(content):
                link_url = match.group(1)
                if link_url.startswith(("http", "mailto:")):
                    continue
                if "#" not in link_url:
                    continue

                file_part, anchor = link_url.split("#", 1)
                if not anchor:
                    continue

                # Skip GitHub line references (#L123 or #L10-L20)
                if re.match(r'L\d+', anchor):
                    continue

                # Resolve target file
                if file_part:
                    target = (source.parent / file_part).resolve()
                    if not target.exists():
                        target = (self.project_root / file_part).resolve()
                    if not target.exists():
                        continue  # Dead link — reported by dead-link check
                    # Only validate heading anchors in markdown files
                    if target.suffix != ".md":
                        continue
                else:
                    # Pure anchor (#section) — same file
                    target = source

                # Validate anchor against target headings
                if target not in anchor_cache:
                    anchor_cache[target] = self.extract_anchors(target)

                if anchor not in anchor_cache[target]:
                    broken.append((source, link_url, anchor))

        return broken

    def get_sections(self) -> List[str]:
        """Get a list of ## sections in INDEX.md."""
        sections = []
        if not self.index_path.exists():
            return sections

        content = self.index_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            match = self.section_pattern.match(line)
            if match:
                sections.append(match.group(1).strip())
        return sections

    def run_audit(self, fix: bool = False) -> int:
        """Run the audit and report findings. Returns 1 if issues found, 0 otherwise."""
        if not self.index_path.exists():
            print(f"Error: {self.index_path} not found.")
            return 1

        all_md_files = self.get_all_md_files()
        index_links = self.parse_index_links()

        # 1. Dead Links: Paths in INDEX.md that don't exist
        dead_links = {p for p in index_links if not p.exists()}
        
        # 2. Orphan Docs: Files in docs/ not in INDEX.md (excluding excluded dirs)
        # INDEX.md itself is not an orphan
        orphan_docs = {p for p in all_md_files if p not in index_links and p != self.index_path}

        # 3. Coverage Gaps: design/*.md not in INDEX.md (excluding design/archive/)
        design_dir = self.docs_dir / "design"
        design_archive = design_dir / "archive"
        coverage_gaps = {
            p for p in orphan_docs 
            if p.is_relative_to(design_dir) and not p.is_relative_to(design_archive)
        }

        issues_found = False
        
        print("=== DocSearch Audit Report ===")
        
        if dead_links:
            issues_found = True
            print(f"\n[!] Dead Links ({len(dead_links)}):")
            for p in sorted(dead_links):
                try:
                    print(f"  - {p.relative_to(self.docs_dir)}")
                except ValueError:
                    print(f"  - {p}")
        else:
            print("\n[OK] No dead links found.")

        if orphan_docs:
            issues_found = True
            print(f"\n[!] Orphan Docs ({len(orphan_docs)}):")
            for p in sorted(orphan_docs):
                try:
                    print(f"  - {p.relative_to(self.docs_dir)}")
                except ValueError:
                    print(f"  - {p}")
        else:
            print("\n[OK] No orphan docs found.")

        if coverage_gaps:
            issues_found = True
            print(f"\n[!] Coverage Gaps (Design docs missing from INDEX) ({len(coverage_gaps)}):")
            for p in sorted(coverage_gaps):
                try:
                    print(f"  - {p.relative_to(self.docs_dir)}")
                except ValueError:
                    print(f"  - {p}")
        else:
            print("\n[OK] No coverage gaps found.")

        # 4. Broken Anchors: Links with #anchor where anchor doesn't resolve
        broken_anchors = self.check_broken_anchors()

        if broken_anchors:
            issues_found = True
            print(f"\n[!] Broken Anchors ({len(broken_anchors)}):")
            for source, link, anchor in sorted(broken_anchors):
                try:
                    rel_source = source.relative_to(self.project_root)
                except ValueError:
                    rel_source = source
                print(f"  - {rel_source} -> {link}")
        else:
            print("\n[OK] No broken anchors found.")

        if fix and orphan_docs:
            self.fix_orphans(orphan_docs)
            return 0 if not dead_links and not coverage_gaps else 1

        return 1 if issues_found else 0

    def fix_orphans(self, orphans: Set[Path]):
        """Interactively add orphan docs to INDEX.md."""
        sections = self.get_sections()
        if not sections:
            print("No sections found in INDEX.md to add docs to.")
            return

        print("\n=== Interactive Fix: Adding Orphans to INDEX.md ===")
        
        added_any = False
        for orphan in sorted(orphans):
            rel_path = orphan.relative_to(self.docs_dir)
            print(f"\nOrphan: {rel_path}")
            print("Select section to add to (or 's' to skip, 'q' to quit):")
            for i, section in enumerate(sections):
                print(f"  {i+1}. {section}")
            
            choice = input("> ").strip().lower()
            if choice == 'q':
                break
            if choice == 's' or not choice:
                continue
            
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(sections):
                    target_section = sections[idx]
                    self._add_to_section(rel_path, target_section)
                    added_any = True
                else:
                    print("Invalid choice.")
            except ValueError:
                print("Invalid input.")

        if added_any:
            print("\nINDEX.md updated.")

    def _add_to_section(self, rel_path: Path, section_name: str):
        """Append a markdown link to the specified section in INDEX.md."""
        content = self.index_path.read_text(encoding="utf-8").splitlines()
        new_content = []
        in_section = False
        added = False
        
        for i, line in enumerate(content):
            new_content.append(line)
            match = self.section_pattern.match(line)
            if match and match.group(1).strip() == section_name:
                in_section = True
                continue
            
            if in_section and not added:
                is_next_section = False
                if i + 1 < len(content):
                    next_line = content[i+1]
                    if self.section_pattern.match(next_line) or next_line.startswith("---"):
                        is_next_section = True
                else:
                    is_next_section = True
                
                if is_next_section:
                    link_line = f"| **New** | [{rel_path.name}]({rel_path.as_posix()}) | Automatically added orphan. |"
                    has_table = False
                    for j in range(i, max(-1, i-5), -1):
                        if "|" in content[j]:
                            has_table = True
                            break
                    
                    if not has_table:
                        link_line = f"- [{rel_path.name}]({rel_path.as_posix()})"
                    
                    new_content.append(link_line)
                    added = True
                    in_section = False

        if not added:
            new_content.append(f"\n## {section_name}")
            new_content.append(f"- [{rel_path.name}]({rel_path.as_posix()})")

        self.index_path.write_text("\n".join(new_content), encoding="utf-8")