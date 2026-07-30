from __future__ import annotations

import calendar
from datetime import date, timedelta

from webscraper.models import DatePrecision, ReleaseFeature


def _month_end(release_date: date) -> date:
    last_day = calendar.monthrange(release_date.year, release_date.month)[1]
    return release_date.replace(day=last_day)


def feature_in_lookback(
    feature: ReleaseFeature,
    *,
    days: int,
    as_of: date,
) -> bool:
    if not feature.is_dated:
        return False

    cutoff = as_of - timedelta(days=days)

    if feature.date_precision == DatePrecision.MONTH:
        month_start = feature.release_date.replace(day=1)
        month_end = _month_end(feature.release_date)
        return month_end >= cutoff and month_start <= as_of

    return cutoff <= feature.release_date <= as_of


def filter_by_lookback(
    features: list[ReleaseFeature],
    *,
    days: int,
    as_of: date,
) -> list[ReleaseFeature]:
    if days < 1:
        raise ValueError("--days must be at least 1")

    return [
        feature
        for feature in features
        if feature_in_lookback(feature, days=days, as_of=as_of)
    ]


def date_range_label(features: list[ReleaseFeature], *, days: int, as_of: date) -> str:
    cutoff = as_of - timedelta(days=days)
    if features:
        earliest = min(feature.release_date for feature in features if feature.is_dated)
        latest = max(feature.release_date for feature in features if feature.is_dated)
        return f"{earliest.isoformat()} to {latest.isoformat()}"
    return f"{cutoff.isoformat()} to {as_of.isoformat()}"
