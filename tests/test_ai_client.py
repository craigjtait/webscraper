from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from webscraper.ai_client import (
    AIConfig,
    _token_cache,
    build_chat_completions_url,
    chat_completion,
    get_access_token,
)


@pytest.fixture(autouse=True)
def clear_token_cache() -> None:
    _token_cache.clear()


@pytest.fixture
def ai_config() -> AIConfig:
    return AIConfig(
        client_id="client-id",
        client_secret="client-secret",
        app_key="app-key",
        model_name="gpt-5-nano",
        api_version="2025-04-01-preview",
        endpoint="https://chat-ai.cisco.com",
        token_url="https://id.example.com/token",
    )


def test_chat_completions_url_from_base_endpoint(ai_config: AIConfig) -> None:
    assert ai_config.chat_completions_url() == (
        "https://chat-ai.cisco.com/openai/deployments/gpt-5-nano/chat/completions"
        "?api-version=2025-04-01-preview"
    )


def test_chat_completions_url_from_deployments_endpoint() -> None:
    url = build_chat_completions_url(
        "https://chat-ai.cisco.com/openai/deployments",
        model_name="gpt-5-nano",
        api_version="2025-04-01-preview",
    )
    assert url == (
        "https://chat-ai.cisco.com/openai/deployments/gpt-5-nano/chat/completions"
        "?api-version=2025-04-01-preview"
    )


def test_chat_completions_url_does_not_duplicate_deployments_path() -> None:
    url = build_chat_completions_url(
        "https://chat-ai.cisco.com/openai/deployments",
        model_name="gpt-5-nano",
        api_version="2025-04-01-preview",
    )
    assert "/openai/deployments/openai/deployments/" not in url


def test_from_env_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_CLIENT_ID", raising=False)
    with pytest.raises(RuntimeError, match="Missing required AI environment variables"):
        AIConfig.from_env()


def test_get_access_token(ai_config: AIConfig) -> None:
    token_response = httpx.Response(
        200,
        json={"access_token": "test-token", "expires_in": 3600},
        request=httpx.Request("POST", ai_config.token_url),
    )
    mock_http = MagicMock()
    mock_http.post.return_value = token_response

    token = get_access_token(ai_config, client=mock_http)

    assert token == "test-token"
    mock_http.post.assert_called_once()


def test_chat_completion(ai_config: AIConfig) -> None:
    token_response = httpx.Response(
        200,
        json={"access_token": "test-token", "expires_in": 3600},
        request=httpx.Request("POST", ai_config.token_url),
    )
    chat_response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "Summary markdown"}}]},
        request=httpx.Request("POST", ai_config.chat_completions_url()),
    )
    mock_http = MagicMock()
    mock_http.post.side_effect = [token_response, chat_response]

    with patch("webscraper.ai_client.httpx.Client") as client_cls:
        client_cls.return_value = mock_http
        content = chat_completion([{"role": "user", "content": "hello"}], config=ai_config)

    assert content == "Summary markdown"
    assert mock_http.post.call_count == 2
    chat_call = mock_http.post.call_args_list[1]
    assert chat_call.kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert chat_call.kwargs["headers"]["api-key"] == "app-key"
