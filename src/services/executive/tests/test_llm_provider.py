import asyncio
import pytest
from unittest.mock import MagicMock, patch
from aiohttp import ClientResponseError, ClientConnectorError

from gladys_executive.server import OllamaProvider, LLMRequest, LLMResponse, create_llm_provider

@pytest.mark.asyncio
async def test_ollama_provider_check_available_success():
    provider = OllamaProvider(base_url="http://localhost:11434")
    
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__aenter__.return_value = mock_resp
        mock_get.return_value = mock_resp
        
        available = await provider.check_available()
        assert available is True
        assert provider._available is True

@pytest.mark.asyncio
async def test_ollama_provider_check_available_failure():
    provider = OllamaProvider(base_url="http://localhost:11434")
    
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.__aenter__.return_value = mock_resp
        mock_get.return_value = mock_resp
        
        available = await provider.check_available()
        assert available is False
        assert provider._available is False

@pytest.mark.asyncio
async def test_ollama_provider_check_available_exception():
    provider = OllamaProvider(base_url="http://localhost:11434")
    
    with patch("aiohttp.ClientSession.get", side_effect=Exception("Connection refused")):
        available = await provider.check_available()
        assert available is False
        assert provider._available is False

@pytest.mark.asyncio
async def test_ollama_provider_generate_success():
    provider = OllamaProvider(base_url="http://localhost:11434", model="gemma:2b")
    provider._available = True
    
    request = LLMRequest(prompt="Hello", system_prompt="You are GLADyS")
    
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json.return_value = asyncio.Future()
        mock_resp.json.return_value.set_result({"response": "Hi there!"})
        mock_resp.__aenter__.return_value = mock_resp
        mock_post.return_value = mock_resp
        
        response = await provider.generate(request)
        
        assert isinstance(response, LLMResponse)
        assert response.text == "Hi there!"
        assert response.model == "gemma:2b"
        assert response.latency_ms > 0

@pytest.mark.asyncio
async def test_ollama_provider_generate_legacy_success():
    provider = OllamaProvider(base_url="http://localhost:11434", model="gemma:2b")
    provider._available = True
    
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json.return_value = asyncio.Future()
        mock_resp.json.return_value.set_result({"response": "Legacy response"})
        mock_resp.__aenter__.return_value = mock_resp
        mock_post.return_value = mock_resp
        
        # Legacy call returns str
        response = await provider.generate("Hello", system="You are GLADyS")
        
        assert response == "Legacy response"

@pytest.mark.asyncio
async def test_ollama_provider_generate_unavailable():
    provider = OllamaProvider(base_url="http://localhost:11434")
    provider._available = False
    
    request = LLMRequest(prompt="Hello")
    response = await provider.generate(request)
    
    assert response is None

@pytest.mark.asyncio
async def test_ollama_provider_generate_error_status():
    provider = OllamaProvider(base_url="http://localhost:11434")
    provider._available = True
    
    request = LLMRequest(prompt="Hello")
    
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.__aenter__.return_value = mock_resp
        mock_post.return_value = mock_resp
        
        response = await provider.generate(request)
        assert response is None

@pytest.mark.asyncio
async def test_ollama_provider_model_name():
    provider = OllamaProvider(model="gemma:2b")
    assert provider.model_name == "ollama/gemma:2b"

def test_create_llm_provider_ollama():
    provider = create_llm_provider("ollama")
    assert isinstance(provider, OllamaProvider)
    assert provider._model == "gemma:2b"  # Default model

def test_create_llm_provider_unknown():
    provider = create_llm_provider("unknown")
    assert provider is None
