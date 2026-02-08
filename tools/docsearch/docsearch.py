import re
import sys
import os
import argparse
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple

class Node:
    """Represents a file in the documentation graph."""
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.content: Optional[str] = None
        self.links: List[Path] = []

class DocGraph:
    def __init__(self, root_dir: Path):
        self.root = root_dir.resolve()
        self.nodes: Dict[Path, Node] = {}
        # Regex for Markdown links: [Label](path)
        # Simplified to avoid tool escaping issues: matches [text](url) non-greedily
        self.link_pattern = re.compile(r'\[(.*?)\]\((.*?)\)')

    def resolve_path(self, source_file: Path, link_path: str) -> Optional[Path]:
        """Resolve a relative link from a source file to an absolute path."""
        # Ignore external links
        if link_path.startswith("http") or link_path.startswith("mailto:"):
            return None
        
        # Remove anchors (#section)
        if "#" in link_path:
            link_path = link_path.split("#")[0]
            
        if not link_path:
            return None

        try:
            # Resolve relative to source file's directory
            abs_path = (source_file.parent / link_path).resolve()
            
            # Check if it exists within root (security/validity check)
            # We allow it to exist, or we check if it SHOULD exist. 
            # For this tool, we only care if it exists on disk.
            if abs_path.exists() and abs_path.is_file():
                return abs_path
            
            # Debug: sometimes links are relative to root? (Not standard MD but possible)
            root_rel_path = (self.root / link_path).resolve()
            if root_rel_path.exists() and root_rel_path.is_file():
                return root_rel_path
                
            return None
        except Exception:
            return None

    def get_node(self, path: Path) -> Node:
        """Get or create a node for a path."""
        path = path.resolve()
        if path not in self.nodes:
            self.nodes[path] = Node(path)
        return self.nodes[path]

    def extract_links(self, source_path: Path) -> List[Path]:
        """Parse file content and return list of resolved linked paths."""
        node = self.get_node(source_path)
        
        # If we already parsed links, return them (cache)
        if node.content is not None:
            return node.links

        try:
            content = source_path.read_text(encoding="utf-8")
            node.content = content
        except Exception as e:
            print(f"Warning: Could not read {source_path}: {e}", file=sys.stderr)
            return []

        found_links = []
        for match in self.link_pattern.finditer(content):
            rel_path = match.group(2)
            abs_path = self.resolve_path(source_path, rel_path)
            if abs_path:
                found_links.append(abs_path)
        
        node.links = found_links
        return found_links

    def traverse(self, start_paths: List[Path], depth: int = 1) -> List[Path]:
        """Perform BFS traversal to gather context."""
        queue = [(p.resolve(), 0) for p in start_paths]
        visited = set()
        results = []

        while queue:
            current_path, current_depth = queue.pop(0)
            
            if current_path in visited:
                continue
            
            visited.add(current_path)
            results.append(current_path)

            if current_depth < depth:
                # Extract links (which also caches content)
                neighbors = self.extract_links(current_path)
                for neighbor in neighbors:
                    if neighbor not in visited:
                        queue.append((neighbor, current_depth + 1))
        
        return results

    def pack(self, paths: List[Path]) -> str:
        """Generate the packed XML output."""
        output = []
        for path in paths:
            try:
                # Ensure content is loaded
                if path not in self.nodes or self.nodes[path].content is None:
                    self.extract_links(path)
                
                content = self.nodes[path].content
                try:
                    rel_path = path.relative_to(self.root)
                except ValueError:
                    rel_path = path.name # Fallback if outside root
                
                # Using triple quotes to avoid newline escaping issues
                xml_block = f"""<document path="{rel_path}">
{content}
</document>"""
                output.append(xml_block)
            except Exception as e:
                print(f"Error packing {path}: {e}", file=sys.stderr)
        
        return "\n\n".join(output)

class IndexParser:
    """Parses INDEX.md to find topics, keywords, and their seed files."""
    def __init__(self, index_path: Path):
        self.index_path = index_path.resolve()
        # DocGraph needs project root. Assumed 2 levels up from docs/INDEX.md
        self.root = index_path.parent.parent
        self.graph = DocGraph(self.root)
        self.topic_keywords: Dict[str, List[str]] = {}

    def parse(self) -> Dict[str, List[Path]]:
        """Parse the index file into topics."""
        topics = {}
        current_topic = None
        
        try:
            content = self.index_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading index: {e}", file=sys.stderr)
            return {}

        for line in content.splitlines():
            line = line.strip()
            
            # Match Header level 2 (Topics)
            if line.startswith("## "):
                raw_topic = line[3:].strip()
                clean_topic = self._clean_topic(raw_topic)
                current_topic = clean_topic
                topics[current_topic] = []
                self.topic_keywords[current_topic] = []
                continue
            
            # Match Keywords: *Keywords: Word1, Word2*
            if current_topic and line.lower().startswith("*keywords:"):
                # Strip "*Keywords:" and trailing "*"
                raw_keywords = line[10:].rstrip("*").strip()
                keywords = [k.strip() for k in raw_keywords.split(",")]
                self.topic_keywords[current_topic].extend(keywords)
                continue

            # Match links inside tables or lists
            if current_topic:
                matches = self.graph.link_pattern.findall(line)
                for label, rel_path in matches:
                    abs_path = self.graph.resolve_path(self.index_path, rel_path)
                    if abs_path:
                        topics[current_topic].append(abs_path)
        
        return topics

    def _clean_topic(self, text: str) -> str:
        """Remove emojis and extra whitespace to get a clean key."""
        # Strip generic emojis roughly by skipping non-alphanum start
        for i, char in enumerate(text):
            if char.isalnum():
                return text[i:]
        return text

    def match_topic(self, query: str, topics: Dict[str, List[Path]]) -> List[str]:
        """Find matching topics by name OR keyword."""
        query = query.lower()
        matches = []
        
        for topic in topics:
            # 1. Check Topic Name
            if query in topic.lower():
                matches.append(topic)
                continue
            
            # 2. Check Keywords
            if topic in self.topic_keywords:
                for keyword in self.topic_keywords[topic]:
                    if query in keyword.lower():
                        matches.append(topic)
                        break
        
        return matches

def main():
    desc = """
    Pack documentation context for AI assistants.
    
    This tool reads `docs/INDEX.md` to find relevant documentation based on a Topic
    or Keyword. It then performs a graph traversal (BFS) to include linked dependencies,
    ensuring the AI has full context without hallucinating.
    """
    
    epilog = """
EXAMPLES:
  python tools/context_packer/pack_context.py "memory" "learning"
    -> Packs all files related to Memory OR Learning (Union).
    
  python tools/context_packer/pack_context.py "bayesian" "personality" --and
    -> Packs only files related to BOTH Bayesian AND Personality (Intersection).
    
  python tools/context_packer/pack_context.py "learning" --exclude personality
    -> Packs Learning context but skips any files matching "personality".
    
  python tools/context_packer/pack_context.py "learning" --output prompt.txt
    -> Packs Learning context and saves to prompt.txt instead of printing to console.
    
DEPTH EXPLANATION:
  0: Seed files only (files explicitly listed in INDEX.md).
  1: Immediate dependencies (Seed files + files they link to). [DEFAULT]
  2: Deep context (Seed -> Links -> Links).
    """
    
    parser = argparse.ArgumentParser(
        description=desc, 
        epilog=epilog, 
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("topics", nargs="*", help="Topic keywords (OR logic) or 'all'")
    parser.add_argument("--depth", type=int, default=1, help="Traversal depth (default: 1)")
    parser.add_argument("--list", action="store_true", help="List available topics and keywords")
    parser.add_argument("--memory", action="store_true", help="Include session memory files (claude_memory.md, gemini_memory.md)")
    parser.add_argument("--memory-only", action="store_true", help="Only memory files")
    parser.add_argument("--files-only", action="store_true", help="List paths only")
    parser.add_argument("--output", help="Write to file instead of stdout")
    parser.add_argument("--force", action="store_true", help="Ignore size limits")
    parser.add_argument("--exclude", action="append", help="Exclude topics or paths matching this keyword")
    parser.add_argument("--and", action="store_true", dest="match_all", help="Match ALL topics (Intersection) instead of ANY (Union)")
    parser.add_argument("--audit", action="store_true", help="Audit docs/INDEX.md for orphan docs and dead links")
    parser.add_argument("--fix", action="store_true", help="When used with --audit, interactively fix orphan docs")
    
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent.resolve()
    # UPDATED ROOT CALCULATION: tools/context_packer/pack.py -> project_root (3 levels up)
    project_root = script_dir.parent.parent
    index_path = project_root / "docs" / "INDEX.md"

    if args.audit:
        try:
            from audit import DocAudit
        except ImportError:
            # Handle cases where sys.path might not include current dir
            sys.path.append(str(script_dir))
            from audit import DocAudit
            
        auditor = DocAudit(project_root)
        sys.exit(auditor.run_audit(fix=args.fix))
    
    if not index_path.exists():
        print(f"Error: Could not find {index_path}", file=sys.stderr)
        sys.exit(1)
        
    idx_parser = IndexParser(index_path)
    topics = idx_parser.parse()
    
    if args.list:
        print("Available Topics:")
        for t in topics:
            keywords = idx_parser.topic_keywords.get(t, [])
            kw_str = f" [{', '.join(keywords)}]" if keywords else ""
            print(f" - {t}{kw_str}")
        return

    # Use a set to handle Deduplication
    selected_paths = set()
    
    # Helper to check exclusions
    def is_excluded(text: str) -> bool:
        if not args.exclude:
            return False
        text = text.lower()
        return any(ex.lower() in text for ex in args.exclude)

    # 1. Gather Seeds from Topics
    if args.topics:
        # Check if 'all' is requested
        if any(t.lower() == "all" for t in args.topics):
            for topic, paths in topics.items(): 
                if not is_excluded(topic):
                    selected_paths.update(paths)
        else:
            # Gather sets of paths for each topic query
            topic_results = []
            
            for query in args.topics:
                matches = idx_parser.match_topic(query, topics)
                # Filter matches by exclusion
                matches = [m for m in matches if not is_excluded(m)]
                
                if not matches:
                    print(f"Warning: Topic '{query}' not found (or excluded).", file=sys.stderr)
                    # If AND logic, missing a topic means empty intersection immediately
                    if args.match_all:
                        topic_results.append(set())
                        break
                    continue
                
                current_paths = set()
                for m in matches: 
                    current_paths.update(topics[m])
                topic_results.append(current_paths)
            
            # If topics were provided but nothing matched
            if not topic_results and not args.memory_only:
                print("Error: No matching topics found.", file=sys.stderr)
                sys.exit(1)

            if topic_results:
                if args.match_all:
                    # Intersection: Start with first set, intersect with rest
                    selected_paths = topic_results[0]
                    for other_set in topic_results[1:]:
                        selected_paths.intersection_update(other_set)
                else:
                    # Union: Combine all sets
                    for path_set in topic_results:
                        selected_paths.update(path_set)

    elif not args.memory_only:
        parser.print_help()
        sys.exit(1)

    # 2. Add Memory
    if args.memory or args.memory_only:
        for m in ["claude_memory.md", "gemini_memory.md"]:
            p = project_root / m
            if p.exists(): selected_paths.add(p)

    # 3. Build Graph
    graph = DocGraph(project_root)
    # traverse expects a list
    final_paths = graph.traverse(list(selected_paths), depth=args.depth)
    
    # Filter paths by exclusion
    if args.exclude:
        final_paths = [p for p in final_paths if not is_excluded(str(p))]

    # 4. Filter/Output
    if args.files_only:
        for p in final_paths:
            try:
                print(p.relative_to(project_root))
            except ValueError:
                print(p.name)
        return

    packed_content = graph.pack(final_paths)
    size_kb = len(packed_content) / 1024

    if size_kb > 100 and not args.force and not args.output:
        print(f"Error: Packed content is {size_kb:.1f}KB. Use --output or --force.", file=sys.stderr)
        sys.exit(1)

    if args.output:
        Path(args.output).write_text(packed_content, encoding="utf-8")
        print(f"Packed {len(final_paths)} files ({size_kb:.1f}KB) to {args.output}")
    else:
        print(packed_content)

if __name__ == "__main__":
    main()
