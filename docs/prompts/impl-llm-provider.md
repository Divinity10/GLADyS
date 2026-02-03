# Implementation: LLM Provider Protocol

**Read `CLAUDE.md` first, then `docs/design/LLM_PROVIDER.md` (the spec), then this prompt.**

## Task

Extract an `LLMProvider` Protocol from the existing `OllamaClient` in the Executive service. This creates an abstraction layer so PoC 2 can swap LLM providers without modifying decision logic.

## Branch

```bash
git checkout main && git pull
git checkout -b refactor/llm-provider
```

## What to Implement

Follow `docs/design/LLM_PROVIDER.md` exactly. Summary:

1. **Add Protocol and dataclasses** to `src/services/executive/gladys_executive/server.py`:
   - `LLMRequest` dataclass
   - `LLMResponse` dataclass
   - `LLMProvider` Protocol

2. **Rename `OllamaClient` → `OllamaProvider`** and implement the Protocol:
   - `generate(request: LLMRequest) -> LLMResponse | None`
   - `check_available() -> bool`
   - `model_name` property

3. **Add factory function**:
   ```python
   def create_llm_provider(provider_type: str, **kwargs) -> LLMProvider | None
   ```

4. **Update `serve()`** to use the factory instead of direct instantiation.

## Constraints

- Do NOT change the behavior of `ProcessEvent` or `ProvideFeedback` yet — they continue to call `self.ollama.generate()` with the old signature. The next PR (DecisionStrategy) will update them.
- Keep backward compatibility: existing code that does `await ollama.generate(prompt, system=..., format=...)` must still work. The `OllamaProvider` can have both the Protocol method and the legacy method during transition.
- Add type hints throughout.

## Testing

- Add unit tests for `OllamaProvider`:
  - Mock HTTP responses for `generate()`
  - Test `check_available()` returns False on connection error
  - Test `generate()` returns None when unavailable
- Tests go in `src/services/executive/tests/test_llm_provider.py`

## Files to Change

| File | Change |
|------|--------|
| `src/services/executive/gladys_executive/server.py` | Add Protocol, dataclasses, rename class, add factory |
| `src/services/executive/tests/test_llm_provider.py` | New file — unit tests |

## Definition of Done

- [ ] `LLMProvider` Protocol exists with correct signature
- [ ] `OllamaProvider` implements the Protocol
- [ ] Factory function works
- [ ] Unit tests pass
- [ ] Existing Executive behavior unchanged (ProcessEvent still works)
- [ ] `make test` passes for executive service

## Working Memory

Use `claude_memory.md` (gitignored) as your working scratchpad.
