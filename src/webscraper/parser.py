from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag
from dateutil import parser as date_parser

from webscraper.models import ReleaseFeature

WHATS_NEW_TOPIC_ID = "topic_D1C27F9C842A4C6CA27898AFFDB474B7"
WEBEX_HELP_BASE = "https://help.webex.com"
DATE_HEADING_PATTERN = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December|\d{1,2}\s+\w+|\w+\s+\d{1,2})",
    re.IGNORECASE,
)


def parse_release_date(text: str) -> date | None:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned or not DATE_HEADING_PATTERN.match(cleaned):
        return None

    for fmt in ("%B %d, %Y", "%d %B, %Y", "%B %d %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    try:
        parsed = date_parser.parse(cleaned, fuzzy=False)
    except (ValueError, OverflowError):
        return None
    return parsed.date()


def _scope_whats_new_html(html: str) -> str:
    start = html.find(f'id="{WHATS_NEW_TOPIC_ID}"')
    if start < 0:
        return html

    end_markers = [
        html.find('id="coming_soon"', start),
        html.find('Coming soon</a>', start),
    ]
    ends = [marker for marker in end_markers if marker >= 0]
    end = min(ends) if ends else len(html)
    return html[start:end]


def normalize_link_url(href: str, *, base_url: str = WEBEX_HELP_BASE) -> str:
    href = href.strip()
    if not href or href.startswith("#"):
        return ""
    if href.startswith(("http://", "https://")):
        return href
    return urljoin(base_url, href)


def _format_anchor(node: Tag) -> str:
    href = normalize_link_url(node.get("href", ""))
    label = node.get_text(" ", strip=True)
    if href and label:
        return f"[{label}]({href})"
    if href:
        return f"<{href}>"
    return label


def _inline_text(node: Tag | NavigableString) -> str:
    if isinstance(node, NavigableString):
        return str(node)

    if node.name == "a":
        return _format_anchor(node)

    if node.name in {"script", "style"}:
        return ""

    return "".join(_inline_text(child) for child in node.children)


def _element_text(element: Tag) -> str:
    parts: list[str] = []

    def walk(node: Tag | NavigableString) -> None:
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                parts.append(text)
            return

        if node.name == "a":
            formatted = _format_anchor(node)
            if formatted:
                parts.append(formatted)
            return

        if node.name == "li":
            item_text = _inline_text(node).strip()
            if item_text:
                parts.append(f"- {item_text}")
            return

        if node.name in {"script", "style"}:
            return

        if node.name in {"p", "div", "section"}:
            paragraph = _inline_text(node).strip()
            if paragraph:
                parts.append(paragraph)
            return

        for child in node.children:
            walk(child)

        if node.name in {"h2", "h3"} and parts and parts[-1]:
            parts.append("")

    walk(element)
    text = "\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_links(element: Tag | None) -> tuple[tuple[str, str], ...]:
    if element is None:
        return ()

    seen: set[tuple[str, str]] = set()
    links: list[tuple[str, str]] = []

    for anchor in element.find_all("a", href=True):
        href = normalize_link_url(anchor.get("href", ""))
        label = anchor.get_text(" ", strip=True) or href
        if not href:
            continue
        key = (label, href)
        if key in seen:
            continue
        seen.add(key)
        links.append(key)

    return tuple(links)


def _iter_h2_sections(soup: BeautifulSoup) -> list[tuple[str, Tag | None]]:
    sections: list[tuple[str, Tag | None]] = []
    for heading in soup.find_all("h2"):
        title = heading.get_text(" ", strip=True)
        if not title:
            continue

        body_parts: list[str] = []
        body_nodes: list[Tag] = []
        for sibling in heading.next_siblings:
            if isinstance(sibling, Tag) and sibling.name == "h2":
                break
            if isinstance(sibling, Tag):
                body_nodes.append(sibling)
            elif isinstance(sibling, NavigableString):
                text = str(sibling).strip()
                if text:
                    body_parts.append(text)

        body_container = None
        if body_nodes:
            wrapper = soup.new_tag("div")
            for node in body_nodes:
                wrapper.append(node)
            body_container = wrapper
        elif body_parts:
            wrapper = soup.new_tag("div")
            wrapper.append("\n".join(body_parts))
            body_container = wrapper
        sections.append((title, body_container))
    return sections


def parse_release_features(html: str, source_url: str) -> list[ReleaseFeature]:
    scoped_html = _scope_whats_new_html(html)
    soup = BeautifulSoup(scoped_html, "lxml")
    features: list[ReleaseFeature] = []
    current_date: date | None = None

    for title, body_container in _iter_h2_sections(soup):
        release_date = parse_release_date(title)
        if release_date:
            current_date = release_date
            continue

        if current_date is None:
            continue

        body_text = _element_text(body_container) if body_container else ""
        features.append(
            ReleaseFeature(
                release_date=current_date,
                title=title,
                body_text=body_text,
                source_url=source_url,
                links=_extract_links(body_container),
            )
        )

    return features
