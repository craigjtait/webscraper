from datetime import date

from webscraper.models import ReleaseFeature
from webscraper.summarizer import _build_prompt, build_fallback_report


def test_build_prompt_includes_links_section() -> None:
    feature = ReleaseFeature(
        release_date=date(2026, 7, 10),
        title="Enhancing Call Control",
        body_text="See [Agent Desktop guide](https://help.webex.com/example).",
        source_url="https://example.com",
        links=(("Agent Desktop guide", "https://help.webex.com/example"),),
    )

    prompt = _build_prompt([feature], days=30, as_of=date(2026, 7, 30))

    assert "Preserve source URLs as Markdown links" in prompt
    assert "LINKS:" in prompt
    assert "[Agent Desktop guide](https://help.webex.com/example)" in prompt


def test_build_fallback_report_groups_features_by_date() -> None:
    features = [
        ReleaseFeature(
            release_date=date(2026, 7, 10),
            title="Feature A",
            body_text="Details for feature A.",
            source_url="https://example.com",
            links=(("Guide", "https://help.webex.com/guide"),),
        ),
        ReleaseFeature(
            release_date=date(2026, 7, 10),
            title="Feature B",
            body_text="Details for feature B.",
            source_url="https://example.com",
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
    assert "AI summarization was unavailable" in report
    assert "## July 10, 2026" in report
    assert "### Feature A" in report
    assert "### Feature B" in report
    assert "[Guide](https://help.webex.com/guide)" in report
