from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from webscraper.ai_client import AITimeoutError
from webscraper.cli import app
from webscraper.models import ReleaseFeature

runner = CliRunner()


def test_cli_writes_fallback_report_on_ai_timeout(tmp_path: Path) -> None:
    feature = ReleaseFeature(
        release_date=date(2026, 7, 10),
        title="Sample Feature",
        body_text="Sample body.",
        source_url="https://example.com",
        tab_name="What's new",
        links=(),
    )
    output_path = tmp_path / "report.md"

    with patch("webscraper.cli.fetch_article") as fetch_mock, patch(
        "webscraper.cli.parse_release_features",
        return_value=[feature],
    ), patch(
        "webscraper.cli.filter_by_lookback",
        return_value=[feature],
    ), patch(
        "webscraper.cli.summarize_features",
        side_effect=AITimeoutError("The AI service did not respond in time."),
    ):
        from webscraper.fetcher import ArticlePage

        fetch_mock.return_value = ArticlePage(
            title="What's new for administrators",
            ui_data="<html></html>",
            source_url="https://example.com",
        )
        result = runner.invoke(
            app,
            ["--output", str(output_path), "--days", "30"],
        )

    assert result.exit_code == 0
    assert "did not respond in time" in result.output
    assert "Writing fallback report" in result.output
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "ai_fallback: true" in content
    assert "### Sample Feature" in content
