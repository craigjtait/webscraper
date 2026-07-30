from datetime import date

import pytest

from webscraper.filter import filter_by_lookback, feature_in_lookback
from webscraper.models import UNDATED_SENTINEL, DatePrecision
from webscraper.parser import parse_period_heading, parse_release_date, parse_release_features

FIXTURE_PATH = "tests/fixtures/whats_new_snippet.html"
CONTROL_HUB_FIXTURE = "tests/fixtures/control_hub_snippet.html"
WEBEX_SUITE_FIXTURE = "tests/fixtures/webex_suite_snippet.html"


@pytest.fixture
def fixture_html() -> str:
    with open(FIXTURE_PATH, encoding="utf-8") as handle:
        return handle.read()


def test_parse_period_heading_formats() -> None:
    assert parse_period_heading("July 24, 2026") == (date(2026, 7, 24), DatePrecision.DAY)
    assert parse_period_heading("28 May, 2026") == (date(2026, 5, 28), DatePrecision.DAY)
    assert parse_period_heading("July 2026") == (date(2026, 7, 1), DatePrecision.MONTH)
    assert parse_period_heading("March, 2026") == (date(2026, 3, 1), DatePrecision.MONTH)
    assert parse_period_heading("July (46.7)", reference_year=2026) == (
        date(2026, 7, 1),
        DatePrecision.MONTH,
    )
    assert parse_period_heading("Admin experience improvements") is None


def test_parse_release_date_compat() -> None:
    assert parse_release_date("July 2026") == date(2026, 7, 1)


def test_parse_release_features_from_fixture(fixture_html: str) -> None:
    features = parse_release_features(
        fixture_html,
        source_url="https://example.com",
        reference_date=date(2026, 7, 30),
    )
    titles = [feature.title for feature in features]

    assert len(features) == 7
    assert "Admin experience improvements" in titles
    assert "Enhancing Call Control" in titles
    assert "Expanded new flow control node support in Flow Designer" in titles
    assert "Management Portal Migration Status" in titles
    assert features[1].release_date == date(2026, 7, 10)
    assert features[2].release_date == date(2026, 7, 10)


def test_parse_control_hub_month_and_h3_features() -> None:
    with open(CONTROL_HUB_FIXTURE, encoding="utf-8") as handle:
        html = handle.read()

    features = parse_release_features(
        html,
        source_url="https://example.com",
        reference_date=date(2026, 7, 30),
    )

    assert len(features) == 4
    july_features = [
        feature
        for feature in features
        if feature.tab_name == "What's new" and feature.release_date == date(2026, 7, 1)
    ]
    assert len(july_features) == 2
    assert july_features[0].title == "Improved localization for Control Hub analytics"
    assert july_features[0].release_date == date(2026, 7, 1)


def test_parse_webex_suite_product_tabs_and_month_version() -> None:
    with open(WEBEX_SUITE_FIXTURE, encoding="utf-8") as handle:
        html = handle.read()

    features = parse_release_features(
        html,
        source_url="https://example.com",
        reference_date=date(2026, 7, 30),
    )

    tabs = {feature.tab_name for feature in features}
    assert tabs == {"Messaging", "Calling"}
    assert all(feature.date_precision == DatePrecision.MONTH for feature in features)
    assert all(feature.release_date == date(2026, 7, 1) for feature in features)
    messaging = [feature for feature in features if feature.tab_name == "Messaging"]
    assert len(messaging) == 2
    assert messaging[0].title == "UI enhancements for messaging area—Android"


def test_parse_release_features_assigns_tab_names(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")

    whats_new = [feature for feature in features if feature.tab_name == "What's new"]
    announcements = [feature for feature in features if feature.tab_name == "Announcements"]

    assert len(whats_new) == 5
    assert len(announcements) == 1
    assert announcements[0].title == "Management Portal Migration Status"


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


def test_month_only_features_included_for_current_month() -> None:
    with open(CONTROL_HUB_FIXTURE, encoding="utf-8") as handle:
        html = handle.read()
    features = parse_release_features(html, source_url="https://example.com")
    july_feature = next(
        feature for feature in features if feature.title.startswith("Improved localization")
    )

    assert feature_in_lookback(july_feature, days=7, as_of=date(2026, 7, 30))
    assert not feature_in_lookback(july_feature, days=7, as_of=date(2026, 8, 15))


def test_filter_by_lookback_seven_days(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")
    filtered = filter_by_lookback(features, days=7, as_of=date(2026, 7, 30))

    assert len(filtered) == 2
    assert {feature.tab_name for feature in filtered} == {"What's new", "Announcements"}


def test_filter_by_lookback_thirty_days(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")
    filtered = filter_by_lookback(features, days=30, as_of=date(2026, 7, 30))

    assert len(filtered) == 4
    assert any(feature.title == "Expanded new flow control node support in Flow Designer" for feature in filtered)


def test_filter_includes_cutoff_date(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")
    filtered = filter_by_lookback(features, days=6, as_of=date(2026, 7, 30))

    assert len(filtered) == 2
    assert {feature.tab_name for feature in filtered} == {"What's new", "Announcements"}


def test_filter_rejects_invalid_days(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")
    with pytest.raises(ValueError):
        filter_by_lookback(features, days=0, as_of=date(2026, 7, 30))


def test_undated_features_use_sentinel(fixture_html: str) -> None:
    features = parse_release_features(fixture_html, source_url="https://example.com")
    limitation = next(feature for feature in features if feature.title == "Supervisor desktop")

    assert limitation.tab_name == "Limitations"
    assert limitation.release_date == UNDATED_SENTINEL
    assert limitation.date_precision == DatePrecision.UNDATED
    assert limitation.is_dated is False
