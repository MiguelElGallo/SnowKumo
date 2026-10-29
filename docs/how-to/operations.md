# Operate the example

These recipes require the [tutorial prerequisites and steps 1–2](../tutorials/first-forecast.md):
configure access, get the repository, and load the input. They do not require a
prior training run; headless execution is an alternative to the interactive route.
Run shell commands from the repository root.

## Run without an interactive notebook session

Load the input with `load_data.py` first. Upload the notebook and requirements to
the stage created by the loader. Replace `/absolute/path/to/SnowKumo` below with
your checkout path:

```sql
PUT 'file:///absolute/path/to/SnowKumo/examples/helsinki/helsinki_temperature_2026.ipynb'
  @HELSINKI_WEATHER_LAB.KUMO_2026.NOTEBOOK_FILES AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file:///absolute/path/to/SnowKumo/examples/helsinki/requirements.txt'
  @HELSINKI_WEATHER_LAB.KUMO_2026.NOTEBOOK_FILES AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
CREATE NOTEBOOK PROJECT HELSINKI_WEATHER_LAB.KUMO_2026.HELSINKI_TEMPERATURE_2026
  FROM '@HELSINKI_WEATHER_LAB.KUMO_2026.NOTEBOOK_FILES';
```

Submit these statements with `snow sql --connection snowkumo --filename your-file.sql`.
Creation copies the source into the runnable object. Uploading revised files to the
stage does not update an existing object. Use a new object name and update
`run_2026.sql` when revising the notebook.

Edit the compute-pool and query-warehouse names in `examples/helsinki/run_2026.sql`
to match your account, then execute:

```bash
snow sql --connection snowkumo --filename examples/helsinki/run_2026.sql
```

The recorded run completed with `Statement executed successfully.` Verify the
result tables afterward. Snowflake now calls these objects
[Code Bundles](https://docs.snowflake.com/en/sql-reference/sql/create-code-bundle);
the `NOTEBOOK PROJECT` grammar used in the verified run remains supported.
Creating and executing the object requires the corresponding schema and compute privileges.

## Export another completed run

Replace the example table suffix with your run ID:

```bash
uv run python examples/helsinki/export_results.py \
  --connection snowkumo --table PREDICTIONS_2026_7A2528115440
```

The exporter writes a CSV, a chart, and 2025 observations beside the notebook.
It checks row counts, duplicate station/date pairs, and null future actuals.
These local exports are ignored by Git. The committed result snapshot is unchanged.

To inspect SQL baselines independently of the GPU notebook:

```bash
snow sql --connection snowkumo --filename examples/helsinki/baseline_2026.sql
```

## Fetch the source again

```bash
uv run python examples/helsinki/annual_data.py
uv run python examples/helsinki/load_data.py --connection snowkumo \
  --data-dir examples/helsinki/data/2026
```

The first command retrieves FMI WFS data and caches raw XML under
`examples/helsinki/data/raw`. It writes CSVs and a URL/checksum manifest under
`examples/helsinki/data/2026`. The date cutoff stays October 28, 2026.
FMI can revise historical observations; a fresh download may differ from the
committed snapshot. Load changed data into a separate lab database by consistently
updating the SQL and notebook database name. Do not mix different source versions
in one run.

Advancing the cutoff creates a new experiment. It requires coordinated edits to
`AS_OF` in `annual_data.py` and the notebook builder, the scoring view in
`setup_2026.sql`, chart labels in `export_results.py`, and fixed population
expectations such as the notebook's 192 future rows. Use a separate working copy,
new run evidence, and checks appropriate to the changed dates. The reference
validator deliberately rejects changes to the executed model code or frozen results;
do not relabel a custom run as the original evidence. No daily refresh task is installed.

## Rebuild the notebook

Edit `examples/helsinki/build_2026_notebook.py`, then run:

```bash
uv run python examples/helsinki/build_2026_notebook.py
uv run python scripts/validate_artifacts.py
```

The validator compares a temporary build with the committed notebook; it does not
overwrite your file. It also pins the original executed code cells. Documentation
changes can pass this check, but model, warehouse, or date changes require their
own experiment and evidence rather than replacing the recorded code hash.

## Stop compute

Finish or cancel this notebook's execution and stop its interactive session.
From a separate worksheet or CLI, inspect the pool you used. Replace
`SYSTEM_COMPUTE_POOL_GPU` in every command below with your selected pool's name:

```sql
SHOW COMPUTE POOLS LIKE 'SYSTEM_COMPUTE_POOL_GPU';
```

Confirm that no other workloads need it, then suspend that pool:

```sql
ALTER COMPUTE POOL SYSTEM_COMPUTE_POOL_GPU SUSPEND;
SHOW COMPUTE POOLS LIKE 'SYSTEM_COMPUTE_POOL_GPU';
```

Expect `SUSPENDED` and zero active/target nodes after shutdown. Suspending lets
running jobs finish, so it is not a substitute for canceling an unwanted run.
Check your query warehouse's auto-suspend setting as well. Predictions persist;
the in-process trainer and scratch files do not constitute a saved model.
