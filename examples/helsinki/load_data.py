"""Load the fixed FMI sample through an explicitly selected Snowflake CLI connection."""

import argparse
import csv
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def canonical(row: dict) -> tuple:
    """Normalize CSV and Snowflake JSON without losing date/key semantics."""
    numeric = {
        "LATITUDE",
        "LONGITUDE",
        "TEMP_C",
        "TARGET1",
        "PERSISTENCE_C",
        "SPLIT",
        "SEASONAL_2025_C",
        "ELIGIBLE",
        "LEAD_DAYS",
    }
    values = []
    for key in sorted(row):
        value = row[key]
        if value is None or value == "":
            value = None
        elif key in numeric:
            value = float(value)
        elif key in {"AVAILABLE_AT", "TIMESTAMP"}:
            value = datetime.fromisoformat(value).isoformat(timespec="seconds")
        else:
            value = str(value)
        values.append((key, value))
    return tuple(values)


def sql(connection: str, query: str) -> list:
    result = subprocess.run(
        ["snow", "sql", "--connection", connection, "--query", query, "--format", "json"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--connection", required=True)
    parser.add_argument("--data-dir", default=str(ROOT.parents[1] / "data" / "snapshot-2026-10-28"))
    args = parser.parse_args()
    identity = sql(args.connection, "SELECT CURRENT_ACCOUNT(), CURRENT_REGION(), CURRENT_USER()")
    print(identity, flush=True)
    schema = "KUMO_2026"
    data = Path(args.data_dir).resolve()
    setup = "setup_2026.sql"
    sql(args.connection, (ROOT / setup).read_text())
    report = {}
    tables = {
        "stations": "STATIONS",
        "observations": "OBSERVATIONS",
        "training_labels": "TRAINING_LABELS",
        "score_population": "SCORE_POPULATION",
    }
    tables["calendar_2026"] = "CALENDAR_2026"
    for filename, table in tables.items():
        path = data / f"{filename}.csv"
        with path.open() as stream:
            source_rows = list(csv.DictReader(stream))
        expected = len(source_rows)
        destination = f"HELSINKI_WEATHER_LAB.{schema}.{table}"
        existing = sql(args.connection, f"SELECT COUNT(*) AS N FROM {destination}")[0]["N"]
        if existing not in (0, expected):
            raise ValueError(
                f"{destination} contains {existing} rows; expected {expected}; stopped"
            )
        if existing == 0:
            # Paths originate in this fixed experiment directory, not external input.
            safe_path = str(path).replace("'", "''")
            sql(
                args.connection,
                f"PUT 'file://{safe_path}' "
                f"@HELSINKI_WEATHER_LAB.{schema}.INPUT_FILES AUTO_COMPRESS=FALSE OVERWRITE=TRUE",
            )
            sql(
                args.connection,
                f"COPY INTO {destination} "
                f"FROM @HELSINKI_WEATHER_LAB.{schema}.INPUT_FILES/{filename}.csv "
                f"FILE_FORMAT=(FORMAT_NAME=HELSINKI_WEATHER_LAB.{schema}.CSV_INPUT) "
                "ON_ERROR=ABORT_STATEMENT",
            )
        actual = sql(args.connection, f"SELECT COUNT(*) AS N FROM {destination}")[0]["N"]
        if actual != expected:
            raise ValueError(f"Row count mismatch: {destination} {actual} != {expected}")
        # Fixed sample has fewer than 20,000 rows per table. Compare every value,
        # including existing tables, so equal counts cannot conceal changed data.
        if expected > 20_000:
            raise ValueError("Sample exceeds the bounded content-verification limit")
        cloud_rows = sql(args.connection, f"SELECT * FROM {destination} LIMIT 20001")
        if Counter(map(canonical, source_rows)) != Counter(map(canonical, cloud_rows)):
            raise ValueError(f"Content mismatch in {destination}; no data replaced")
        report[table] = actual
        print(f"{destination}: {actual} verified rows", flush=True)
    # Check key uniqueness and reference integrity in Snowflake itself.
    checks = sql(
        args.connection,
        f"""
      SELECT COUNT(*) - COUNT(DISTINCT OBS_ID) AS DUPLICATE_OBSERVATIONS,
        COUNT_IF(AVAILABLE_AT <> DATEADD(day, 1, OBS_DATE)::TIMESTAMP_NTZ) AS BAD_TIMES,
        COUNT_IF(STATION_ID NOT IN (SELECT STATION_ID FROM HELSINKI_WEATHER_LAB.{schema}.STATIONS))
          AS ORPHANS
      FROM HELSINKI_WEATHER_LAB.{schema}.OBSERVATIONS
    """,
    )[0]
    if any(checks.values()):
        raise ValueError(checks)
    evidence = ROOT / "evidence"
    evidence.mkdir(exist_ok=True)
    (evidence / "load_2026.json").write_text(
        json.dumps({"identity": identity, "row_counts": report, "checks": checks}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
