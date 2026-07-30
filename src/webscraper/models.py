from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReleaseFeature:
    release_date: date
    title: str
    body_text: str
    source_url: str
