# LLM Provider Interface Spec

**Status**: Proposed
**Date**: 2026-02-02
**Implements**: Extensibility Review item #1 (partial)

## Purpose

Define an abstract interface for LLM text generation so that Phase 2 can swap providers (Ollama, OpenAI, vLLM, local inference) without modifying decision logic.

## Current State

`OllamaClient` in `src/services/executive/gladys_executive/server.py` is a concrete class with:
- Hardcoded HTTP API calls to Ollama
- No interface — directly instantiated by `ExecutiveServicer`
- Mixed concerns: availability checking + generation

## Protocol

```python
from dataclasses import dataclass
from typing import Protocol, Any


@dataclass
class LLMRequest:
    """Request to an LLM provider."""
    prompt: str
    system_prompt: str | None = None
    format: str | None = None  # "json" for structured output
    max_tokens: int | None = None
    temperature: float | None = None


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    text: str
    model: str
    tokens_used: int | None = None
    latency_ms: float | None = None
    raw_response: dict[str, Any] | None = None


class LLMProvider(Protocol):
    """Interface for LLM text generation."""

    async def generate(self, request: LLMRequest) -> LLMResponse | None:
        """Generate a response. Returns None if unavailable."""
        ...

    async def check_available(self) -> bool:
        """Check if the provider is reachable."""
        ...

    @property
    def model_name(self) -> str:
        """Return model identifier for logging."""
        ...
```

## Default Implementation: OllamaProvider

Rename `OllamaClient` to `OllamaProvider` and implement the Protocol:

```python
class OllamaProvider:
    """LLM provider wrapping Ollama's HTTP API."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma:2b"):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._available: bool | None = None

    async def generate(self, request: LLMRequest) -> LLMResponse | None:
        if self._available is False:
            return None

        payload = {
            "model": self._model,
            "prompt": request.prompt,
            "stream": False,
            "keep_alive": "30m",
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt
        if request.format:
            payload["format"] = request.format

        try:
            start = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return LLMResponse(
                            text=data.get("response", ""),
                            model=self._model,
                            latency_ms=(time.time() - start) * 1000,
                            raw_response=data,
                        )
                    return None
        except Exception:
            return None

    async def check_available(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    self._available = resp.status == 200
                    return self._available
        except Exception:
            self._available = False
            return False

    @property
    def model_name(self) -> str:
        return f"ollama/{self._model}"
```

## Configuration

Environment variables (existing, unchanged):
```
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma:2b
```

New env var for provider selection:
```
EXECUTIVE_LLM_PROVIDER=ollama  # "ollama" | "openai" (future)
```

Factory:
```python
def create_llm_provider(provider_type: str, **kwargs) -> LLMProvider | None:
    if provider_type == "ollama":
        return OllamaProvider(
            base_url=kwargs.get("url", os.environ.get("OLLAMA_URL", "http://localhost:11434")),
            model=kwargs.get("model", os.environ.get("OLLAMA_MODEL", "gemma:2b")),
        )
    # Future: elif provider_type == "openai": ...
    return None
```

## File Changes

| File | Change |
|------|--------|
| `server.py` (executive) | Add `LLMProvider` Protocol, `LLMRequest`, `LLMResponse` dataclasses |
| `server.py` (executive) | Rename `OllamaClient` → `OllamaProvider`, implement Protocol |
| `server.py` (executive) | Add `create_llm_provider` factory |
| `server.py` (executive) | Update `serve()` to use factory |

## Testing

- Unit test `OllamaProvider` with mocked HTTP responses
- Test `check_available()` returns False on connection error
- Test `generate()` returns None when unavailable

## Out of Scope

- OpenAI, vLLM, or other providers — add in Phase 2 as needed
- Streaming responses — not needed for current use case

