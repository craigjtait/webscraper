from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from webscraper.ai_client import AIConfig, chat_completion
from webscraper.filter import date_range_label
from webscraper.models import ReleaseFeature

MAX_BODY_CHARS = 4000


def _tab_order(features: list[ReleaseFeature]) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []
    for feature in features:
        if feature.tab_name not in seen:
            seen.add(feature.tab_name)
            order.append(feature.tab_name)
    return order


def _format_date_heading(release_date: date) -> str:
    return release_date.strftime("%B %d, %Y")


def _group_features_by_tab_and_date(
    features: list[ReleaseFeature],
) -> list[tuple[str, list[tuple[date | None, list[ReleaseFeature]]]]]:
    """Group features by tab, then date (newest first within each tab)."""
    by_tab: dict[str, list[ReleaseFeature]] = defaultdict(list)
    for feature in features:
        by_tab[feature.tab_name].append(feature)

    grouped: list[tuple[str, list[tuple[date | None, list[ReleaseFeature]]]]] = []
    for tab_name in _tab_order(features):
        tab_features = by_tab[tab_name]
        by_date: dict[date, list[ReleaseFeature]] = defaultdict(list)
        undated: list[ReleaseFeature] = []

        for feature in tab_features:
            if feature.is_dated:
                by_date[feature.release_date].append(feature)
            else:
                undated.append(feature)

        date_groups: list[tuple[date | None, list[ReleaseFeature]]] = []
        for release_date in sorted(by_date.keys(), reverse=True):
            date_groups.append((release_date, by_date[release_date]))
        if undated:
            date_groups.append((None, undated))

        grouped.append((tab_name, date_groups))
    return grouped


def _build_prompt(features: list[ReleaseFeature], *, days: int, as_of: date) -> str:
    lines = [
        "Summarize the following Webex Contact Center administrator release notes.",
        f"Only include features released in the last {days} days as of {as_of.isoformat()}.",
        "Requirements:",
        "- Preserve the source page tab structure.",
        "- Use Markdown headings: ## for tab names, ### for dates, #### for feature titles.",
        "- Within each tab, group by release date, newest first.",
        "- Skip tabs that have no features in the lookback window.",
        "- Provide 1-3 concise bullet points per feature.",
        "- Consolidate duplicate themes without losing distinct capabilities.",
        "- Preserve source URLs as Markdown links [label](url) in the summary.",
        "- When LINKS are listed for a feature, embed the relevant ones inline in bullets.",
        "- Do not invent URLs; only use links provided in BODY or LINKS.",
        "- For undated sections, omit the date heading and place features directly under the tab.",
        "- Output valid Markdown only. Do not include YAML front matter or preamble.",
        "",
        "Release notes:",
    ]

    for tab_name, date_groups in _group_features_by_tab_and_date(features):
        lines.append(f"TAB: {tab_name}")
        for release_date, tab_features in date_groups:
            if release_date is not None:
                lines.append(f"DATE: {release_date.isoformat()}")
            for feature in tab_features:
                body = feature.body_text
                if len(body) > MAX_BODY_CHARS:
                    body = body[:MAX_BODY_CHARS] + "\n[truncated]"
                lines.extend(
                    [
                        f"TITLE: {feature.title}",
                        f"BODY:\n{body}",
                    ]
                )
                if feature.links:
                    link_lines = [f"- [{label}]({url})" for label, url in feature.links]
                    lines.append("LINKS:\n" + "\n".join(link_lines))
                lines.append("---")
        lines.append("===")
    return "\n".join(lines)


def _render_feature_block(feature: ReleaseFeature, *, heading_level: str = "###") -> list[str]:
    lines = [f"{heading_level} {feature.title}", ""]
    if feature.body_text.strip():
        lines.append(feature.body_text.strip())
        lines.append("")
    if feature.links:
        lines.append("**Links:**")
        for label, url in feature.links:
            lines.append(f"- [{label}]({url})")
        lines.append("")
    return lines


def render_grouped_markdown_body(
    features: list[ReleaseFeature],
    *,
    preamble_lines: list[str] | None = None,
) -> str:
    """Render tab → date → feature markdown from scraped features."""
    lines = list(preamble_lines or [])
    if lines:
        lines.append("")

    for tab_name, date_groups in _group_features_by_tab_and_date(features):
        lines.extend(["", f"## {tab_name}", ""])
        for release_date, tab_features in date_groups:
            if release_date is not None:
                lines.extend([f"### {_format_date_heading(release_date)}", ""])
                feature_heading = "####"
            else:
                feature_heading = "###"

            for feature in tab_features:
                lines.extend(_render_feature_block(feature, heading_level=feature_heading))

    return "\n".join(lines).strip()


def summarize_features(
    features: list[ReleaseFeature],
    *,
    days: int,
    as_of: date,
    source_url: str,
    ai_config: AIConfig | None = None,
) -> str:
    if not features:
        return _empty_report(days=days, as_of=as_of, source_url=source_url)

    config = ai_config or AIConfig.from_env()
    summary = chat_completion(
        [
            {
                "role": "system",
                "content": (
                    "You are a technical writer summarizing product release notes for "
                    "contact center administrators."
                ),
            },
            {"role": "user", "content": _build_prompt(features, days=days, as_of=as_of)},
        ],
        config=config,
    )
    return build_markdown_report(
        summary.strip(),
        features=features,
        days=days,
        as_of=as_of,
        source_url=source_url,
        model_name=config.model_name,
    )


def build_markdown_report(
    body: str,
    *,
    features: list[ReleaseFeature],
    days: int,
    as_of: date,
    source_url: str,
    model_name: str | None = None,
    fallback_reason: str | None = None,
) -> str:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    tab_names = _tab_order(features)
    front_matter_lines = [
        "---",
        "title: Webex Contact Center Admin Updates",
        f"source: {source_url}",
        f"lookback_days: {days}",
        f"as_of: {as_of.isoformat()}",
        f"date_range: {date_range_label(features, days=days, as_of=as_of)}",
        f"generated_at: {generated_at}",
        f"feature_count: {len(features)}",
    ]
    if tab_names:
        front_matter_lines.append(f"tabs: {', '.join(tab_names)}")
    if model_name:
        front_matter_lines.append(f"ai_model: {model_name}")
    if fallback_reason:
        front_matter_lines.append("ai_fallback: true")
        front_matter_lines.append(f'ai_fallback_reason: "{fallback_reason}"')
    front_matter_lines.extend(["---", ""])
    front_matter = "\n".join(front_matter_lines)
    heading = f"# Webex Contact Center Admin Updates — Last {days} Days (as of {as_of.strftime('%B %d, %Y')})"
    return f"{front_matter}{heading}\n\n{body.strip()}\n"


def build_fallback_report(
    features: list[ReleaseFeature],
    *,
    days: int,
    as_of: date,
    source_url: str,
    reason: str,
) -> str:
    """Produce a structured markdown report when AI summarization is unavailable."""
    body = render_grouped_markdown_body(
        features,
        preamble_lines=[
            f"> **Note:** AI summarization was unavailable ({reason}). "
            "Below is a structured listing of the scraped release notes."
        ],
    )
    return build_markdown_report(
        body,
        features=features,
        days=days,
        as_of=as_of,
        source_url=source_url,
        fallback_reason=reason,
    )


def _empty_report(*, days: int, as_of: date, source_url: str) -> str:
    body = (
        f"No releases found in the last {days} days as of "
        f"{as_of.strftime('%B %d, %Y')}."
    )
    return build_markdown_report(
        body,
        features=[],
        days=days,
        as_of=as_of,
        source_url=source_url,
    )


def write_report(content: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
