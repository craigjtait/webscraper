from datetime import date

import pytest

from webscraper.filter import filter_by_lookback
from webscraper.parser import parse_release_date, parse_release_features

FIXTURE_PATH = "tests/fixtures/whats_new_snippet.html"


@pytest.fixture
def fixture_html() -> str:
    with open(FIXTURE_PATH, encoding="utf-8") as handle:
        return handle.read()


def test_parse_release_date_formats() -> None:
    assert parse_release_date("July 24, 2026") == date(2026, 7, 24)
    assert parse_release_date("28 May, 2026") == date(2026, 5, 28)
    assert parse_release_date("Admin experience improvements") is None


def test_parse_release_features_from_fixture(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")
    titles = [feature.title for feature in features]

    assert len(features) == 5
    assert "Admin experience improvements" in titles
    assert "Enhancing Call Control" in titles
    assert "Expanded new flow control node support in Flow Designer" in titles
    assert features[1].release_date == date(2026, 7, 10)
    assert features[2].release_date == date(2026, 7, 10)


def test_parse_release_features_extracts_markdown_links(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")
    call_control = next(feature for feature in features if feature.title == "Enhancing Call Control")

    assert "[Manage your calls in Agent Desktop]" in call_control.body_text
    assert "help.webex.com/en-us/article/mmcf7p" in call_control.body_text
    assert call_control.links == (
        (
            "Manage your calls in Agent Desktop",
            "https://help.webex.com/en-us/article/mmcf7p/Manage-your-calls-in-Agent-Desktop",
        ),
    )


def test_filter_by_lookback_seven_days(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")
    filtered = filter_by_lookback(features, days=7, as_of=date(2026, 7, 30))

    assert len(filtered) == 1
    assert filtered[0].release_date == date(2026, 7, 24)
    assert all(feature.release_date >= date(2026, 7, 23) for feature in filtered)


def test_filter_by_lookback_thirty_days(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")
    filtered = filter_by_lookback(features, days=30, as_of=date(2026, 7, 30))

    assert len(filtered) == 3
    assert all(feature.release_date >= date(2026, 6, 30) for feature in filtered)
    assert any(feature.title == "Expanded new flow control node support in Flow Designer" for feature in filtered)


def test_filter_includes_cutoff_date(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")
    filtered = filter_by_lookback(features, days=6, as_of=date(2026, 7, 30))

    assert len(filtered) == 1
    assert filtered[0].release_date == date(2026, 7, 24)


def test_filter_rejects_invalid_days(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")
    with pytest.raises(ValueError):
        filter_by_lookback(features, days=0, as_of=date(2026, 7, 30))
