# Experiment reference

## Recorded execution

| Item | Value |
|---|---|
| Run ID / execution date | `7A2528115440` / October 29, 2026 |
| Observation cutoff | October 28, 2026 |
| Snowflake runtime | GPU Container Runtime 2.9, Python 3.12 |
| Kumo Engine | 1.0.0, Snowflake extra |
| PyTorch / CUDA | 2.9.1+cu128 / 12.8 |
| Reported GPU / driver | NVIDIA A10-24Q / 570.211.01 |
| Model plan | FAST, one experiment, seed 42, GNN channels `[64]` |
| Epochs / refit | At most 3; full refit enabled, trainval refit disabled |
| Package route | `snowflake.snowpark.pypi_shared_repository` |

The runtime was live-tested in an Azure trial. This records the successful
configuration, not a guarantee of current capacity or eligibility elsewhere.
Only Kumo and PyTorch are pinned in the GPU requirements. `uv.lock` covers local
development tools, not the Snowflake GPU environment.

## Source data

FMI WFS endpoint: `https://opendata.fmi.fi/wfs`.
Daily query: `fmi::observations::weather::daily::simple`, parameter `tday`.
Station query: `fmi::ef::stations`.

| Station ID | Station |
|---|---|
| 100971 | Helsinki Kaisaniemi |
| 100996 | Helsinki Harmaja |
| 101004 | Helsinki Kumpula |

Temperatures are degrees Celsius. FMI's daily mean is usually based on four or
eight observations per day; this example preserves the published `tday` value.
Current station coordinates are used for historical rows.

The frozen snapshot contains 10,546 observation rows from 2017 through the cutoff.
The full year 2025 contains 1,095 station-days. Eligible labels total 8,601:
6,408 training (2018–2023), 1,098 validation (2024), and 1,095 internal test (2025).
There are 165 historical station-days excluded for unavailable target or history.

`data/snapshot-2026-10-28/manifest.json` records public request URLs, acquisition
time, counts, and original XML hashes. The XML is not committed; the exact CSV
inputs are. `results/2026-10-29/provenance.json` hashes the committed inputs and outputs.

## Files

| Path | Purpose |
|---|---|
| `examples/helsinki/helsinki_temperature_2026.ipynb` | Executable Snowflake Workspace notebook |
| `examples/helsinki/build_2026_notebook.py` | Reviewable notebook source |
| `examples/helsinki/notebook_helpers.py` | Notebook-format helpers and runtime preflight |
| `examples/helsinki/annual_data.py` | Fetch observations and construct annual populations |
| `examples/helsinki/fmi_data.py` | FMI parser, cache, and tested population utilities |
| `examples/helsinki/load_data.py` | Annual-only loader with full content read-back |
| `examples/helsinki/setup_2026.sql` | Tables, stages, and temporal graph views |
| `examples/helsinki/baseline_2026.sql` | Persistence and previous-year baselines |
| `examples/helsinki/run_2026.sql` | Headless notebook execution |
| `examples/helsinki/verify_results.sql` | SQL checks for a completed run |
| `examples/helsinki/export_results.py` | Export a run's CSV and chart |
| `scripts/validate_artifacts.py` | Offline notebook, coverage, metric, and hash checks |

## Snowflake objects

The example database is `HELSINKI_WEATHER_LAB`.

| Schema | Objects |
|---|---|
| `KUMO_2026` | `STATIONS`, `OBSERVATIONS`, `TRAINING_LABELS`, `TRAINING_LABELS_KUMO`, `SCORE_POPULATION`, `CALENDAR_2026` |
| `TRAIN_2026` | Station and temperature views restricted to history before 2026 |
| `SCORE_2026` | Station and temperature views through October 28, 2026 |
| `KUMO_2026` | Run-suffixed `ROLLING_2026_*`, `FUTURE_2026_*`, `PREDICTIONS_2026_*`, `METRICS_2026_*`, `RECURSIVE_HISTORY_*` |

## Published prediction columns

| Column | Meaning |
|---|---|
| `STATION_ID`, `PREDICTION_DATE` | Unique station/day key |
| `ACTUAL_C` | Published observation; null for all future rows |
| `PERSISTENCE_C` | Previous calendar day's actual for rolling evaluation |
| `SEASONAL_2025_C` | Same calendar day in 2025 |
| `PREDICTION_C` | Kumo estimate in °C |
| `PHASE` | `ROLLING_ACTUAL_HISTORY` or `FUTURE_RECURSIVE` |
| `LEAD_DAYS` | 1 for rolling; 1–64 for the separate recursive forecast |
| `ELIGIBLE` | Seven-day observed-history eligibility for rolling rows |
| `ISSUED_AT` | Archival anchor or recursive issuance timestamp |
| `STATUS` | `COMPARED_WITH_ACTUAL` or `FORECAST_ONLY` in the recorded run |

Expected totals: 1,095 predictions, 903 comparisons, 192 future rows, and 183
November/December rows with null actuals. The recursive history has 10,546
`ACTUAL` rows plus 192 `PREDICTED` rows; it is separate from `OBSERVATIONS`.

## Primary sources

- [Snowflake Kumo tutorial](https://www.snowflake.com/en/developers/guides/getting-started-with-nvidia-kumo-graph-neural-networks-in-snowflake/)
- [NVIDIA Snowflake notebook setup](https://docs.nvidia.com/sdgm/kumo-engine/1.0.0/get-started-with-kumo-engine/installation/snowflake-notebook)
- [NVIDIA API source used for review](https://github.com/NVIDIA/kumo-engine/tree/ce6acc6913a3c1d79efedfaaaf9db8552864e1f8)
- [FMI open-data manual](https://en.ilmatieteenlaitos.fi/open-data-manual)
- [FMI observation definitions](https://en.ilmatieteenlaitos.fi/guidance-to-observations)
