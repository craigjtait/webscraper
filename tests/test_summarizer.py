from datetime import date

from webscraper.models import ReleaseFeature
from webscraper.summarizer import _build_prompt, build_fallback_report, render_grouped_markdown_body


def test_build_prompt_includes_tab_and_links_section() -> None:
    feature = ReleaseFeature(
        release_date=date(2026, 7, 10),
        title="Enhancing Call Control",
        body_text="See [Agent Desktop guide](https://help.webex.com/example).",
        source_url="https://example.com",
        tab_name="What's new",
        links=(("Agent Desktop guide", "https://help.webex.com/example"),),
    )

    prompt = _build_prompt([feature], days=30, as_of=date(2026, 7, 30))

    assert "TAB: What's new" in prompt
    assert "Preserve the source page tab structure" in prompt
    assert "LINKS:" in prompt
    assert "[Agent Desktop guide](https://help.webex.com/example)" in prompt


def test_render_grouped_markdown_body_uses_tab_date_feature_headings() -> None:
    features = [
        ReleaseFeature(
            release_date=date(2026, 7, 10),
            title="Feature A",
            body_text="Details for feature A.",
            source_url="https://example.com",
            tab_name="What's new",
            links=(("Guide", "https://help.webex.com/guide"),),
        ),
        ReleaseFeature(
            release_date=date(2026, 7, 30),
            title="Announcement A",
            body_text="Announcement details.",
            source_url="https://example.com",
            tab_name="Announcements",
            links=(),
        ),
    ]

    body = render_grouped_markdown_body(features)

    assert "## What's new" in body
    assert "### July 10, 2026" in body
    assert "#### Feature A" in body
    assert "## Announcements" in body
    assert "### July 30, 2026" in body
    assert "#### Announcement A" in body
    assert "[Guide](https://help.webex.com/guide)" in body


def test_render_grouped_markdown_body_omits_date_heading_for_undated_features() -> None:
    from webscraper.models import UNDATED_SENTINEL

    body = render_grouped_markdown_body(
        [
            ReleaseFeature(
                release_date=UNDATED_SENTINEL,
                title="Supervisor desktop",
                body_text="Performance limits apply.",
                source_url="https://example.com",
                tab_name="Limitations",
                links=(),
            )
        ]
    )

    assert "## Limitations" in body
    assert "### Supervisor desktop" in body
    assert "July" not in body


def test_build_fallback_report_groups_by_tab_then_date() -> None:
    features = [
        ReleaseFeature(
            release_date=date(2026, 7, 10),
            title="Feature A",
            body_text="Details for feature A.",
            source_url="https://example.com",
            tab_name="What's new",
            links=(),
        ),
        ReleaseFeature(
            release_date=date(2026, 7, 30),
            title="Announcement A",
            body_text="Announcement details.",
            source_url="https://example.com",
            tab_name="Announcements",
            links=(),
        ),
    ]

    report = build_fallback_report(
        features,
        days=30,
        as_of=date(2026, 7, 30),
        source_url="https://example.com",
        reason="request timed out",
    )

    assert "ai_fallback: true" in report
    assert 'ai_fallback_reason: "request timed out"' in report
    assert "tabs: What's new, Announcements" in report
    assert "## What's new" in report
    assert "## Announcements" in report
    assert "### July 10, 2026" in report
    assert "#### Feature A" in report
