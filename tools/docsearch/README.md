# DocSearch

Graph-based documentation search engine for GLADyS.

## Installation

Using `uv` (Recommended):

```bash
# Run directly
uv run --package docsearch --project tools/docsearch docsearch memory

# Or install tool globally
uv tool install tools/docsearch
docsearch memory
```

## Usage

```bash
# Search for topics (Union)
python tools/docsearch/docsearch.py "memory" "learning"

# Search for Intersection (AND)
python tools/docsearch/docsearch.py "bayesian" "personality" --and

# Audit documentation consistency
python tools/docsearch/docsearch.py --audit

# Interactively fix orphan docs found during audit
python tools/docsearch/docsearch.py --audit --fix

# Exclude topics
python tools/docsearch/docsearch.py "learning" --exclude personality

# Pack session memory
python tools/docsearch/docsearch.py --memory-only
```

## How it Works

1.  Reads `docs/INDEX.md` as the semantic map.
2.  Parses keywords and topic headers.
3.  Builds a dependency graph from Markdown links `[Link](path)`.
4.  Traverses the graph (BFS) to gather full context.
5.  Packs content into XML for AI prompts.
