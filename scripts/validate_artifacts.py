"""Validate published evidence without connecting to Snowflake or fitting a model."""

import csv
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import nbformat
from IPython.core.inputtransformer2 import TransformerManager

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "2026-10-29"
EXAMPLE = ROOT / "examples" / "helsinki"
SNAPSHOT = ROOT / "data" / "snapshot-2026-10-28"
STATIONS = {"100971", "100996", "101004"}


def rows(path: Path) -> list[dict]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def validate() -> None:
    predictions = rows(RESULTS / "helsinki_2026_kumo.csv")
    expected = {
        (station, str(date(2026, 1, 1) + timedelta(days=i)))
        for station in STATIONS
        for i in range(365)
    }
    keys = {(r["STATION_ID"], r["PREDICTION_DATE"]) for r in predictions}
    assert len(predictions) == len(keys) == 1095 and keys == expected
    assert all(math.isfinite(float(r["PREDICTION_C"])) for r in predictions)
    rolling = [r for r in predictions if r["PREDICTION_DATE"] <= "2026-10-28"]
    future = [r for r in predictions if r["PREDICTION_DATE"] > "2026-10-28"]
    assert len(rolling) == 903 and len(future) == 192
    assert all(r["ACTUAL_C"] and r["PHASE"] == "ROLLING_ACTUAL_HISTORY" for r in rolling)
    assert all(
        not r["ACTUAL_C"] and r["STATUS"] == "FORECAST_ONLY" and r["PHASE"] == "FUTURE_RECURSIVE"
        for r in future
    )
    assert sum(r["PREDICTION_DATE"] >= "2026-11-01" for r in future) == 183

    observations = rows(SNAPSHOT / "observations.csv")
    lookup = {(r["STATION_ID"], r["OBS_DATE"]): r for r in observations}
    assert len(observations) == len(lookup) == 10546
    assert max(r["OBS_DATE"] for r in observations) == "2026-10-28"
    for row in rolling:
        station, day = row["STATION_ID"], date.fromisoformat(row["PREDICTION_DATE"])
        assert float(row["ACTUAL_C"]) == float(lookup[station, str(day)]["TEMP_C"])
        yesterday = lookup[station, str(day - timedelta(days=1))]
        assert float(row["PERSISTENCE_C"]) == float(yesterday["TEMP_C"])
        previous_year = lookup[station, str(day.replace(year=2025))]
        assert float(row["SEASONAL_2025_C"]) == float(previous_year["TEMP_C"])
    labels = rows(SNAPSHOT / "training_labels.csv")
    assert len(labels) == 8601 and all(r["TIMESTAMP"] < "2026-01-01" for r in labels)
    assert {s: sum(r["SPLIT"] == s for r in labels) for s in ("0", "1", "2")} == {
        "0": 6408,
        "1": 1098,
        "2": 1095,
    }
    for row in labels:
        anchor = date.fromisoformat(row["TIMESTAMP"][:10])
        assert float(row["TARGET1"]) == float(lookup[row["ENTITY1"], str(anchor)]["TEMP_C"])
        for lag in range(1, 8):
            assert math.isfinite(
                float(lookup[row["ENTITY1"], str(anchor - timedelta(days=lag))]["TEMP_C"])
            )

    reported = json.loads((RESULTS / "metrics.json").read_text())
    for name, column in {
        "kumo": "PREDICTION_C",
        "persistence": "PERSISTENCE_C",
        "seasonal_naive_2025": "SEASONAL_2025_C",
    }.items():
        errors = [float(r[column]) - float(r["ACTUAL_C"]) for r in rolling]
        actual = {
            "n": len(errors),
            "mae_c": sum(map(abs, errors)) / len(errors),
            "rmse_c": math.sqrt(sum(e * e for e in errors) / len(errors)),
        }
        for metric, value in actual.items():
            assert math.isclose(value, reported[name][metric], abs_tol=1e-10)
    cold = [r for r in rolling if float(r["ACTUAL_C"]) < 0]
    assert len(cold) == 169 and all(float(r["PREDICTION_C"]) >= 0 for r in cold)

    path = EXAMPLE / "helsinki_temperature_2026.ipynb"
    before = path.read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        generated = Path(directory) / path.name
        subprocess.run(
            [sys.executable, str(EXAMPLE / "build_2026_notebook.py"), "--output", str(generated)],
            check=True,
            cwd=ROOT,
        )
        assert generated.read_bytes() == before, (
            "Notebook differs from its builder; nothing changed"
        )
    notebook = nbformat.read(path, as_version=4)
    nbformat.validate(notebook)
    ids = [c.id for c in notebook.cells]
    assert len(ids) == len(set(ids)) and all(re.fullmatch(r"[A-Za-z0-9]{8}", i) for i in ids)
    transform = TransformerManager()
    for cell in notebook.cells:
        if cell.cell_type == "code":
            assert not cell.outputs and cell.execution_count is None
            compile(transform.transform_cell(cell.source), f"notebook:{cell.id}", "exec")
    code = "\n".join(c.source for c in notebook.cells if c.cell_type == "code")
    provenance = json.loads((RESULTS / "provenance.json").read_text())
    assert hashlib.sha256(code.encode()).hexdigest() == provenance["executed_code_cells_sha256"]
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name

    # Check local documentation links, including images, without requiring network access.
    for path in ROOT.rglob("*.md"):
        if ".venv" in path.parts:
            continue
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            assert (path.parent / target.split("#")[0]).exists(), (path, target)
    print(
        "Validated: 1,095 predictions; 903 comparisons; 192 future predictions; "
        "notebook, metrics, source labels, links, and hashes OK."
    )


if __name__ == "__main__":
    validate()
