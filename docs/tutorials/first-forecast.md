# Your first Helsinki forecast

You will load weather observations, run a GPU notebook, and inspect a full year of
predictions. Use a separate lab database: the example creates objects in
`HELSINKI_WEATHER_LAB` and replaces its example views.

## Before you start

You need Python 3.12, [uv](https://docs.astral.sh/uv/), and the
[Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/installation/installation).
Configure a CLI connection named `snowkumo` using your own account and authentication.
Keep credentials in your local Snowflake configuration, outside this repository.
Use [key-pair authentication](https://docs.snowflake.com/en/user-guide/key-pair-auth)
if you need unattended CLI access.

Your Snowflake role needs permission to create the example database, schemas,
tables, views, and stages; use a query warehouse; and use an available x86 GPU
compute pool. It also needs package access to
`snowflake.snowpark.pypi_shared_repository` through the
`SNOWFLAKE.PYPI_REPOSITORY_USER` database role. Ask your account administrator to
grant the required privileges to a lab role. The notebook does not require an
ACCOUNTADMIN login or a separate Kumo API key.

This run used GPU Container Runtime 2.9 / Python 3.12. GPU availability and trial
entitlements vary by account and region. Compute consumes credits while running.

## 1. Get the example

```bash
git clone https://github.com/MiguelElGallo/SnowKumo.git
cd SnowKumo
uv sync --locked
snow connection test --connection snowkumo
uv run python scripts/validate_artifacts.py
```

The connection test should succeed. The validator should report 1,095 predictions,
903 comparisons, and 192 future predictions. It reads the included result files.

## 2. Load the frozen input

The repository includes the exact CSV inputs used for the published experiment.
They contain observations through October 28, 2026, including all of 2025.

```bash
uv run python examples/helsinki/load_data.py --connection snowkumo
```

The loader creates the lab objects, loads empty tables, and compares every stored
value with its source CSV. Expect 10,546 observations, 8,601 training labels,
903 scoring rows, and 1,095 calendar rows. Existing tables with different content
cause a failure; the loader does not replace their data.

## 3. Prepare the notebook

Open a Snowflake Workspace and upload these two files together:

- `examples/helsinki/helsinki_temperature_2026.ipynb`
- `examples/helsinki/requirements.txt`

Select **GPU Container Runtime 2.9 / Python 3.12**, an available GPU pool, and
the `COMPUTE_WH` query warehouse. If your warehouse has another name, make a separate
working copy of the notebook and update its `connector_for` function and execution
configuration. Keep the committed notebook as the reference for the published results.

Follow Snowflake's [container package setup](https://docs.snowflake.com/en/developer-guide/snowflake-ml/container-runtime-package-management)
to configure the managed repository and requirements file. For the exact managed
installation route used in this run, follow [headless execution](../how-to/operations.md#run-without-an-interactive-notebook-session):
`REQUIREMENTS_FILE` selects the file and `ARTIFACT_REPOSITORIES` selects the repository.
That command runs the whole notebook; continue at step 5 when it finishes.

For an interactive session with PyPI access already configured, you can instead run:

```python
%pip install -r requirements.txt
```

Restart the kernel after installation. The requirements pin Kumo Engine 1.0.0 and
PyTorch 2.9.1; these are the versions used in the successful run.

Run the preflight cell. It must report Python 3.12 and `cuda_available: True`.
If it fails, use the [troubleshooting guide](../how-to/troubleshooting.md) before fitting.

## 4. Follow the notebook

Run the cells in order. First you will see the yearly coverage and chronological
splits. Then the notebook connects the station table to its daily observations.

The prediction is expressed with a Predictive Query, or PQL:

```text
PREDICT AVG(DAILY_TEMPERATURES.TEMP_C, 0, 1, days)
FOR EACH STATIONS.STATION_ID
WHERE COUNT(DAILY_TEMPERATURES.*, -7, 0, days) >= 7
```

The task is one temperature per station and anchor date. Custom labels map that
task to FMI's published daily mean. The seven-day condition requires a complete
recent history; it does not mean the model uses only seven days of history.

The notebook fits one short GNN experiment and refits through 2025. It then makes
daily predictions using available 2026 history and a separate recursive forecast
through December. The completed run took about 20 minutes including 64 sequential
future prediction steps; your runtime may differ.

## 5. Inspect your output

Copy the run ID printed by the configuration cell. The output tables in
`HELSINKI_WEATHER_LAB.KUMO_2026` end with that ID. Replace the example run ID in
`examples/helsinki/verify_results.sql`, then run:

```bash
snow sql --connection snowkumo --filename examples/helsinki/verify_results.sql
```

Expect 1,095 unique station/date pairs, no invalid predictions, and 183 November
and December rows with zero actuals. Your predictions and errors need not exactly
match the published run: GPU execution and dependency resolution can vary.

Read the [results explanation](../explanation/method-and-results.md) before treating
the curves as forecasts. The recorded Kumo model lost to the persistence baseline.

## 6. Stop compute

End the notebook session. Follow [Stop compute](../how-to/operations.md#stop-compute)
to suspend your pool and verify shutdown. The prediction tables remain available.

You now have the complete workflow: source tables, a relational graph, a PQL task,
a fitted model, and predictions that you can query with SQL.
