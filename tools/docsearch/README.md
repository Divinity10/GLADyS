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
docsearch memory learning

# Search for Intersection (AND)
docsearch bayesian personality --and

# Exclude topics
docsearch learning --exclude personality

# Pack session memory
docsearch --memory-only
```

## How it Works

1.  Reads `docs/INDEX.md` as the semantic map.
2.  Parses keywords and topic headers.
3.  Builds a dependency graph from Markdown links `[Link](path)`.
4.  Traverses the graph (BFS) to gather full context.
5.  Packs content into XML for AI prompts.
