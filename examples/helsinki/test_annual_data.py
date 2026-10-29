"""Guard full-calendar reporting and the boundary between actuals and forecasts."""

from datetime import date, timedelta

from annual_data import annual_populations
from fmi_data import STATION_IDS


def sample():
    start = date(2025, 12, 25)
    return [
        {
            "STATION_ID": station,
            "OBS_DATE": str(start + timedelta(days=offset)),
            "TEMP_C": float(offset),
        }
        for station in STATION_IDS
        for offset in range(9)
    ]


def test_full_calendar_and_future_actuals_are_null():
    _, score, calendar, _ = annual_populations(sample(), date(2026, 1, 2))
    assert len(calendar) == 1095 and len(score) == 6
    future = [r for r in calendar if r["PHASE"] == "FUTURE_RECURSIVE"]
    assert len(future) == 1089
    assert all(r["TARGET1"] is None and r["PERSISTENCE_C"] is None for r in future)
    assert max(r["LEAD_DAYS"] for r in future) == 363


def test_rolling_target_missing_does_not_change_its_scoring_eligibility():
    # Missing Jan 1 target still allows its score from Dec 25-31 history.
    # Use Dec 31 as seed for the separate forecast, and add the Jan 1 score
    # via a second data fixture whose seed date is Jan 8 and history is complete.
    rows = sample()
    for station in STATION_IDS:
        rows.extend(
            {
                "STATION_ID": station,
                "OBS_DATE": str(date(2026, 1, 3) + timedelta(days=i)),
                "TEMP_C": 2.0,
            }
            for i in range(6)
        )
    for row in rows:
        if row["OBS_DATE"] == "2026-01-01":
            row["TEMP_C"] = None
    _, score, calendar, _ = annual_populations(rows, date(2026, 1, 8))
    assert sum(r["TIMESTAMP"].startswith("2026-01-01") for r in score) == 3
    first = [r for r in calendar if r["TIMESTAMP"].startswith("2026-01-01")]
    assert all(r["ELIGIBLE"] == 1 and r["TARGET1"] is None for r in first)


def test_incomplete_recursive_seed_stops_instead_of_filling_with_predictions():
    import pytest

    with pytest.raises(ValueError, match="Incomplete forecast seed"):
        annual_populations(sample()[:-1], date(2026, 1, 2))
