"""Export verified Snowflake results and an explicitly labelled annual chart."""

import argparse
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from load_data import sql

ROOT = Path(__file__).resolve().parent
NAMES = {"100971": "Kaisaniemi", "101004": "Kumpula", "100996": "Harmaja"}


def export(connection: str, table: str) -> None:
    """Read a bounded annual result and save the values and four-panel chart."""
    if not re.fullmatch(r"BASELINE_CALENDAR|PREDICTIONS_2026_[0-9A-F]{12}", table):
        raise ValueError("Expected BASELINE_CALENDAR or a run-specific prediction table")
    baseline = table == "BASELINE_CALENDAR"
    name = "helsinki_2026_baseline" if baseline else "helsinki_2026_kumo"
    frame = pd.DataFrame(
        sql(
            connection,
            f"SELECT * FROM HELSINKI_WEATHER_LAB.KUMO_2026.{table} "
            "ORDER BY PREDICTION_DATE, STATION_ID LIMIT 2000",
        )
    )
    frame["STATION_ID"] = frame["STATION_ID"].astype(str)
    frame["PREDICTION_DATE"] = pd.to_datetime(frame["PREDICTION_DATE"])
    assert len(frame) == 1095
    assert not frame.duplicated(["STATION_ID", "PREDICTION_DATE"]).any()
    assert frame.loc[frame.PHASE == "FUTURE_RECURSIVE", "ACTUAL_C"].isna().all()
    frame.to_csv(ROOT / f"{name}.csv", index=False)
    history = pd.DataFrame(
        sql(
            connection,
            "SELECT STATION_ID, OBS_DATE, TEMP_C FROM "
            "HELSINKI_WEATHER_LAB.KUMO_2026.OBSERVATIONS "
            "WHERE YEAR(OBS_DATE)=2025 ORDER BY OBS_DATE, STATION_ID LIMIT 1100",
        )
    )
    assert len(history) == 1095
    history["OBS_DATE"] = pd.to_datetime(history["OBS_DATE"])
    history.to_csv(ROOT / "helsinki_2025_observations.csv", index=False)
    fig, axes = plt.subplots(4, 1, figsize=(13, 12), layout="constrained")
    for station, rows in history.groupby("STATION_ID"):
        axes[0].plot(rows.OBS_DATE, rows.TEMP_C, label=NAMES[str(station)], linewidth=0.8)
    axes[0].set(
        title="2025 · complete FMI observed history",
        ylabel="°C",
        xlim=(pd.Timestamp("2025-01-01"), pd.Timestamp("2025-12-31")),
    )
    axes[0].legend(loc="upper right", ncol=3)
    column = "BASELINE_C" if baseline else "PREDICTION_C"
    for ax, (station, rows) in zip(axes[1:], frame.groupby("STATION_ID"), strict=True):
        past = rows[rows.PHASE == "ROLLING_ACTUAL_HISTORY"]
        future = rows[rows.PHASE == "FUTURE_RECURSIVE"]
        ax.plot(past.PREDICTION_DATE, past.ACTUAL_C, label="FMI actual", color="#184e77", lw=1)
        ax.plot(
            past.PREDICTION_DATE,
            past[column],
            color="#c45d17",
            lw=0.85,
            alpha=0.8,
            label="Yesterday baseline" if baseline else "Daily Kumo prediction",
        )
        ax.plot(
            future.PREDICTION_DATE,
            future[column],
            color="#c45d17",
            linestyle="--",
            lw=1.1,
            label="Same day in 2025 baseline" if baseline else "Recursive Kumo prediction",
        )
        ax.axvspan(
            pd.Timestamp("2026-11-01"), pd.Timestamp("2026-12-31"), color="#f5d18e", alpha=0.25
        )
        ax.axvline(pd.Timestamp("2026-10-28"), color="grey", linestyle=":", linewidth=0.8)
        ax.set(
            title=f"2026 · {NAMES[str(station)]}",
            ylabel="°C",
            xlim=(pd.Timestamp("2026-01-01"), pd.Timestamp("2026-12-31")),
        )
        ax.legend(loc="upper left", ncol=3, fontsize=8)
    for ax in axes:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.grid(axis="y", alpha=0.2)
    label = "BASELINES ONLY · Kumo results not included" if baseline else "Kumo GNN experiment"
    if not baseline:
        paired = frame[frame.PHASE == "ROLLING_ACTUAL_HISTORY"].dropna(
            subset=["ACTUAL_C", "PREDICTION_C", "PERSISTENCE_C"]
        )
        mae = (paired.PREDICTION_C - paired.ACTUAL_C).abs().mean()
        persistence_mae = (paired.PERSISTENCE_C - paired.ACTUAL_C).abs().mean()
        label = f"Kumo MAE {mae:.2f}°C · yesterday baseline {persistence_mae:.2f}°C"
    fig.suptitle(f"Helsinki daily mean temperature\n{label}", fontsize=16)
    axes[-1].set_xlabel(
        "Actuals through 28 October 2026 · shaded November/December: predictions only\n"
        "FMI © Finnish Meteorological Institute · CC BY 4.0 · archival experiment"
    )
    fig.savefig(ROOT / f"{name}.png", dpi=150)
    plt.close(fig)
    print(f"Exported {len(frame)} annual rows to {ROOT / name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection", required=True)
    parser.add_argument("--table", default="BASELINE_CALENDAR")
    args = parser.parse_args()
    export(args.connection, args.table)
