from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

DEFAULT_TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
DEFAULT_APP_KEY_HEADER = "Ocp-Apim-Subscription-Key"
DEFAULT_MODEL = "gpt-5-nano"
DEFAULT_API_VERSION = "2025-04-01-preview"
REQUEST_TIMEOUT = 60.0

_token_cache: dict[str, tuple[str, float]] = {}


@dataclass(frozen=True)
class AIConfig:
    client_id: str
    client_secret: str
    app_key: str
    model_name: str
    api_version: str
    endpoint: str
    token_url: str = DEFAULT_TOKEN_URL
    app_key_header: str = DEFAULT_APP_KEY_HEADER

    @classmethod
    def from_env(cls) -> AIConfig:
        missing = [
            name
            for name, value in {
                "AI_CLIENT_ID": os.environ.get("AI_CLIENT_ID"),
                "AI_CLIENT_SECRET": os.environ.get("AI_CLIENT_SECRET"),
                "AI_APP_KEY": os.environ.get("AI_APP_KEY"),
                "AI_ENDPOINT": os.environ.get("AI_ENDPOINT"),
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing required AI environment variables: "
                + ", ".join(missing)
            )

        return cls(
            client_id=os.environ["AI_CLIENT_ID"],
            client_secret=os.environ["AI_CLIENT_SECRET"],
            app_key=os.environ["AI_APP_KEY"],
            model_name=os.environ.get("AI_MODEL_NAME", DEFAULT_MODEL),
            api_version=os.environ.get("AI_API_VERSION", DEFAULT_API_VERSION),
            endpoint=os.environ["AI_ENDPOINT"].rstrip("/"),
            token_url=os.environ.get("AI_TOKEN_URL", DEFAULT_TOKEN_URL),
            app_key_header=os.environ.get("AI_APP_KEY_HEADER", DEFAULT_APP_KEY_HEADER),
        )

    def chat_completions_url(self) -> str:
        return (
            f"{self.endpoint}/openai/deployments/{self.model_name}/chat/completions"
            f"?api-version={self.api_version}"
        )


def _cache_key(config: AIConfig) -> str:
    return f"{config.token_url}:{config.client_id}"


def get_access_token(config: AIConfig, *, client: httpx.Client | None = None) -> str:
    cache_entry = _token_cache.get(_cache_key(config))
    if cache_entry and cache_entry[1] > time.time():
        return cache_entry[0]

    owns_client = client is None
    http = client or httpx.Client(timeout=REQUEST_TIMEOUT)
    try:
        response = http.post(
            config.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": config.client_id,
                "client_secret": config.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Failed to obtain AI access token: {exc}") from exc
    finally:
        if owns_client:
            http.close()

    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Token response did not include access_token")

    expires_in = int(payload.get("expires_in", 3600))
    _token_cache[_cache_key(config)] = (token, time.time() + max(expires_in - 60, 0))
    return token


def chat_completion(
    messages: list[dict[str, str]],
    *,
    config: AIConfig | None = None,
    temperature: float = 0.2,
) -> str:
    ai_config = config or AIConfig.from_env()
    owns_client = True
    http = httpx.Client(timeout=REQUEST_TIMEOUT)
    try:
        token = get_access_token(ai_config, client=http)
        response = http.post(
            ai_config.chat_completions_url(),
            headers={
                "Authorization": f"Bearer {token}",
                ai_config.app_key_header: ai_config.app_key,
                "Content-Type": "application/json",
            },
            json={
                "messages": messages,
                "temperature": temperature,
            },
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"AI chat completion request failed: {exc}") from exc
    finally:
        if owns_client:
            http.close()

    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected AI response format") from exc
