from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path

from openai import OpenAI

from webscraper.filter import date_range_label
from webscraper.models import ReleaseFeature

DEFAULT_MODEL = "gpt-4o-mini"
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
                "---",
            ]
        )
    return "\n".join(lines)


def summarize_features(
    features: list[ReleaseFeature],
    *,
    days: int,
    as_of: date,
    source_url: str,
    model: str | None = None,
) -> str:
    if not features:
        return _empty_report(days=days, as_of=as_of, source_url=source_url)

    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
    )
    chosen_model = model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    response = client.chat.completions.create(
        model=chosen_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a technical writer summarizing product release notes for "
                    "contact center administrators."
                ),
            },
            {"role": "user", "content": _build_prompt(features, days=days, as_of=as_of)},
        ],
        temperature=0.2,
    )
    summary = response.choices[0].message.content or ""
    return build_markdown_report(
        summary.strip(),
        features=features,
        days=days,
        as_of=as_of,
        source_url=source_url,
    )


def build_markdown_report(
    body: str,
    *,
    features: list[ReleaseFeature],
    days: int,
    as_of: date,
    source_url: str,
) -> str:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    front_matter = "\n".join(
        [
            "---",
            "title: Webex Contact Center Admin Updates",
            f"source: {source_url}",
            f"lookback_days: {days}",
            f"as_of: {as_of.isoformat()}",
            f"date_range: {date_range_label(features, days=days, as_of=as_of)}",
            f"generated_at: {generated_at}",
            f"feature_count: {len(features)}",
            "---",
            "",
        ]
    )
    heading = f"# Webex Contact Center Admin Updates — Last {days} Days (as of {as_of.strftime('%B %d, %Y')})"
    return f"{front_matter}{heading}\n\n{body.strip()}\n"


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
