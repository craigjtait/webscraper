from datetime import date

from webscraper.models import ReleaseFeature
from webscraper.summarizer import _build_prompt


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
