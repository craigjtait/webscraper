from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

DEFAULT_USER_AGENT = "webscraper/0.1.0 (+https://github.com/craigjtait/webscraper)"
NEXT_DATA_PATTERN = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


class FetchError(RuntimeError):
    """Raised when page content cannot be retrieved or parsed."""


def fetch_page_html(url: str, *, timeout: float = 30.0) -> str:
    """Fetch the article page HTML from help.webex.com."""
    response = httpx.get(
        url,
        headers={"User-Agent": DEFAULT_USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def extract_next_data(html: str) -> dict:
    match = NEXT_DATA_PATTERN.search(html)
    if not match:
        raise FetchError("Could not find __NEXT_DATA__ script tag in page HTML")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise FetchError("Could not parse __NEXT_DATA__ JSON") from exc


def extract_ui_data(html: str) -> str:
    """Extract article HTML embedded in Next.js page props."""
    page_props = extract_next_data(html).get("props", {}).get("pageProps", {})
    ui_data = page_props.get("UIData")
    if isinstance(ui_data, str) and ui_data.strip():
        return ui_data

    content_url = page_props.get("data", {}).get("contentUrl")
    if content_url:
        fallback_html = fetch_page_html(content_url)
        return extract_ui_data_from_content_html(fallback_html)

    raise FetchError("No UIData or contentUrl found in page props")


def extract_ui_data_from_content_html(html: str) -> str:
    """Return article HTML from a CloudFront content mirror page."""
    match = re.search(
        r'(<div[^>]*class="article-content"[^>]*>.*?</div>\s*</main>\s*</div>)',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return html


def load_cached_html(cache_path: Path) -> str:
    if not cache_path.is_file():
        raise FetchError(f"Cache file not found: {cache_path}")
    return cache_path.read_text(encoding="utf-8")


def save_cache(html: str, cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")


def fetch_ui_data(
    url: str,
    *,
    cache_dir: Path | None = None,
    timeout: float = 30.0,
) -> str:
    """Fetch page HTML and return embedded article UIData HTML."""
    cache_path = cache_dir / "page.html" if cache_dir else None
    if cache_path and cache_path.is_file():
        html = load_cached_html(cache_path)
    else:
        html = fetch_page_html(url, timeout=timeout)
        if cache_path:
            save_cache(html, cache_path)

    return extract_ui_data(html)
