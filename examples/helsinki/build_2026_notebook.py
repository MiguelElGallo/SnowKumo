"""Build the revised rolling-2026 plus separate recursive-future Workspace notebook."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from notebook_helpers import CELLS, PREFLIGHT, ROOT, cell, notebook

CELLS.clear()
cell(
    """
# Helsinki: all of 2025, predictions across 2026

Three FMI stations: Kaisaniemi, Kumpula and Harmaja. The dataset includes every
day of 2025 and observations through **2026-10-28**. The output calendar contains
all 365 days of 2026 for each station: 1,095 rows.

**Requested evaluation:** update daily using actual 2026 history. A separate
recursive forecast starts on 2026-10-29 and continues through December 31.
November and December contain predictions only; October 29–31 bridge the gap.
Actuals that are unavailable remain null. Predictions are never labelled actuals.

The target is a **same-day UTC mean temperature hindcast**, issued at 00:00:01 UTC
using previous days. Assume FMI daily values become available at midnight after
their observation date. Actual historical publication/revision times are unknown.
This assumption makes the experiment an archival comparison, not an operational
forecast replay. Long recursive outputs are experimental trajectories: their
uncertainty grows with lead time and has not been calibrated.

Training: 2018–2023, validation: 2024, internal test: 2025; then **full refit** on
all eligible 2018–2025 labels. No 2026 labels are used in fitting or model selection.
The graph links stations to their histories and shares model parameters, without
cross-station spatial edges. Every training row needs seven preceding calendar
days; rolling scoring eligibility is independent of whether its actual is known.

## Setup

From the repository root, load the frozen input snapshot with
`uv run python examples/helsinki/load_data.py --connection snowkumo`.
To load a fresh download from `annual_data.py`, add
`--data-dir examples/helsinki/data/2026`; historical FMI values may have changed.
Upload this notebook and `requirements.txt` into Snowflake Workspaces. Choose GPU
Container Runtime 2.9 / Python 3.12, an available GPU pool, and `COMPUTE_WH`.
Prefer managed package repository `snowflake.snowpark.pypi_shared_repository`.
The tested trial rejected direct PyPI external access (509009); other accounts may differ.
Install `requirements.txt` before execution. It pins Kumo 1.0.0 and PyTorch 2.9.1
to avoid an incompatible CUDA 13 upgrade. For interactive installation, run
`%pip install -r requirements.txt` once and restart the kernel before continuing.

One three-epoch GNN trial plus a refit at the selected epoch (at most three).
Future forecasting performs 64 sequential prediction/index-refresh steps. No
Model Registry, Experiment Tracking, serving endpoint, or recurring job is created.
Stop the notebook service when done. Source/license: © Finnish Meteorological
Institute, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
""",
    "introduction",
    "markdown",
)
cell(
    PREFLIGHT.replace('"KUMO"', '"KUMO_2026"')
    .replace("import importlib.metadata", "import importlib.metadata\nimport logging")
    .replace('print({"python":', 'logging.warning({"python":'),
    "runtime_preflight",
)
cell(
    """
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import kumo.engine as kumo
from kumoapi.graph import Edge
from kumoapi.jobs import MetadataField, PredictionArtifactType, WriteMode
from kumoapi.model_plan import GNNModelPlan, RunMode
from kumoapi.train import TrainingTableSpec
from kumoapi.typing import Stype

assert importlib.metadata.version("kumo-engine") == "1.0.0"
AS_OF = date(2026, 10, 28)
END_DATE = date(2026, 12, 31)
STATION_IDS = {"100971", "101004", "100996"}
run_id = uuid.uuid4().hex[:12].upper()
rolling_name = "ROLLING_2026_" + run_id
future_name = "FUTURE_2026_" + run_id
history_name = "RECURSIVE_HISTORY_" + run_id
calendar_name = "PREDICTIONS_2026_" + run_id
metrics_name = "METRICS_2026_" + run_id
scratch = Path("/tmp/helsinki-kumo-2026") / run_id
scratch.mkdir(parents=True, exist_ok=True)
kumo.configure(scratch_dir=str(scratch))
print("Kumo:", importlib.metadata.version("kumo-engine"), "run:", run_id)
""",
    "configuration",
)
cell(
    """
SELECT YEAR(OBS_DATE) AS YEAR, COUNT(*) AS N, MIN(OBS_DATE) AS FIRST_DAY,
       MAX(OBS_DATE) AS LAST_DAY
FROM HELSINKI_WEATHER_LAB.KUMO_2026.OBSERVATIONS
WHERE OBS_DATE >= '2025-01-01' GROUP BY YEAR(OBS_DATE) ORDER BY YEAR
""",
    "year_coverage",
    "sql",
)
cell(
    """
SELECT SPLIT, COUNT(*) AS N, MIN(TIMESTAMP) AS FIRST_ANCHOR, MAX(TIMESTAMP) AS LAST_ANCHOR
FROM HELSINKI_WEATHER_LAB.KUMO_2026.TRAINING_LABELS GROUP BY SPLIT ORDER BY SPLIT
""",
    "training_splits",
    "sql",
)
cell(
    """
SELECT PHASE, COUNT(*) AS CALENDAR_ROWS, COUNT(TARGET1) AS ACTUAL_ROWS,
       COUNT_IF(ELIGIBLE=1) AS ELIGIBLE_ROLLING_ROWS
FROM HELSINKI_WEATHER_LAB.KUMO_2026.CALENDAR_2026 GROUP BY PHASE ORDER BY PHASE
""",
    "calendar_coverage",
    "sql",
)
cell(
    """
SELECT OBS_DATE, s.NAME, TEMP_C
FROM HELSINKI_WEATHER_LAB.KUMO_2026.OBSERVATIONS o
JOIN HELSINKI_WEATHER_LAB.KUMO_2026.STATIONS s USING (STATION_ID)
WHERE OBS_DATE >= '2025-01-01' ORDER BY OBS_DATE, s.NAME LIMIT 2200
""",
    "observed_history",
    "sql",
)
cell(
    """
import matplotlib.pyplot as plt

observed = observed_history.limit(2200).to_pandas()  # noqa: F821 - SQL binding
fig, ax = plt.subplots(figsize=(12, 4))
for name, group in observed.groupby("NAME"):
    ax.plot(group["OBS_DATE"], group["TEMP_C"], label=name, linewidth=0.8)
ax.axvline(date(2026, 1, 1), color="black", linestyle="--", label="2026 evaluation starts")
ax.set(title="Full 2025 and available 2026 FMI observations", ylabel="°C", xlabel="UTC date")
ax.legend()
plt.show()
""",
    "observations_chart",
)
cell(
    """
def connector_for(schema):
    return kumo.SnowflakeConnector.from_spcs_env(
        warehouse="COMPUTE_WH", database="HELSINKI_WEATHER_LAB", schema_name=schema
    )


def graph_for(connector, history_sql=None):
    stations = kumo.Table.from_source_table(
        connector["STATIONS"], ["STATION_ID", "LATITUDE", "LONGITUDE"],
        primary_key="STATION_ID",
    )
    if history_sql is None:
        daily = kumo.Table.from_source_table(
            connector["DAILY_TEMPERATURES"],
            ["OBS_ID", "STATION_ID", "AVAILABLE_AT", "TEMP_C"],
            primary_key="OBS_ID", time_column="AVAILABLE_AT",
        )
    else:
        daily = kumo.Table.from_sql(
            connector, history_sql, primary_key="OBS_ID", time_column="AVAILABLE_AT"
        )
    daily = daily.with_column("STATION_ID", stype=Stype.ID)
    graph = kumo.Graph(
        tables={"STATIONS": stations, "DAILY_TEMPERATURES": daily},
        edges=[Edge(src_table="DAILY_TEMPERATURES", fkey="STATION_ID", dst_table="STATIONS")],
    )
    graph.validate()
    return graph


QUERY = "PREDICT AVG(DAILY_TEMPERATURES.TEMP_C, 0, 1, days) " \
        "FOR EACH STATIONS.STATION_ID " \
        "WHERE COUNT(DAILY_TEMPERATURES.*, -7, 0, days) >= 7"
train_graph = graph_for(connector_for("TRAIN_2026"))
pquery = kumo.PredictiveQuery(graph=train_graph, query=QUERY)
pquery.validate()
assert str(pquery.get_task_type()).lower() == "regression"
print(pquery.query)
train_snapshot = train_graph.snapshot()
populations = connector_for("KUMO_2026")
spec = TrainingTableSpec(split_col="SPLIT")
training_table = kumo.TrainingTable.from_source_table(
    populations["TRAINING_LABELS_KUMO"], spec, pq=pquery, snapshot=train_snapshot
)
""",
    "graph_and_labels",
)
cell(
    """
## Fit, then include the full 2025 training history

The initial trial uses 2024 for selection and 2025 for an internal test. Full refit
then includes all eligible labels through December 2025. Kumo prediction uses that
full-refit model automatically. Internal metrics below describe the pre-refit model;
the final model is evaluated only against 2026 actuals.
""",
    "refit_notes",
    "markdown",
)
cell(
    """
plan = pquery.suggest_model_plan(train_snapshot, run_mode=RunMode.FAST, train_table_spec=spec)
plan.training_job.num_experiments = 1
plan.training_job.refit_trainval = False
plan.training_job.refit_full = True
plan.training_job.manual_seed = 42
plan.optimization.max_epochs = 3
plan.model_architecture.model = [GNNModelPlan(channels=[64])]
trainer = kumo.Trainer(plan)
result = trainer.fit(training_table, snapshot=train_snapshot)
print("Pre-refit internal metrics:", result.metrics)
""",
    "fit_and_refit",
)
cell(
    """
## Rolling 2026 comparison

The scoring graph contains actual history through October 28. Kumo's temporal
sampling restricts each anchor to earlier availability timestamps; later 2026
observations are not inputs for earlier anchors. The model is fixed after the
2025 refit; daily updates here mean updated observed history, not daily retraining.
Targets are kept outside the scoring population. Missing targets do not remove
otherwise eligible scoring rows.
""",
    "rolling_notes",
    "markdown",
)
cell(
    """
score_graph = graph_for(connector_for("SCORE_2026"))
score_query = kumo.PredictiveQuery(graph=score_graph, query=QUERY)
score_query.validate()
score_snapshot = score_graph.snapshot()
rolling_population = kumo.PredictionTable.from_source_table(
    populations["SCORE_POPULATION"], pq=score_query, snapshot=score_snapshot,
    plan=trainer.training_table_generation_plan,
)
expected_rolling = session.table("HELSINKI_WEATHER_LAB.KUMO_2026.SCORE_POPULATION").count()
assert rolling_population.row_count == expected_rolling, "Kumo dropped eligible rolling anchors"
written = trainer.predict(
    rolling_population, snapshot=score_snapshot,
    output_config=kumo.PredictionOutputConfig(
        connector=populations, artifact_type=PredictionArtifactType.PREDICTIONS,
        table_name=rolling_name, write_mode=WriteMode.OVERWRITE,
        extra_fields=[MetadataField.ANCHOR_TIMESTAMP],
    ),
)
assert written.num_rows == rolling_population.row_count
print("Rolling predictions saved:", rolling_name, written.num_rows)
""",
    "rolling_predictions",
)
cell(
    """
## Separate recursive forecast through December 31

Seed with actuals only through October 28. Each next day's prediction is appended
to a dedicated working table and becomes available the following midnight. Never
append generated rows to the observations table. The October bridge is included.

Each step changes the literal SQL cutoff and therefore the graph fingerprint.
This avoids Kumo 1.0.0's hourly cache version for Snowflake views. Snapshot IDs must
change after each step. Future predictions have no actual values or accuracy metrics.
""",
    "future_notes",
    "markdown",
)
cell(
    """
# DDL names contain only fixed prefixes and a generated hexadecimal run ID.
session.sql(f"CREATE TABLE HELSINKI_WEATHER_LAB.KUMO_2026.{history_name} AS "
            "SELECT OBS_ID, STATION_ID, AVAILABLE_AT, TEMP_C, OBS_DATE, "
            "CAST('ACTUAL' AS VARCHAR(16)) AS SOURCE_TYPE "
            "FROM HELSINKI_WEATHER_LAB.KUMO_2026.OBSERVATIONS "
            f"WHERE OBS_DATE <= '{AS_OF}' AND TEMP_C IS NOT NULL").collect()
seed = (session.table(["HELSINKI_WEATHER_LAB", "KUMO_2026", history_name])
        .filter(f"OBS_DATE >= DATEADD(day, -6, '{AS_OF}'::DATE)")
        .select("STATION_ID", "OBS_DATE").limit(100).to_pandas())
expected_seed = {(station, AS_OF - timedelta(days=lag))
                 for station in STATION_IDS for lag in range(7)}
actual_seed = {(str(r.STATION_ID), pd.Timestamp(r.OBS_DATE).date()) for r in seed.itertuples()}
assert actual_seed == expected_seed, "Forecast seed is missing a station/calendar day"

previous_snapshot_id = None
day = AS_OF + timedelta(days=1)
step = 0
while day <= END_DATE:
    anchor = datetime.combine(day, time(0, 0, 1))
    history_sql = (
        "SELECT OBS_ID, STATION_ID, AVAILABLE_AT, TEMP_C "
        f"FROM HELSINKI_WEATHER_LAB.KUMO_2026.{history_name} "
        f"WHERE AVAILABLE_AT < '{anchor:%Y-%m-%d %H:%M:%S}'"
    )
    graph = graph_for(populations, history_sql)
    query = kumo.PredictiveQuery(graph=graph, query=QUERY)
    query.validate()
    snapshot = graph.snapshot()
    assert snapshot.id != previous_snapshot_id, "Stale recursive graph snapshot"
    previous_snapshot_id = snapshot.id
    population = query.generate_prediction_table(
        snapshot, prediction_time=anchor, plan=trainer.training_table_generation_plan
    )
    assert population.row_count == len(STATION_IDS)
    frame = trainer.predict(population, snapshot=snapshot).frame
    assert len(frame) == len(STATION_IDS)
    assert set(frame["ENTITY"].astype(str)) == STATION_IDS
    assert np.isfinite(frame["TARGET_PRED"]).all()
    assert frame["TARGET_PRED"].between(-60, 50).all(), "Implausible forecast; stop recursion"
    forecasts, history_rows = [], []
    for row in frame.itertuples():
        station, predicted = str(row.ENTITY), float(row.TARGET_PRED)
        forecasts.append({"STATION_ID": station, "FORECAST_DATE": day,
                          "PREDICTION_C": predicted, "ISSUED_AT": datetime.combine(
                              AS_OF + timedelta(days=1), time(0, 0, 1)),
                          "LEAD_DAYS": (day - AS_OF).days})
        history_rows.append({"OBS_ID": f"{station}_{day}", "STATION_ID": station,
                             "AVAILABLE_AT": datetime.combine(day + timedelta(days=1), time()),
                             "TEMP_C": predicted, "OBS_DATE": day, "SOURCE_TYPE": "PREDICTED"})
    mode = "errorifexists" if step == 0 else "append"
    session.create_dataframe(forecasts).write.mode(mode).save_as_table(
        ["HELSINKI_WEATHER_LAB", "KUMO_2026", future_name], column_order="name"
    )
    session.create_dataframe(history_rows).write.mode("append").save_as_table(
        ["HELSINKI_WEATHER_LAB", "KUMO_2026", history_name], column_order="name"
    )
    step += 1
    print("Forecast", day, "lead", step, "rows", len(forecasts))
    day += timedelta(days=1)
assert session.table(["HELSINKI_WEATHER_LAB", "KUMO_2026", future_name]).count() == (
    END_DATE - AS_OF).days * len(STATION_IDS)
""",
    "recursive_future",
)
cell(
    """
# Preserve every day with explicit prediction status; the calendar is the left side.
session.sql(f"""
    + '"""'
    + """
CREATE TABLE HELSINKI_WEATHER_LAB.KUMO_2026.{calendar_name} AS
SELECT c.ENTITY1 AS STATION_ID, c.TIMESTAMP::DATE AS PREDICTION_DATE,
       c.TARGET1 AS ACTUAL_C, c.PERSISTENCE_C, c.SEASONAL_2025_C,
       COALESCE(r.TARGET_PRED::FLOAT, f.PREDICTION_C) AS PREDICTION_C,
       c.PHASE, c.LEAD_DAYS, c.ELIGIBLE,
       IFF(c.PHASE='ROLLING_ACTUAL_HISTORY', c.TIMESTAMP, f.ISSUED_AT) AS ISSUED_AT,
       CASE WHEN c.PHASE='ROLLING_ACTUAL_HISTORY' AND c.ELIGIBLE=0 THEN 'INSUFFICIENT_HISTORY'
            WHEN COALESCE(r.TARGET_PRED::FLOAT, f.PREDICTION_C) IS NULL THEN 'NOT_PRODUCED'
            WHEN c.PHASE='FUTURE_RECURSIVE' THEN 'FORECAST_ONLY'
            WHEN c.TARGET1 IS NULL THEN 'ACTUAL_UNAVAILABLE'
            ELSE 'COMPARED_WITH_ACTUAL' END AS STATUS
FROM HELSINKI_WEATHER_LAB.KUMO_2026.CALENDAR_2026 c
LEFT JOIN HELSINKI_WEATHER_LAB.KUMO_2026.{rolling_name} r
  ON r.ENTITY::VARCHAR=c.ENTITY1 AND r.ANCHOR_TIMESTAMP::TIMESTAMP_NTZ=c.TIMESTAMP
LEFT JOIN HELSINKI_WEATHER_LAB.KUMO_2026.{future_name} f
  ON f.STATION_ID=c.ENTITY1 AND f.FORECAST_DATE=c.TIMESTAMP::DATE
"""
    + '"""'
    + """).collect()
""",
    "save_calendar",
)
cell(
    """
SELECT * FROM HELSINKI_WEATHER_LAB.KUMO_2026.{{calendar_name}}
ORDER BY PREDICTION_DATE, STATION_ID LIMIT 2000
""",
    "all_predictions",
    "sql",
)
cell(
    """
all_rows = all_predictions.limit(2000).to_pandas()  # noqa: F821 - SQL binding
assert len(all_rows) == 1095
assert not all_rows.duplicated(["STATION_ID", "PREDICTION_DATE"]).any()
eligible = all_rows[(all_rows["PHASE"] == "ROLLING_ACTUAL_HISTORY") &
                    (all_rows["ELIGIBLE"] == 1)]
assert len(eligible) == expected_rolling
assert np.isfinite(eligible["PREDICTION_C"].to_numpy()).all()
future = all_rows[all_rows["PHASE"] == "FUTURE_RECURSIVE"]
assert future["ACTUAL_C"].isna().all()
assert len(future) == 192 and future["PREDICTION_C"].notna().all()
paired = all_rows[(all_rows["PHASE"] == "ROLLING_ACTUAL_HISTORY") &
                  all_rows[["ACTUAL_C", "PREDICTION_C", "PERSISTENCE_C",
                            "SEASONAL_2025_C"]].notna().all(axis=1)]
assert len(paired) > 0
assert np.isfinite(paired[["ACTUAL_C", "PREDICTION_C", "PERSISTENCE_C",
                          "SEASONAL_2025_C"]].to_numpy()).all()
metrics = []
for model, column in [("KUMO_GNN", "PREDICTION_C"), ("PERSISTENCE", "PERSISTENCE_C"),
                       ("SEASONAL_NAIVE_2025", "SEASONAL_2025_C")]:
    error = paired[column] - paired["ACTUAL_C"]
    metrics.append({"RUN_ID": run_id, "MODEL": model, "N": len(paired),
                    "MAE_C": float(error.abs().mean()),
                    "RMSE_C": float(np.sqrt((error**2).mean()))})
session.create_dataframe(metrics).write.mode("errorifexists").save_as_table(
    ["HELSINKI_WEATHER_LAB", "KUMO_2026", metrics_name]
)
print(pd.DataFrame(metrics).to_string(index=False))
print(all_rows.groupby(["PHASE", "STATUS"]).size())
print("Persisted calendar:", calendar_name, "metrics:", metrics_name)
""",
    "compare_actuals",
)
cell(
    """
fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
names = {"100971": "Kaisaniemi", "101004": "Kumpula", "100996": "Harmaja"}
for ax, (station, rows) in zip(axes, all_rows.groupby("STATION_ID"), strict=True):
    ax.plot(rows["PREDICTION_DATE"], rows["ACTUAL_C"], label="Actual FMI", linewidth=0.9)
    past = rows[rows["PHASE"] == "ROLLING_ACTUAL_HISTORY"]
    remaining = rows[rows["PHASE"] == "FUTURE_RECURSIVE"]
    ax.plot(past["PREDICTION_DATE"], past["PREDICTION_C"], label="Daily Kumo", linewidth=0.8)
    ax.plot(remaining["PREDICTION_DATE"], remaining["PREDICTION_C"],
            label="Recursive forecast only", linestyle="--")
    ax.axvspan(date(2026, 11, 1), END_DATE, alpha=0.08, color="orange")
    ax.axvline(AS_OF, color="grey", linestyle=":")
    ax.set(title=names[station], ylabel="°C")
    ax.legend(loc="upper right")
axes[-1].set_xlabel("2026 UTC date; November/December show predictions only")
plt.tight_layout()
plt.show()
""",
    "year_chart",
)
cell(
    """
## Interpretation and cleanup

The 2026 comparison evaluates one-day archival predictions of the model refit
through 2025. It does **not** validate the long recursive trajectory. Do not compare
November/December predictions with invented actuals, report confidence intervals
without calibration, or describe a three-epoch smoke test as a weather service.

Stop the notebook service and, after verifying no other workloads use the GPU pool,
suspend the pool from a separate worksheet/CLI. `SUSPEND` alone lets active jobs
finish, so cancel this notebook execution first if it is still running.

```sql
SHOW COMPUTE POOLS LIKE 'SYSTEM_COMPUTE_POOL_GPU';
ALTER COMPUTE POOL SYSTEM_COMPUTE_POOL_GPU SUSPEND;
```

Outputs stay in `HELSINKI_WEATHER_LAB.KUMO_2026`. Run-specific recursive history is
retained for provenance and has `SOURCE_TYPE='ACTUAL'` or `'PREDICTED'`.
Original observations are unchanged. Scratch models are ephemeral.

Sources: [tutorial](https://www.snowflake.com/en/developers/guides/getting-started-with-nvidia-kumo-graph-neural-networks-in-snowflake/),
[FMI manual](https://en.ilmatieteenlaitos.fi/open-data-manual),
[FMI observation definitions](https://en.ilmatieteenlaitos.fi/guidance-to-observations),
[NVIDIA source](https://github.com/NVIDIA/kumo-engine/tree/ce6acc6913a3c1d79efedfaaaf9db8552864e1f8).
""",
    "finish",
    "markdown",
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "helsinki_temperature_2026.ipynb")
    output = parser.parse_args().output
    output.write_text(json.dumps(notebook(CELLS), indent=2) + "\n")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--select",
            "I",
            "--fix",
            str(output),
        ],
        check=True,
    )
    subprocess.run([sys.executable, "-m", "ruff", "format", "--no-cache", str(output)], check=True)
