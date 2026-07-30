from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import httpx
import pytest

from webscraper.ai_client import (
    AITimeoutError,
    AIConfig,
    _token_cache,
    build_chat_completions_url,
    chat_completion,
    get_access_token,
    request_timeout_seconds,
)


@pytest.fixture(autouse=True)
def clear_token_cache() -> None:
    _token_cache.clear()


@pytest.fixture
def ai_config() -> AIConfig:
    return AIConfig(
        client_id="client-id",
        client_secret="client-secret",
        app_key="circuit-app-key",
        model_name="gpt-5-nano",
        api_version="2025-04-01-preview",
        chat_base_url="https://chat-ai.cisco.com/openai/deployments",
        token_url="https://id.example.com/token",
        scope="chat-ai-scope",
    )


def test_chat_completions_url(ai_config: AIConfig) -> None:
    assert ai_config.chat_completions_url() == (
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


def test_get_access_token_uses_basic_auth(ai_config: AIConfig) -> None:
    token_response = httpx.Response(
        200,
        json={"access_token": "oauth-token", "expires_in": 3600},
        request=httpx.Request("POST", ai_config.token_url),
    )
    mock_http = MagicMock()
    mock_http.post.return_value = token_response

    token = get_access_token(ai_config, client=mock_http)

    assert token == "oauth-token"
    call = mock_http.post.call_args
    headers = call.kwargs["headers"]
    expected = base64.b64encode(b"client-id:client-secret").decode("ascii")
    assert headers["Authorization"] == f"Basic {expected}"
    assert call.kwargs["data"]["grant_type"] == "client_credentials"
    assert call.kwargs["data"]["scope"] == "chat-ai-scope"


def test_chat_completion_uses_api_key_header_and_user_appkey(ai_config: AIConfig) -> None:
    token_response = httpx.Response(
        200,
        json={"access_token": "oauth-token", "expires_in": 3600},
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
    chat_call = mock_http.post.call_args_list[1]
    assert chat_call.kwargs["headers"]["api-key"] == "oauth-token"
    assert "Authorization" not in chat_call.kwargs["headers"]
    assert chat_call.kwargs["json"]["user"] == '{"appkey": "circuit-app-key"}'
    assert chat_call.kwargs["json"]["messages"] == [{"role": "user", "content": "hello"}]


def test_from_env_accepts_circuit_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRCUIT_CLIENT_ID", "cid")
    monkeypatch.setenv("CIRCUIT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("CIRCUIT_APP_KEY", "appkey")
    monkeypatch.delenv("AI_CLIENT_ID", raising=False)
    monkeypatch.delenv("AI_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("AI_APP_KEY", raising=False)

    config = AIConfig.from_env()
    assert config.client_id == "cid"
    assert config.app_key == "appkey"


def test_request_timeout_seconds_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("CIRCUIT_TIMEOUT_SECONDS", raising=False)
    assert request_timeout_seconds() == 120.0


def test_request_timeout_seconds_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "90")
    assert request_timeout_seconds() == 90.0


def test_chat_completion_timeout_raises_aitimeout_error(ai_config: AIConfig) -> None:
    token_response = httpx.Response(
        200,
        json={"access_token": "oauth-token", "expires_in": 3600},
        request=httpx.Request("POST", ai_config.token_url),
    )
    mock_http = MagicMock()
    mock_http.post.side_effect = [token_response, httpx.ReadTimeout("The read operation timed out")]

    with patch("webscraper.ai_client.httpx.Client") as client_cls:
        client_cls.return_value = mock_http
        with pytest.raises(AITimeoutError, match="did not respond in time"):
            chat_completion([{"role": "user", "content": "hello"}], config=ai_config)
