from __future__ import annotations

from datetime import date, timedelta

from webscraper.models import ReleaseFeature


def filter_by_lookback(
    features: list[ReleaseFeature],
    *,
    days: int,
    as_of: date,
) -> list[ReleaseFeature]:
    if days < 1:
        raise ValueError("--days must be at least 1")

    cutoff = as_of - timedelta(days=days)
    return [
        feature
        for feature in features
        if cutoff <= feature.release_date <= as_of
    ]


def date_range_label(features: list[ReleaseFeature], *, days: int, as_of: date) -> str:
    cutoff = as_of - timedelta(days=days)
    if features:
        earliest = min(feature.release_date for feature in features)
        latest = max(feature.release_date for feature in features)
        return f"{earliest.isoformat()} to {latest.isoformat()}"
    return f"{cutoff.isoformat()} to {as_of.isoformat()}"
