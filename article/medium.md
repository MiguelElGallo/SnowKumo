# NVIDIA Kumo in Snowflake: from weather tables to a working GNN

## A Helsinki experiment with a simple setup—and an honest baseline comparison

The useful part of trying a new machine-learning library is getting from your own
data to an answer you can inspect. With NVIDIA Kumo Engine in Snowflake, that path
can stay in one notebook: connect tables, describe a prediction, train, and write
the results back to tables.

I tested that workflow with Helsinki temperatures. It completed GPU training and
produced 1,095 predictions covering three stations across all of 2026. The setup
needed two compatibility fixes, which are included in the example repository.

The accuracy result deserves equal attention: Kumo's average absolute error was
3.09°C, while predicting yesterday's temperature achieved 1.45°C. This was a short
three-epoch experiment. It demonstrates the integration, not a reliable weather service.

Everything needed to inspect or repeat it is in
[SnowKumo on GitHub](https://github.com/MiguelElGallo/SnowKumo): the notebook,
input snapshot, SQL, prediction CSV, chart, and documentation.

## Start with two related tables

The source is open data from the Finnish Meteorological Institute: published daily
mean temperatures for Kaisaniemi, Harmaja, and Kumpula. All 365 days of 2025 are
included. Earlier observations support training, and 2026 actuals are available
through October 28.

One table describes the stations. Another holds daily temperatures, with a station
ID and an availability timestamp. Kumo connects each observation to its station.
That is the graph in this example; there are no explicit spatial links between stations.

The notebook's connector uses the Snowflake container identity. There is no
separate Kumo account or API key to paste into a cell:

```python
import kumo.engine as kumo

connector = kumo.SnowflakeConnector.from_spcs_env(
    warehouse="COMPUTE_WH",
    database="HELSINKI_WEATHER_LAB",
    schema_name="TRAIN_2026",
)
```

The GPU pool handles graph and model computation. The query warehouse reads the
Snowflake tables. Keeping that distinction clear makes setup easier to diagnose.

## Describe the prediction

Kumo's Predictive Query Language expresses the task in a form that is easy to read:

```text
PREDICT AVG(DAILY_TEMPERATURES.TEMP_C, 0, 1, days)
FOR EACH STATIONS.STATION_ID
WHERE COUNT(DAILY_TEMPERATURES.*, -7, 0, days) >= 7
```

For this experiment, custom labels associate each station and date with FMI's
published daily mean. The recent-history condition requires seven complete days
before a prediction is eligible. It does not limit all model inputs to seven days.

The notebook validates the graph and query, creates a snapshot, and constructs the
training population. It then fits one small GNN experiment. The full implementation
is in the repository; these snippets show the main ideas rather than a standalone script.

The initial split trains on 2018–2023, validates on 2024, and tests internally on
2025. A final refit includes eligible history through 2025. No 2026 labels enter
fitting or model selection.

## Make the runtime predictable

The successful run used Snowflake GPU Container Runtime 2.9 with Python 3.12 and
these requirements:

```text
kumo-engine[snowflake]==1.0.0
torch==2.9.1
```

Two details mattered. An unpinned PyTorch upgrade selected a CUDA build that the
runtime's driver could not use. Pinning PyTorch restored a working GPU environment.
The custom-label loader also rejected Snowflake's exported split-column type;
a view exposing the split as strings `0`, `1`, and `2` resolved that mismatch.

The trial account rejected the guide's direct PyPI external-access integration.
Package installation worked through Snowflake's managed Artifact Repository instead.
GPU capacity also required an available pool configuration. These are observations
from this account, not a promise that every trial has the same capabilities.

Once those pieces were in place, the notebook handled fitting and predictions in
the same process. That is the approachable part: the workflow stays close to the
tables and the prediction question, without building a separate training service.

## Compare with actuals before trusting the curve

For January 1 through October 28, the fixed model receives the actual history
available before each day's anchor. It is not retrained daily. The comparison uses
903 station-days, with the same rows for every method:

| Method | MAE °C | RMSE °C |
|---|---:|---:|
| Kumo GNN | 3.09 | 4.86 |
| Yesterday's actual | **1.45** | **1.96** |
| Same calendar day in 2025 | 3.43 | 4.76 |

MAE measures the average absolute miss. RMSE gives more weight to large misses.
Kumo improved MAE over the previous-year baseline, but persistence was clearly
better on both measures and at every station.

![Helsinki: full 2025 observations and 2026 actuals, daily Kumo predictions, and recursive future predictions](../results/2026-10-29/helsinki_2026_kumo.png)

*The top panel shows three observed station series for 2025. In the 2026 panels,
solid blue lines are actuals and orange lines are Kumo predictions. Dashed orange
lines continue beyond the October 28 cutoff. Shaded November and December contain
predictions only. Source: © Finnish Meteorological Institute, CC BY 4.0; model
outputs and chart from SnowKumo, run October 29, 2026.*

Winter exposes the model's weakness. Its average signed error was +1.93°C, and it
predicted no subzero values on the 169 station-days when the actual was below zero.
That is a reason to investigate the model and inputs, not to hide the baseline.

## Keep future predictions separate

From October 29 through December 31, the notebook forecasts recursively: each
prediction becomes history for the next step. This produces 192 future rows,
including 183 in November and December. Their actual-temperature fields stay null.

The future curve is an experimental trajectory. It has no measured future accuracy
or calibrated confidence interval. The comparison with past actuals is also an
archival hindcast: it assumes a daily observation becomes available at midnight
the next day, because historical FMI publication and revision times are unknown.

The source snapshot is fixed through October 28. “Daily updates” describes how
observed history enters the evaluation; no scheduled refresh or forecasting service
is installed. Prediction tables persist after compute is stopped.

## Try it with the complete example

SnowKumo separates the learning path from the details. Start with the tutorial,
use the how-to guides for execution and cleanup, consult the reference for schemas
and versions, and read the explanation for the evaluation choices.

The run shows that NVIDIA Kumo can turn related Snowflake tables into a working
GPU experiment with a compact notebook workflow. Whether it produces useful
predictions is a second question, answered by the comparison you build around it.

Start with the [SnowKumo tutorial](https://github.com/MiguelElGallo/SnowKumo/blob/main/docs/tutorials/first-forecast.md)
and inspect the [results and method](https://github.com/MiguelElGallo/SnowKumo/blob/main/docs/explanation/method-and-results.md).
The workflow builds on the [Snowflake Kumo guide](https://www.snowflake.com/en/developers/guides/getting-started-with-nvidia-kumo-graph-neural-networks-in-snowflake/)
and [NVIDIA's Snowflake setup documentation](https://docs.nvidia.com/sdgm/kumo-engine/1.0.0/get-started-with-kumo-engine/installation/snowflake-notebook).
Weather data comes from [FMI open data](https://en.ilmatieteenlaitos.fi/open-data-manual),
under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
