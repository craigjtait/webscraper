from __future__ import annotations

from datetime import date
from pathlib import Path

import typer
from dotenv import load_dotenv

from webscraper.fetcher import fetch_ui_data
from webscraper.filter import filter_by_lookback
from webscraper.parser import parse_release_features
from webscraper.summarizer import build_markdown_report, summarize_features, write_report

DEFAULT_URL = (
    "https://help.webex.com/en-us/article/nv7abhz/"
    "What's-new-for-administrators-in-Webex-Contact-Center"
)

app = typer.Typer(add_completion=False, help="Scrape Webex release notes and summarize with AI.")


def _parse_as_of(value: str | None) -> date:
    if not value:
        return date.today()
    return date.fromisoformat(value)


def _default_output_path(*, as_of: date, days: int) -> Path:
    return Path("output") / f"webex-cc-admin-updates-{as_of.isoformat()}-last{days}d.md"


@app.command()
def main(
    url: str = typer.Option(DEFAULT_URL, "--url", help="Webex help article URL to scrape."),
    days: int = typer.Option(30, "--days", min=1, help="Lookback window in days."),
    as_of: str | None = typer.Option(
        None,
        "--as-of",
        help="Reference date (YYYY-MM-DD). Defaults to today.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Output markdown file path.",
    ),
    cache_dir: Path | None = typer.Option(
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
    output_path = output or _default_output_path(as_of=reference_date, days=days)

    typer.echo(f"Fetching release notes from {url}")
    ui_data = fetch_ui_data(url, cache_dir=cache_dir)
    all_features = parse_release_features(ui_data, source_url=url)
    filtered = filter_by_lookback(all_features, days=days, as_of=reference_date)

    typer.echo(
        f"Parsed {len(all_features)} features; {len(filtered)} within last {days} days "
        f"(as of {reference_date.isoformat()})."
    )

    if dry_run:
        for feature in filtered:
            typer.echo(f"- {feature.release_date.isoformat()} | {feature.title}")
        raise typer.Exit(code=0)

    if filtered:
        report = summarize_features(
            filtered,
            days=days,
            as_of=reference_date,
            source_url=url,
        )
    else:
        report = build_markdown_report(
            f"No releases found in the last {days} days as of "
            f"{reference_date.strftime('%B %d, %Y')}.",
            features=[],
            days=days,
            as_of=reference_date,
            source_url=url,
        )

    saved_path = write_report(report, output_path)
    typer.echo(f"Wrote report to {saved_path}")


if __name__ == "__main__":
    app()
