from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

DEFAULT_TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
DEFAULT_APP_KEY_HEADER = "api-key"
DEFAULT_MODEL = "gpt-5-nano"
DEFAULT_API_VERSION = "2025-04-01-preview"
DEFAULT_AUTH_MODE = "oauth"
DEFAULT_TOKEN_AUTH = "basic"
REQUEST_TIMEOUT = 60.0
DEPLOYMENTS_PATH = "/openai/deployments"

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
    scope: str = ""
    auth_mode: str = DEFAULT_AUTH_MODE
    token_auth: str = DEFAULT_TOKEN_AUTH

    @classmethod
    def from_env(cls) -> "AIConfig":
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

        auth_mode = os.environ.get("AI_AUTH_MODE", DEFAULT_AUTH_MODE)
        if auth_mode not in {"oauth", "bearer_app_key", "api_key_only"}:
            raise RuntimeError(
                "AI_AUTH_MODE must be one of: oauth, bearer_app_key, api_key_only"
            )

        token_auth = os.environ.get("AI_TOKEN_AUTH", DEFAULT_TOKEN_AUTH)
        if token_auth not in {"basic", "body"}:
            raise RuntimeError("AI_TOKEN_AUTH must be one of: basic, body")

        return cls(
            client_id=os.environ["AI_CLIENT_ID"],
            client_secret=os.environ["AI_CLIENT_SECRET"],
            app_key=os.environ["AI_APP_KEY"],
            model_name=os.environ.get("AI_MODEL_NAME", DEFAULT_MODEL),
            api_version=os.environ.get("AI_API_VERSION", DEFAULT_API_VERSION),
            endpoint=os.environ["AI_ENDPOINT"].rstrip("/"),
            token_url=os.environ.get("AI_TOKEN_URL", DEFAULT_TOKEN_URL),
            app_key_header=os.environ.get("AI_APP_KEY_HEADER", DEFAULT_APP_KEY_HEADER),
            scope=os.environ.get("AI_SCOPE", "").strip(),
            auth_mode=auth_mode,
            token_auth=token_auth,
        )

    def chat_completions_url(self) -> str:
        return build_chat_completions_url(
            self.endpoint,
            model_name=self.model_name,
            api_version=self.api_version,
        )


def build_chat_completions_url(
    endpoint: str,
    *,
    model_name: str,
    api_version: str,
) -> str:
    """Build an Azure OpenAI-style chat completions URL without duplicating path segments."""
    normalized = endpoint.rstrip("/")

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
    return f"{config.token_url}:{config.client_id}:{config.scope}:{config.token_auth}"


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def _token_request_data(config: AIConfig) -> Dict[str, str]:
    data = {"grant_type": "client_credentials"}
    if config.scope:
        data["scope"] = config.scope
    if config.token_auth == "body":
        data["client_id"] = config.client_id
        data["client_secret"] = config.client_secret
    return data


def _token_request_headers(config: AIConfig) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    if config.token_auth == "basic":
        headers["Authorization"] = _basic_auth_header(config.client_id, config.client_secret)
    return headers


def decode_jwt_claims(token: str) -> Dict[str, object]:
    """Decode JWT payload without verification for troubleshooting."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        return json.loads(decoded)
    except (ValueError, json.JSONDecodeError, IndexError):
        return {}


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
        response = http.post(
            config.token_url,
            data=_token_request_data(config),
            headers=_token_request_headers(config),
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise _http_error("Failed to obtain AI access token", exc) from exc
    finally:
        if owns_client:
            http.close()

    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Token response did not include access_token")

    expires_in = int(payload.get("expires_in", 3600))
    _token_cache[_cache_key(config)] = (token, time.time() + max(expires_in - 60, 0))
    return token


def _request_headers(config: AIConfig, token: Optional[str]) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}

    if config.auth_mode == "oauth":
        if not token:
            raise RuntimeError("OAuth access token is required for AI_AUTH_MODE=oauth")
        headers["Authorization"] = f"Bearer {token}"
        if config.app_key:
            headers[config.app_key_header] = config.app_key
        return headers

    if config.auth_mode == "bearer_app_key":
        headers["Authorization"] = f"Bearer {config.app_key}"
        return headers

    if config.auth_mode == "api_key_only":
        headers[config.app_key_header] = config.app_key
        return headers

    raise RuntimeError(f"Unsupported auth mode: {config.auth_mode}")


def _jwt_debug_suffix(token: Optional[str]) -> str:
    if not token:
        return ""
    claims = decode_jwt_claims(token)
    if not claims:
        return ""
    interesting = {
        key: claims.get(key)
        for key in ("iss", "aud", "scope", "scp", "sub", "client_id", "exp")
        if key in claims
    }
    if not interesting:
        return ""
    return f" Token claims: {interesting}"


def _http_error(message: str, exc: httpx.HTTPError, *, bearer_token: Optional[str] = None) -> RuntimeError:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        detail = response.text.strip()
        suffix = ""
        if response.status_code == 401 and "jwt" in detail.lower():
            suffix = _jwt_debug_suffix(bearer_token)
        if detail:
            return RuntimeError(f"{message}: {exc} Response body: {detail[:500]}{suffix}")
    return RuntimeError(f"{message}: {exc}")


def chat_completion(
    messages: List[Dict[str, str]],
    *,
    config: Optional[AIConfig] = None,
    temperature: float = 0.2,
) -> str:
    ai_config = config or AIConfig.from_env()
    owns_client = True
    http = httpx.Client(timeout=REQUEST_TIMEOUT)
    token: Optional[str] = None
    try:
        if ai_config.auth_mode == "oauth":
            token = get_access_token(ai_config, client=http)
        response = http.post(
            ai_config.chat_completions_url(),
            headers=_request_headers(ai_config, token),
            json={
                "messages": messages,
                "temperature": temperature,
            },
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise _http_error(
            "AI chat completion request failed",
            exc,
            bearer_token=token,
        ) from exc
    finally:
        if owns_client:
            http.close()

    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected AI response format") from exc
