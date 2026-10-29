# LinkedIn graphic

The portrait chart is designed at 1080 × 1350 pixels (4:5). Use the 2160 × 2700
PNG for upload; the smaller PNG provides a feed-size preview. A PDF is also included.

Regenerate from the verified CSV without Snowflake access:

```bash
uv run python scripts/render_linkedin.py
```

The chart shows every daily value, with common temperature axes across stations.
The shaded, dashed section starts October 29, 2026; future actuals remain null.
Metrics are computed from the same 903 observed station-days as the original run.
It uses Avenir Next when installed and DejaVu Sans otherwise.

Suggested alt text:

> Three stacked charts show daily 2026 temperatures for Helsinki Kaisaniemi,
> Kumpula, and Harmaja. Blue lines show FMI observations through October 28;
> peach lines show Kumo predictions. Shaded areas and dashed peach lines mark
> recursive predictions through December, with no future actuals. Kumo misses
> the winter cold. Across 903 observed station-days, its mean absolute error
> is 3.09°C, compared with 1.45°C for yesterday's-temperature baseline.

Data: © Finnish Meteorological Institute, CC BY 4.0. Model output: SnowKumo run
`7A2528115440`, October 29, 2026. The chart is an archival experiment, with no
measured future accuracy or calibrated uncertainty intervals.
