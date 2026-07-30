from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from webscraper.ai_client import AIConfig, chat_completion
from webscraper.filter import date_range_label
from webscraper.models import ReleaseFeature

MAX_BODY_CHARS = 4000


def _build_prompt(features: list[ReleaseFeature], *, days: int, as_of: date) -> str:
    lines = [
        "Summarize the following Webex Contact Center administrator release notes.",
        f"Only include features released in the last {days} days as of {as_of.isoformat()}.",
        "Requirements:",
        "- Group by release date, newest first.",
        "- Use Markdown headings: ## for dates, ### for feature titles.",
        "- Provide 1-3 concise bullet points per feature.",
        "- Consolidate duplicate themes without losing distinct capabilities.",
        "- Preserve source URLs as Markdown links [label](url) in the summary.",
        "- When LINKS are listed for a feature, embed the relevant ones inline in bullets.",
        "- Do not invent URLs; only use links provided in BODY or LINKS.",
        "- Output valid Markdown only. Do not include YAML front matter or preamble.",
        "",
        "Release notes:",
    ]

    for feature in sorted(features, key=lambda item: item.release_date, reverse=True):
        body = feature.body_text
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS] + "\n[truncated]"
        lines.extend(
            [
                f"DATE: {feature.release_date.isoformat()}",
                f"TITLE: {feature.title}",
                f"BODY:\n{body}",
            ]
        )
        if feature.links:
            link_lines = [f"- [{label}]({url})" for label, url in feature.links]
            lines.append("LINKS:\n" + "\n".join(link_lines))
        lines.append("---")
    return "\n".join(lines)


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
    lines = [
        f"> **Note:** AI summarization was unavailable ({reason}). "
        "Below is a structured listing of the scraped release notes.",
        "",
    ]

    current_date: date | None = None
    for feature in sorted(
        features,
        key=lambda item: (item.release_date, item.title),
        reverse=True,
    ):
        if feature.release_date != current_date:
            current_date = feature.release_date
            lines.extend(["", f"## {current_date.strftime('%B %d, %Y')}", ""])
        lines.extend([f"### {feature.title}", ""])
        if feature.body_text.strip():
            lines.append(feature.body_text.strip())
            lines.append("")
        if feature.links:
            lines.append("**Links:**")
            for label, url in feature.links:
                lines.append(f"- [{label}]({url})")
            lines.append("")

    body = "\n".join(lines).strip()
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
