from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

DEFAULT_TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
DEFAULT_CHAT_BASE_URL = "https://chat-ai.cisco.com/openai/deployments"
DEFAULT_MODEL = "gpt-5-nano"
DEFAULT_API_VERSION = "2025-04-01-preview"
REQUEST_TIMEOUT = 60.0
DEPLOYMENTS_PATH = "/openai/deployments"

_token_cache: dict[str, tuple[str, float]] = {}


def _env(primary: str, fallback: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(primary)
    if value:
        return value
    value = os.environ.get(fallback)
    if value:
        return value
    return default


@dataclass(frozen=True)
class AIConfig:
    client_id: str
    client_secret: str
    app_key: str
    model_name: str
    api_version: str
    chat_base_url: str
    token_url: str = DEFAULT_TOKEN_URL
    scope: str = ""

    @classmethod
    def from_env(cls) -> "AIConfig":
        client_id = _env("AI_CLIENT_ID", "CIRCUIT_CLIENT_ID")
        client_secret = _env("AI_CLIENT_SECRET", "CIRCUIT_CLIENT_SECRET")
        app_key = _env("AI_APP_KEY", "CIRCUIT_APP_KEY")
        chat_base_url = (
            _env("AI_CHAT_BASE_URL", "CIRCUIT_CHAT_BASE_URL")
            or _env("AI_ENDPOINT", "CIRCUIT_CHAT_BASE_URL")
            or DEFAULT_CHAT_BASE_URL
        )

        missing = [
            name
            for name, value in {
                "AI_CLIENT_ID (or CIRCUIT_CLIENT_ID)": client_id,
                "AI_CLIENT_SECRET (or CIRCUIT_CLIENT_SECRET)": client_secret,
                "AI_APP_KEY (or CIRCUIT_APP_KEY)": app_key,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing required AI environment variables: "
                + ", ".join(missing)
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            app_key=app_key,
            model_name=_env("AI_MODEL_NAME", "CIRCUIT_MODEL_NAME", DEFAULT_MODEL),
            api_version=_env("AI_API_VERSION", "CIRCUIT_API_VERSION", DEFAULT_API_VERSION),
            chat_base_url=chat_base_url.rstrip("/"),
            token_url=_env("AI_TOKEN_URL", "CIRCUIT_TOKEN_URL", DEFAULT_TOKEN_URL),
            scope=(_env("AI_SCOPE", "CIRCUIT_OAUTH_SCOPE") or "").strip(),
        )

    def chat_completions_url(self) -> str:
        return build_chat_completions_url(
            self.chat_base_url,
            model_name=self.model_name,
            api_version=self.api_version,
        )


def build_chat_completions_url(
    chat_base_url: str,
    *,
    model_name: str,
    api_version: str,
) -> str:
    """Build chat completions URL from a deployments base URL."""
    normalized = chat_base_url.rstrip("/")

    if normalized.endswith("/chat/completions"):
        return _ensure_api_version(normalized, api_version)

    if normalized.endswith(DEPLOYMENTS_PATH):
        return (
            f"{normalized}/{model_name}/chat/completions"
            f"?api-version={api_version}"
        )

    deployment_prefix = f"{DEPLOYMENTS_PATH}/{model_name}"
    if deployment_prefix in normalized:
        if normalized.endswith(deployment_prefix):
            return (
                f"{normalized}/chat/completions"
                f"?api-version={api_version}"
            )
        return _ensure_api_version(f"{normalized}/chat/completions", api_version)

    return (
        f"{normalized}{DEPLOYMENTS_PATH}/{model_name}/chat/completions"
        f"?api-version={api_version}"
    )


def _ensure_api_version(url: str, api_version: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["api-version"] = api_version
    return urlunparse(parsed._replace(query=urlencode(query)))


def _cache_key(config: AIConfig) -> str:
    return f"{config.token_url}:{config.client_id}:{config.scope}"


def get_access_token(
    config: AIConfig,
    *,
    client: Optional[httpx.Client] = None,
) -> str:
    cache_entry = _token_cache.get(_cache_key(config))
    if cache_entry and cache_entry[1] > time.time():
        return cache_entry[0]

    owns_client = client is None
    http = client or httpx.Client(timeout=REQUEST_TIMEOUT)
    try:
        token, error, expires_in = _fetch_access_token(config, http)
    finally:
        if owns_client:
            http.close()

    if error:
        raise RuntimeError(error)

    assert token is not None
    ttl = expires_in if expires_in is not None else 3600
    _token_cache[_cache_key(config)] = (token, time.time() + max(ttl - 60, 0))
    return token


def _fetch_access_token(
    config: AIConfig,
    http: httpx.Client,
) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    encoded = base64.b64encode(
        f"{config.client_id}:{config.client_secret}".encode("utf-8")
    ).decode("utf-8")
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded}",
    }
    form: Dict[str, str] = {"grant_type": "client_credentials"}
    if config.scope:
        form["scope"] = config.scope

    try:
        response = http.post(config.token_url, headers=headers, data=form)
    except httpx.HTTPError as exc:
        return None, f"Token request failed: {exc}", None

    if response.status_code != 200:
        return None, f"Token HTTP {response.status_code}: {response.text[:2000]}", None

    try:
        payload = response.json()
    except json.JSONDecodeError:
        return None, f"Token response was not JSON: {response.text[:500]}", None

    token = payload.get("access_token")
    if not token:
        err = payload.get("error") or payload.get("error_description") or payload
        return None, f"No access_token in token response: {err}", None

    expires_in = payload.get("expires_in")
    try:
        expires_int = int(float(expires_in)) if expires_in is not None else None
    except (TypeError, ValueError):
        expires_int = None

    return str(token), None, expires_int


def _chat_headers(access_token: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "api-key": access_token,
    }


def _chat_payload(
    messages: List[Dict[str, str]],
    *,
    app_key: str,
) -> Dict[str, object]:
    return {
        "user": json.dumps({"appkey": app_key}),
        "messages": messages,
    }


def chat_completion(
    messages: List[Dict[str, str]],
    *,
    config: Optional[AIConfig] = None,
) -> str:
    ai_config = config or AIConfig.from_env()
    owns_client = True
    http = httpx.Client(timeout=REQUEST_TIMEOUT)
    try:
        access_token = get_access_token(ai_config, client=http)
        response = http.post(
            ai_config.chat_completions_url(),
            headers=_chat_headers(access_token),
            json=_chat_payload(messages, app_key=ai_config.app_key),
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"AI chat completion request failed: HTTP {response.status_code}: "
                f"{response.text[:4000]}"
            )
        payload = response.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"AI chat completion request failed: {exc}") from exc
    finally:
        if owns_client:
            http.close()

    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected AI response format ({exc}): {json.dumps(payload)[:2000]}"
        ) from exc
