from dataclasses import dataclass
from datetime import date

UNDATED_SENTINEL = date(1, 1, 1)


@dataclass(frozen=True)
class ReleaseFeature:
    release_date: date
    title: str
    body_text: str
    source_url: str
    tab_name: str = "Release notes"
    links: tuple[tuple[str, str], ...] = ()

    @property
    def is_dated(self) -> bool:
        return self.release_date != UNDATED_SENTINEL
