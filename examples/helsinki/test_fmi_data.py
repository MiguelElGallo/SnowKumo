"""Check temporal leakage, calendar gaps and parser failure behavior."""

from datetime import date, timedelta

import pytest
from fmi_data import parse_daily, populations
from load_data import canonical


def xml(values):
    body = "".join(
        f"<b:BsWfsElement><b:Time>{day}T00:00:00Z</b:Time>"
        f"<b:ParameterName>tday</b:ParameterName>"
        f"<b:ParameterValue>{value}</b:ParameterValue></b:BsWfsElement>"
        for day, value in values
    )
    return (f'<root xmlns:b="http://xml.fmi.fi/schema/wfs/2.0">{body}</root>').encode()


def test_daily_value_becomes_visible_only_after_observation_day():
    rows = parse_daily(xml([("2024-02-29", "-3.2")]), "100971")
    assert rows[0]["AVAILABLE_AT"] == "2024-03-01 00:00:00"
    assert rows[0]["OBS_DATE"] == "2024-02-29"


def test_missing_measurement_is_preserved_as_null():
    assert parse_daily(xml([("2024-01-01", "NaN")]), "100971")[0]["TEMP_C"] is None


def test_duplicate_observation_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        parse_daily(xml([("2024-01-01", "1"), ("2024-01-01", "2")]), "100971")


def test_empty_response_rejected():
    with pytest.raises(ValueError, match="No daily"):
        parse_daily(xml([]), "100971")


def test_cloud_readback_normalizes_types_but_preserves_content_changes():
    source = {"ENTITY1": "100971", "TIMESTAMP": "2025-01-01 00:00:01", "TARGET1": "-2"}
    cloud = {"ENTITY1": "100971", "TIMESTAMP": "2025-01-01T00:00:01", "TARGET1": -2.0}
    assert canonical(source) == canonical(cloud)
    assert canonical(source) != canonical({**cloud, "TARGET1": -3.0})


def test_holdout_uses_exact_previous_calendar_day_and_requires_full_history():
    day = date(2024, 12, 25)
    values = [(str(day + timedelta(days=i)), str(i)) for i in range(10)]
    rows = parse_daily(xml(values), "100971")
    training, truth, counts = populations(rows)
    assert len(truth) == 3
    assert truth[0] == {
        "ENTITY1": "100971",
        "TIMESTAMP": "2025-01-01 00:00:01",
        "TARGET1": 7.0,
        "PERSISTENCE_C": 6.0,
    }
    assert not training  # Warmup is too short for a 2024 training anchor.
    assert counts["incomplete_history"] > 0
    # Removing Dec 31 must not silently substitute the Dec 30 baseline.
    rows = [r for r in rows if r["OBS_DATE"] != "2024-12-31"]
    assert populations(rows)[1] == []


def test_split_boundaries_are_chronological_and_holdout_never_trains():
    values = []
    for year in (2022, 2023, 2024, 2025):
        start = date(year, 1, 1) - timedelta(days=7)
        values.extend((str(start + timedelta(days=i)), "-2") for i in range(8))
    training, truth, _ = populations(parse_daily(xml(values), "100971"))
    assert {r["TIMESTAMP"]: r["SPLIT"] for r in training} == {
        "2022-01-01 00:00:01": 0,
        "2023-01-01 00:00:01": 1,
        "2024-01-01 00:00:01": 2,
    }
    assert len(truth) == 1 and truth[0]["TIMESTAMP"].startswith("2025")
