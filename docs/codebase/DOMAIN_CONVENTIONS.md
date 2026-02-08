# Domain Conventions


## Heuristic Matching
- **Semantic matching**: Python uses cosine similarity between event embedding and condition_embedding
- **NOT keyword matching**: Don't assume simple word overlap
- **source_filter**: Optional filter that matches heuristic condition_text PREFIX (e.g., `source="minecraft"` matches conditions starting with `"minecraft:"`)

## Heuristic Fields
| Field | Purpose |
|-------|---------|
| `condition_text` | Natural language description of when to trigger |
| `condition_embedding` | 384-dim vector generated from condition_text |
| `effects_json` | JSON with salience modifiers and actions |
| `confidence` | 0.0-1.0, updated via TD learning |
| `origin` | `'learned'`, `'user'`, `'pack'`, `'built_in'` |

## Heuristic Field Gaps (Proto vs DB)

| Field | DB Column | Proto Field | Notes |
|-------|-----------|-------------|-------|
| Active status | `frozen` (BOOLEAN) | **NOT IN PROTO** | DB uses `frozen=false` for active. Code uses `getattr(h, "active") else True` |
| Origin ID | `origin_id` | `origin_id` | In proto but `_heuristic_to_dict` may not include it |

**Impact**: Dashboard filtering by "active" status requires workaround since proto doesn't have the field.

## SalienceVector Fields
All float 0.0-1.0:
- `threat`, `opportunity`, `humor`, `novelty`, `goal_relevance`, `social`, `emotional`, `actionability`, `habituation`
