from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup, NavigableString, Tag
from dateutil import parser as date_parser

from webscraper.models import ReleaseFeature

WHATS_NEW_TOPIC_ID = "topic_D1C27F9C842A4C6CA27898AFFDB474B7"
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


def _element_text(element: Tag) -> str:
    parts: list[str] = []

    def walk(node: Tag | NavigableString) -> None:
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                parts.append(text)
            return

        if node.name == "li":
            item_text = node.get_text(" ", strip=True)
            if item_text:
                parts.append(f"- {item_text}")
            return

        if node.name in {"script", "style"}:
            return

        for child in node.children:
            walk(child)

        if node.name in {"p", "section", "div", "h2", "h3"} and parts and parts[-1]:
            parts.append("")

    walk(element)
    text = "\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _iter_h2_sections(soup: BeautifulSoup) -> list[tuple[str, Tag | None]]:
    sections: list[tuple[str, Tag | None]] = []
    for heading in soup.find_all("h2"):
        title = heading.get_text(" ", strip=True)
        if not title:
            continue

        body_parts: list[str] = []
        for sibling in heading.next_siblings:
            if isinstance(sibling, Tag) and sibling.name == "h2":
                break
            if isinstance(sibling, Tag):
                body_parts.append(_element_text(sibling))
            elif isinstance(sibling, NavigableString):
                text = str(sibling).strip()
                if text:
                    body_parts.append(text)

        body_container = None
        if body_parts:
            wrapper = soup.new_tag("div")
            wrapper.append("\n".join(part for part in body_parts if part))
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
            )
        )

    return features
