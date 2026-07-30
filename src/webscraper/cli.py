from datetime import date
from pathlib import Path
from typing import Optional
import re

import typer
from dotenv import load_dotenv

from webscraper.ai_client import AIServiceError, AITimeoutError
from webscraper.fetcher import fetch_article
from webscraper.filter import filter_by_lookback
from webscraper.parser import parse_release_features
from webscraper.summarizer import (
    build_fallback_report,
    build_markdown_report,
    summarize_features,
    write_report,
)

DEFAULT_URL = (
    "https://help.webex.com/en-us/article/nv7abhz/"
    "What's-new-for-administrators-in-Webex-Contact-Center"
)

app = typer.Typer(add_completion=False, help="Scrape Webex release notes and summarize with AI.")


def _parse_as_of(value: Optional[str]) -> date:
    if not value:
        return date.today()
    return date.fromisoformat(value)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:60] or "webex-release-notes"


def _default_output_path(*, page_title: str, as_of: date, days: int) -> Path:
    slug = _slugify(page_title)
    return Path("output") / f"{slug}-{as_of.isoformat()}-last{days}d.md"


@app.command()
def main(
    url: str = typer.Option(
        DEFAULT_URL,
        "--url",
        help="Webex help article URL to scrape (What's new, Control Hub, Webex Suite, etc.).",
    ),
    days: int = typer.Option(30, "--days", min=1, help="Lookback window in days."),
    as_of: Optional[str] = typer.Option(
        None,
        "--as-of",
        help="Reference date (YYYY-MM-DD). Defaults to today.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        help="Output markdown file path.",
    ),
    cache_dir: Optional[Path] = typer.Option(
        None,
        "--cache-dir",
        help="Optional directory to cache fetched page HTML.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Parse and filter only; skip AI summarization.",
    ),
) -> None:
    load_dotenv()
    reference_date = _parse_as_of(as_of)

    typer.echo(f"Fetching release notes from {url}")
    article = fetch_article(url, cache_dir=cache_dir)
    output_path = output or _default_output_path(
        page_title=article.title,
        as_of=reference_date,
        days=days,
    )

    all_features = parse_release_features(
        article.ui_data,
        article.source_url,
        reference_date=reference_date,
    )
    filtered = filter_by_lookback(all_features, days=days, as_of=reference_date)

    typer.echo(
        f"Parsed {len(all_features)} features from \"{article.title}\"; "
        f"{len(filtered)} within last {days} days "
        f"(as of {reference_date.isoformat()})."
    )

    if dry_run:
        current_tab = ""
        for feature in filtered:
            if feature.tab_name != current_tab:
                current_tab = feature.tab_name
                typer.echo(f"[{current_tab}]")
            typer.echo(f"- {feature.release_date.isoformat()} | {feature.title}")
        raise typer.Exit(code=0)

    if filtered:
        try:
            report = summarize_features(
                filtered,
                page_title=article.title,
                days=days,
                as_of=reference_date,
                source_url=url,
            )
        except AITimeoutError as exc:
            typer.secho(str(exc), fg=typer.colors.YELLOW, err=True)
            typer.echo("Writing fallback report without AI summarization.")
            report = build_fallback_report(
                filtered,
                page_title=article.title,
                days=days,
                as_of=reference_date,
                source_url=url,
                reason="request timed out",
            )
        except AIServiceError as exc:
            typer.secho(f"AI summarization failed: {exc}", fg=typer.colors.YELLOW, err=True)
            typer.echo("Writing fallback report without AI summarization.")
            report = build_fallback_report(
                filtered,
                page_title=article.title,
                days=days,
                as_of=reference_date,
                source_url=url,
                reason=str(exc),
            )
    else:
        report = build_markdown_report(
            f"No releases found in the last {days} days as of "
            f"{reference_date.strftime('%B %d, %Y')}.",
            page_title=article.title,
            features=[],
            days=days,
            as_of=reference_date,
            source_url=url,
        )

    saved_path = write_report(report, output_path)
    typer.echo(f"Wrote report to {saved_path}")


if __name__ == "__main__":
    app()
