from dataclasses import dataclass
from datetime import date
from enum import Enum

UNDATED_SENTINEL = date(1, 1, 1)


class DatePrecision(str, Enum):
    DAY = "day"
    MONTH = "month"
    UNDATED = "undated"


@dataclass(frozen=True)
class ReleaseFeature:
    release_date: date
    title: str
    body_text: str
    source_url: str
    tab_name: str = "Release notes"
    date_precision: DatePrecision = DatePrecision.DAY
    links: tuple[tuple[str, str], ...] = ()

    @property
    def is_dated(self) -> bool:
        return self.date_precision != DatePrecision.UNDATED
