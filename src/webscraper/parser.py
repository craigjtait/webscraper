from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag
from dateutil import parser as date_parser

from webscraper.models import UNDATED_SENTINEL, ReleaseFeature

WHATS_NEW_TOPIC_ID = "topic_D1C27F9C842A4C6CA27898AFFDB474B7"
WEBEX_HELP_BASE = "https://help.webex.com"
DATE_HEADING_PATTERN = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December|\d{1,2}\s+\w+|\w+\s+\d{1,2})",
    re.IGNORECASE,
)
MONTH_YEAR_PATTERN = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}$",
    re.IGNORECASE,
)


def parse_release_date(text: str) -> date | None:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned or not DATE_HEADING_PATTERN.match(cleaned):
        return None

    month_year = MONTH_YEAR_PATTERN.match(cleaned)
    if month_year:
        try:
            parsed = date_parser.parse(f"{cleaned} 1", fuzzy=False)
        except (ValueError, OverflowError):
            return None
        return parsed.date()

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


def _is_tab_pane(element: Tag) -> bool:
    classes = element.get("class") or []
    return "tab-pane" in classes


def _iter_tab_panes(html: str) -> list[tuple[str, str]]:
    """Return tab label and HTML for each top-level tab pane in nav order."""
    soup = BeautifulSoup(html, "lxml")
    tabs: list[tuple[str, str]] = []
    seen: set[str] = set()

    for link in soup.select(".nav-tabs a[href^='#'], ul.nav a[href^='#']"):
        target_id = link.get("href", "")[1:]
        if not target_id or target_id in seen:
            continue

        pane = soup.find(id=target_id)
        if pane is None or not _is_tab_pane(pane):
            continue

        seen.add(target_id)
        tab_name = link.get_text(" ", strip=True) or target_id
        tabs.append((tab_name, str(pane)))

    return tabs


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


def _parse_features_from_html(
    html: str,
    *,
    source_url: str,
    tab_name: str,
) -> list[ReleaseFeature]:
    soup = BeautifulSoup(html, "lxml")
    features: list[ReleaseFeature] = []
    current_date: date | None = None

    for title, body_container in _iter_h2_sections(soup):
        release_date = parse_release_date(title)
        if release_date:
            current_date = release_date
            continue

        feature_date = current_date if current_date is not None else UNDATED_SENTINEL
        body_text = _element_text(body_container) if body_container else ""
        features.append(
            ReleaseFeature(
                release_date=feature_date,
                title=title,
                body_text=body_text,
                source_url=source_url,
                tab_name=tab_name,
                links=_extract_links(body_container),
            )
        )

    return features


def parse_release_features(html: str, source_url: str) -> list[ReleaseFeature]:
    tabs = _iter_tab_panes(html)
    if not tabs:
        return _parse_features_from_html(
            html,
            source_url=source_url,
            tab_name="Release notes",
        )

    features: list[ReleaseFeature] = []
    for tab_name, tab_html in tabs:
        features.extend(
            _parse_features_from_html(
                tab_html,
                source_url=source_url,
                tab_name=tab_name,
            )
        )
    return features
