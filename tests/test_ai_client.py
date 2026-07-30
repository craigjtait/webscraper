from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import httpx
import pytest

from webscraper.ai_client import (
    AIConfig,
    _token_cache,
    build_chat_completions_url,
    chat_completion,
    decode_jwt_claims,
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
        scope="chat-ai-scope",
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


def test_get_access_token_uses_basic_auth(ai_config: AIConfig) -> None:
    token_response = httpx.Response(
        200,
        json={"access_token": "test-token", "expires_in": 3600},
        request=httpx.Request("POST", ai_config.token_url),
    )
    mock_http = MagicMock()
    mock_http.post.return_value = token_response

    token = get_access_token(ai_config, client=mock_http)

    assert token == "test-token"
    call = mock_http.post.call_args
    headers = call.kwargs["headers"]
    expected = base64.b64encode(b"client-id:client-secret").decode("ascii")
    assert headers["Authorization"] == f"Basic {expected}"
    assert call.kwargs["data"]["grant_type"] == "client_credentials"
    assert call.kwargs["data"]["scope"] == "chat-ai-scope"
    assert "client_id" not in call.kwargs["data"]


def test_chat_completion_oauth_mode(ai_config: AIConfig) -> None:
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
    chat_call = mock_http.post.call_args_list[1]
    assert chat_call.kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert chat_call.kwargs["headers"]["api-key"] == "app-key"


def test_bearer_app_key_mode_skips_token_request() -> None:
    config = AIConfig(
        client_id="client-id",
        client_secret="client-secret",
        app_key="jwt-app-key",
        model_name="gpt-5-nano",
        api_version="2025-04-01-preview",
        endpoint="https://chat-ai.cisco.com",
        auth_mode="bearer_app_key",
    )
    chat_response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "ok"}}]},
        request=httpx.Request("POST", config.chat_completions_url()),
    )
    mock_http = MagicMock()
    mock_http.post.return_value = chat_response

    with patch("webscraper.ai_client.httpx.Client") as client_cls:
        client_cls.return_value = mock_http
        content = chat_completion([{"role": "user", "content": "hello"}], config=config)

    assert content == "ok"
    mock_http.post.assert_called_once()
    assert mock_http.post.call_args.kwargs["headers"]["Authorization"] == "Bearer jwt-app-key"


def test_decode_jwt_claims_reads_payload() -> None:
    payload = base64.urlsafe_b64encode(b'{"iss":"id.cisco.com","aud":"chat-ai"}').decode("ascii")
    claims = decode_jwt_claims(f"header.{payload}.signature")
    assert claims["iss"] == "id.cisco.com"
    assert claims["aud"] == "chat-ai"
