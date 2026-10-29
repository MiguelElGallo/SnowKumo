"""Prepare full-year 2025 history, rolling 2026 evaluation and future calendar."""

import json
import math
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta

from fmi_data import NS, ROOT, STATION_IDS, fetch, parse_daily, write_csv

AS_OF = date(2026, 10, 28)
DAY = timedelta(days=1)


def annual_populations(rows: list[dict], as_of: date = AS_OF):
    lookup = {(r["STATION_ID"], date.fromisoformat(r["OBS_DATE"])): r["TEMP_C"] for r in rows}
    if len(lookup) != len(rows):
        raise ValueError("Duplicate station/day")
    training, scoring, calendar = [], [], []
    missing_training = 0
    for station in STATION_IDS:
        day = date(2018, 1, 1)
        while day <= date(2026, 12, 31):
            history = [lookup.get((station, day - DAY * i)) for i in range(1, 8)]
            eligible = all(v is not None and math.isfinite(v) for v in history)
            target = lookup.get((station, day)) if day <= as_of else None
            anchor = f"{day} 00:00:01"
            if day.year < 2026:
                if target is not None and eligible:
                    training.append(
                        {
                            "ENTITY1": station,
                            "TIMESTAMP": anchor,
                            "TARGET1": target,
                            "SPLIT": 0 if day.year <= 2023 else day.year - 2023,
                        }
                    )
                else:
                    missing_training += 1
            else:
                past = day <= as_of
                if past and eligible:
                    scoring.append({"ENTITY1": station, "TIMESTAMP": anchor})
                previous_year = lookup.get((station, date(2025, day.month, day.day)))
                calendar.append(
                    {
                        "ENTITY1": station,
                        "TIMESTAMP": anchor,
                        "TARGET1": target,
                        "PERSISTENCE_C": history[0] if past else None,
                        "SEASONAL_2025_C": previous_year,
                        "PHASE": "ROLLING_ACTUAL_HISTORY" if past else "FUTURE_RECURSIVE",
                        "ELIGIBLE": int(eligible) if past else None,
                        "LEAD_DAYS": 1 if past else (day - as_of).days,
                    }
                )
            day += DAY
    # The common seed date must have a full, finite seven-day history for each station.
    for station in STATION_IDS:
        for lag in range(7):
            value = lookup.get((station, as_of - DAY * lag))
            if value is None or not math.isfinite(value):
                raise ValueError(f"Incomplete forecast seed: {station} {as_of - DAY * lag}")
    assert len(calendar) == len(STATION_IDS) * 365
    return training, scoring, calendar, missing_training


def main():
    data = ROOT / "data" / "2026"
    raw = ROOT / "data" / "raw"
    data.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    observations, stations, requests = [], [], []
    for station in STATION_IDS:
        path = raw / f"station_{station}.xml"
        requests.append(fetch("fmi::ef::stations", path, fmisid=station))
        root = ET.fromstring(path.read_bytes())
        name = root.find(".//g:name", NS)
        pos = root.find(".//g:pos", NS)
        identifier = root.find(".//g:identifier", NS)
        if name is None or pos is None or not pos.text or identifier is None:
            raise ValueError("Incomplete station metadata")
        if identifier.text != station:
            raise ValueError("Unexpected station metadata")
        lat, lon = map(float, pos.text.split())
        stations.append(
            {"STATION_ID": station, "NAME": name.text, "LATITUDE": lat, "LONGITUDE": lon}
        )
        for year in range(2017, 2027):
            end = AS_OF if year == 2026 else date(year, 12, 31)
            # Original pilot cache is full-year only through 2024.
            path = raw / (
                f"daily_{station}_{year}.xml"
                if year <= 2024
                else f"daily_{station}_{year}_{end}.xml"
            )
            requests.append(
                fetch(
                    "fmi::observations::weather::daily::simple",
                    path,
                    fmisid=station,
                    parameters="tday",
                    starttime=f"{year}-01-01T00:00:00Z",
                    endtime=f"{end}T00:00:00Z",
                )
            )
            chunk = parse_daily(path.read_bytes(), station)
            if any(not date(year, 1, 1) <= date.fromisoformat(r["OBS_DATE"]) <= end for r in chunk):
                raise ValueError("Observation outside requested interval")
            observations.extend(chunk)
    train, scoring, calendar, excluded = annual_populations(observations)
    for filename, rows in {
        "stations": stations,
        "observations": observations,
        "training_labels": train,
        "score_population": scoring,
        "calendar_2026": calendar,
    }.items():
        write_csv(data / f"{filename}.csv", rows)
    measured = [r for r in calendar if r["TARGET1"] is not None and r["ELIGIBLE"] == 1]
    baseline_metrics = {}
    for label, column in [
        ("persistence", "PERSISTENCE_C"),
        ("seasonal_naive_2025", "SEASONAL_2025_C"),
    ]:
        pairs = [r for r in measured if r[column] is not None]
        errors = [r[column] - r["TARGET1"] for r in pairs]
        baseline_metrics[label] = {
            "n": len(pairs),
            "mae_c": sum(map(abs, errors)) / len(errors),
            "rmse_c": math.sqrt(sum(x * x for x in errors) / len(errors)),
        }
    report = {
        "as_of": str(AS_OF),
        "acquired_at": datetime.now(UTC).isoformat(),
        "source": "Finnish Meteorological Institute, CC BY 4.0",
        "observations": len(observations),
        "training_rows": len(train),
        "training_exclusions": excluded,
        "splits": {str(s): sum(r["SPLIT"] == s for r in train) for s in range(3)},
        "rolling_score_rows": len(scoring),
        "calendar_rows": len(calendar),
        "actual_rows": sum(r["TARGET1"] is not None for r in calendar),
        "future_rows": sum(r["PHASE"] == "FUTURE_RECURSIVE" for r in calendar),
        "baselines": baseline_metrics,
        "requests": requests,
    }
    (data / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "requests"}, indent=2))


if __name__ == "__main__":
    main()
