from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag
from dateutil import parser as date_parser

from webscraper.models import UNDATED_SENTINEL, DatePrecision, ReleaseFeature

WEBEX_HELP_BASE = "https://help.webex.com"
HEADING_TAGS = ("h2", "h3", "h4")
MONTH_NAMES = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
DATE_HEADING_PATTERN = re.compile(
    rf"^({MONTH_NAMES}|\d{{1,2}}\s+\w+|\w+\s+\d{{1,2}})",
    re.IGNORECASE,
)
MONTH_YEAR_PATTERN = re.compile(
    rf"^({MONTH_NAMES})\s+(\d{{4}})$",
    re.IGNORECASE,
)
MONTH_COMMA_YEAR_PATTERN = re.compile(
    rf"^({MONTH_NAMES})\s*,\s*(\d{{4}})$",
    re.IGNORECASE,
)
MONTH_VERSION_PATTERN = re.compile(
    rf"^({MONTH_NAMES})\s*\(\s*[\d.]+\s*\)$",
    re.IGNORECASE,
)


def parse_period_heading(
    text: str,
    *,
    reference_year: int | None = None,
) -> tuple[date, DatePrecision] | None:
    """Parse a section heading into a release period, if recognized."""
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned or not DATE_HEADING_PATTERN.match(cleaned):
        return None

    year = reference_year or date.today().year

    month_version = MONTH_VERSION_PATTERN.match(cleaned)
    if month_version:
        month_name = month_version.group(1)
        parsed = date_parser.parse(f"{month_name} 1, {year}", fuzzy=False)
        return parsed.date().replace(day=1), DatePrecision.MONTH

    month_comma_year = MONTH_COMMA_YEAR_PATTERN.match(cleaned)
    if month_comma_year:
        month_name, parsed_year = month_comma_year.groups()
        parsed = date_parser.parse(f"{month_name} 1, {parsed_year}", fuzzy=False)
        return parsed.date().replace(day=1), DatePrecision.MONTH

    month_year = MONTH_YEAR_PATTERN.match(cleaned)
    if month_year:
        month_name, parsed_year = month_year.groups()
        parsed = date_parser.parse(f"{month_name} 1, {parsed_year}", fuzzy=False)
        return parsed.date().replace(day=1), DatePrecision.MONTH

    for fmt in ("%B %d, %Y", "%d %B, %Y", "%B %d %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date(), DatePrecision.DAY
        except ValueError:
            continue

    try:
        parsed = date_parser.parse(cleaned, fuzzy=False)
    except (ValueError, OverflowError):
        return None

    if parsed.day == 1 and not re.search(r"\d{1,2}", cleaned.split(",")[0]):
        return parsed.date().replace(day=1), DatePrecision.MONTH
    return parsed.date(), DatePrecision.DAY


def parse_release_date(text: str, *, reference_year: int | None = None) -> date | None:
    """Backward-compatible helper returning only the parsed date."""
    period = parse_period_heading(text, reference_year=reference_year)
    return period[0] if period else None


def _heading_level(tag: Tag) -> int:
    return int(tag.name[1])


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

        if node.name in HEADING_TAGS:
            nested = node.get_text(" ", strip=True)
            if nested:
                parts.append(nested)
            return

        if node.name in {"p", "div", "section"}:
            paragraph = _inline_text(node).strip()
            if paragraph:
                parts.append(paragraph)
            return

        for child in node.children:
            walk(child)

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


def _body_until_next_section(heading: Tag, *, soup: BeautifulSoup) -> Tag | None:
    level = _heading_level(heading)
    body_nodes: list[Tag] = []
    body_parts: list[str] = []

    for sibling in heading.next_siblings:
        if isinstance(sibling, Tag):
            if sibling.name in HEADING_TAGS and _heading_level(sibling) <= level:
                break
            body_nodes.append(sibling)
        elif isinstance(sibling, NavigableString):
            text = str(sibling).strip()
            if text:
                body_parts.append(text)

    if body_nodes:
        wrapper = soup.new_tag("div")
        for node in body_nodes:
            wrapper.append(node)
        return wrapper

    if body_parts:
        wrapper = soup.new_tag("div")
        wrapper.append("\n".join(body_parts))
        return wrapper

    return None


def _parse_features_from_html(
    html: str,
    *,
    source_url: str,
    tab_name: str,
    reference_year: int,
) -> list[ReleaseFeature]:
    soup = BeautifulSoup(html, "lxml")
    features: list[ReleaseFeature] = []
    current_period: date | None = None
    current_precision = DatePrecision.UNDATED

    for heading in soup.find_all(HEADING_TAGS):
        title = heading.get_text(" ", strip=True)
        if not title:
            continue

        period = parse_period_heading(title, reference_year=reference_year)
        if period is not None:
            current_period, current_precision = period
            continue

        if current_period is None:
            feature_date = UNDATED_SENTINEL
            precision = DatePrecision.UNDATED
        else:
            feature_date = current_period
            precision = current_precision

        body_container = _body_until_next_section(heading, soup=soup)
        body_text = _element_text(body_container) if body_container else ""
        features.append(
            ReleaseFeature(
                release_date=feature_date,
                title=title,
                body_text=body_text,
                source_url=source_url,
                tab_name=tab_name,
                date_precision=precision,
                links=_extract_links(body_container),
            )
        )

    return features


def parse_release_features(
    html: str,
    source_url: str,
    *,
    reference_date: date | None = None,
) -> list[ReleaseFeature]:
    reference = reference_date or date.today()
    tabs = _iter_tab_panes(html)
    if not tabs:
        return _parse_features_from_html(
            html,
            source_url=source_url,
            tab_name="Release notes",
            reference_year=reference.year,
        )

    features: list[ReleaseFeature] = []
    for tab_name, tab_html in tabs:
        features.extend(
            _parse_features_from_html(
                tab_html,
                source_url=source_url,
                tab_name=tab_name,
                reference_year=reference.year,
            )
        )
    return features
