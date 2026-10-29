"""Acquire a small, reproducible FMI archival hindcast dataset; no credentials required."""

import csv
import hashlib
import math
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATION_IDS = ("100971", "101004", "100996")
NS = {"b": "http://xml.fmi.fi/schema/wfs/2.0", "g": "http://www.opengis.net/gml/3.2"}
DAY = timedelta(days=1)


def fetch(query: str, cache: Path, **params: str) -> dict:
    """Cache original WFS bytes; check OGC exceptions even when HTTP status is 200."""
    url = "https://opendata.fmi.fi/wfs?" + urllib.parse.urlencode(
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "storedquery_id": query,
            **params,
        }
    )
    if not cache.exists():
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    payload = response.read()
                root = ET.fromstring(payload)
                if root.tag.endswith("ExceptionReport"):
                    raise ValueError(ET.tostring(root, encoding="unicode"))
                cache.write_bytes(payload)
                break
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
    payload = cache.read_bytes()
    if ET.fromstring(payload).tag.endswith("ExceptionReport"):
        raise ValueError(f"FMI exception cached in {cache}")
    return {
        "file": cache.name,
        "url": url,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def parse_daily(payload: bytes, station_id: str) -> list[dict]:
    rows = []
    seen = set()
    for item in ET.fromstring(payload).findall(".//b:BsWfsElement", NS):
        if item.findtext("b:ParameterName", namespaces=NS) != "tday":
            raise ValueError("Unexpected FMI parameter")
        timestamp = item.findtext("b:Time", namespaces=NS)
        if timestamp is None:
            raise ValueError("Missing observation timestamp")
        observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if observed.time().isoformat() != "00:00:00":
            raise ValueError(f"Unexpected daily timestamp {timestamp}")
        day = observed.date()
        if day in seen:
            raise ValueError(f"Duplicate observation: {station_id} {day}")
        seen.add(day)
        value = float(item.findtext("b:ParameterValue", default="nan", namespaces=NS))
        if math.isfinite(value) and not -60 <= value <= 50:
            raise ValueError(f"Implausible Helsinki temperature: {value}")
        rows.append(
            {
                "OBS_ID": f"{station_id}_{day.isoformat()}",
                "STATION_ID": station_id,
                "OBS_DATE": day.isoformat(),
                "AVAILABLE_AT": (observed + DAY).strftime("%Y-%m-%d %H:%M:%S"),
                "TEMP_C": value if math.isfinite(value) else None,
            }
        )
    if not rows:
        raise ValueError(f"No daily observations returned for {station_id}")
    return rows


def populations(rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """Require exact calendar history; do not fill gaps or shift over missing days."""
    lookup = {(r["STATION_ID"], date.fromisoformat(r["OBS_DATE"])): r["TEMP_C"] for r in rows}
    if len(lookup) != len(rows):
        raise ValueError("Duplicate station/date keys")
    training, truth = [], []
    counts = {"candidate_days": 0, "missing_target": 0, "incomplete_history": 0}
    for station in STATION_IDS:
        day = date(2018, 1, 1)
        while day <= date(2025, 1, 31):
            counts["candidate_days"] += 1
            target = lookup.get((station, day))
            history = [lookup.get((station, day - DAY * lag)) for lag in range(1, 8)]
            if target is None:
                counts["missing_target"] += 1
            elif any(value is None for value in history):
                counts["incomplete_history"] += 1
            else:
                record = {"ENTITY1": station, "TIMESTAMP": f"{day} 00:00:01", "TARGET1": target}
                if day.year <= 2024:
                    record["SPLIT"] = 0 if day.year <= 2022 else day.year - 2022
                    training.append(record)
                else:
                    truth.append({**record, "PERSISTENCE_C": history[0]})
            day += DAY
    return training, truth, counts


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty dataset: {path}")
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
