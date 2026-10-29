"""Render a portrait LinkedIn figure from the verified prediction snapshot."""

from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "social"
BG = "#081724"
PANEL = "#102536"
TEXT = "#F4F7F9"
MUTED = "#A8BDC9"
ACTUAL = "#72D5EF"
KUMO = "#FFAB78"
GREEN = "#B6E5AE"


def render() -> None:
    """Save a 4:5 data graphic at feed and high-resolution sizes."""
    source = ROOT / "results/2026-10-29/helsinki_2026_kumo.csv"
    frame = pd.read_csv(source, dtype={"STATION_ID": str}, parse_dates=["PREDICTION_DATE"])
    rolling = frame[frame.PHASE == "ROLLING_ACTUAL_HISTORY"]
    future = frame[frame.PHASE == "FUTURE_RECURSIVE"]
    assert len(frame) == 1095 and len(rolling) == 903 and len(future) == 192
    assert future.ACTUAL_C.isna().all()
    mae = float((rolling.PREDICTION_C - rolling.ACTUAL_C).abs().mean())
    baseline = float((rolling.PERSISTENCE_C - rolling.ACTUAL_C).abs().mean())
    available = {font.name for font in font_manager.fontManager.ttflist}
    family = "Avenir Next" if "Avenir Next" in available else "DejaVu Sans"
    plt.rcParams.update({"font.family": family, "svg.fonttype": "none", "pdf.fonttype": 42})
    fig = plt.figure(figsize=(10.8, 13.5), facecolor=BG)

    def text(x, y, value, size=12, color=TEXT, weight="normal", **kwargs):
        fig.text(
            x / 1080,
            1 - y / 1350,
            value,
            fontsize=size,
            color=color,
            fontweight=weight,
            va="top",
            **kwargs,
        )

    def card(x, y, width, height, color=PANEL, radius=14):
        fig.add_artist(
            FancyBboxPatch(
                (x / 1080, 1 - (y + height) / 1350),
                width / 1080,
                height / 1350,
                boxstyle=f"round,pad=0,rounding_size={radius / 1080}",
                transform=fig.transFigure,
                facecolor=color,
                edgecolor="none",
                zorder=0,
            )
        )

    card(56, 52, 7, 20, ACTUAL, 2)
    text(77, 52, "SNOWKUMO  /  EXPERIMENT 01", 12, MUTED, "bold")
    text(1024, 52, "2026", 12, MUTED, "bold", ha="right")
    text(56, 99, "Helsinki, predicted.", 43, TEXT, "bold")
    text(58, 171, "NVIDIA Kumo + Snowflake", 23, TEXT)
    text(58, 218, "3 stations  ·  365 days  ·  1,095 predictions", 15, MUTED)

    # A shared legend applies to all three daily-series panels.
    legend = fig.add_axes((0.053, 1 - 295 / 1350, 0.9, 0.035), facecolor="none")
    legend.set_axis_off()
    handles = [
        Line2D([0], [0], color=ACTUAL, lw=2),
        Line2D([0], [0], color=KUMO, lw=2),
        Line2D([0], [0], color=KUMO, lw=2, linestyle=(0, (4, 3))),
    ]
    legend.legend(
        handles,
        ["FMI actual", "Kumo daily prediction", "Recursive future"],
        loc="center left",
        ncol=3,
        frameon=False,
        labelcolor=TEXT,
        fontsize=12,
        handlelength=2.2,
        columnspacing=2.1,
        borderaxespad=0,
    )

    names = [("100971", "Kaisaniemi"), ("101004", "Kumpula"), ("100996", "Harmaja")]
    cutoff = datetime(2026, 10, 29)
    start, end = datetime(2026, 1, 1), datetime(2026, 12, 31)
    for index, (station, name) in enumerate(names):
        top = 312 + 219 * index
        card(56, top, 968, 204)
        text(78, top + 14, name, 16, TEXT, "bold")
        text(998, top + 16, "DAILY MEAN / °C", 10, MUTED, ha="right")
        ax = fig.add_axes(
            (106 / 1080, 1 - (top + 165) / 1350, 885 / 1080, 110 / 1350), facecolor=PANEL
        )
        data = frame[frame.STATION_ID == station].sort_values("PREDICTION_DATE")
        observed = data[data.PHASE == "ROLLING_ACTUAL_HISTORY"]
        forecast = data[data.PHASE == "FUTURE_RECURSIVE"]
        ax.axvspan(
            float(mdates.date2num(cutoff)),
            float(mdates.date2num(end)),
            color=KUMO,
            alpha=0.07,
            lw=0,
        )
        ax.axvline(
            float(mdates.date2num(cutoff)), color=KUMO, alpha=0.5, lw=0.8, linestyle=(0, (2, 3))
        )
        ax.plot(observed.PREDICTION_DATE, observed.ACTUAL_C, color=ACTUAL, lw=1.25)
        ax.plot(observed.PREDICTION_DATE, observed.PREDICTION_C, color=KUMO, lw=1.35, alpha=0.96)
        ax.plot(
            forecast.PREDICTION_DATE,
            forecast.PREDICTION_C,
            color=KUMO,
            lw=1.8,
            linestyle=(0, (4, 2.7)),
        )
        ax.set(xlim=(start, end), ylim=(-25, 27), yticks=[-20, 0, 20])
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 3, 5, 7, 9, 11]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.tick_params(axis="both", colors=MUTED, labelsize=14, length=0, pad=7)
        ax.grid(axis="y", color="white", alpha=0.1, lw=0.6)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.text(
            0.987,
            0.96,
            "Forecast only",
            transform=ax.transAxes,
            color=KUMO,
            fontsize=14,
            ha="right",
            va="top",
            linespacing=1.2,
        )

    text(58, 978, "Actuals through 28 Oct.  Nov–Dec: predictions only.", 17.5, MUTED)
    card(56, 1020, 968, 164, "#162B38")
    text(79, 1040, "THE BASELINE WINS", 12, GREEN, "bold")
    text(79, 1072, "Average absolute error", 14, TEXT)
    text(79, 1102, "Same 903 observed station-days", 11, MUTED)
    text(79, 1137, "A working workflow. More model work ahead.", 10.5, MUTED)
    text(608, 1041, "KUMO", 11, KUMO, "bold")
    text(603, 1070, f"{mae:.2f}°", 35, KUMO, "bold")
    text(608, 1135, "Celsius", 10.5, MUTED)
    text(811, 1041, "YESTERDAY", 11, GREEN, "bold")
    text(806, 1070, f"{baseline:.2f}°", 35, GREEN, "bold")
    text(811, 1135, "Celsius", 10.5, MUTED)

    text(58, 1208, "3-epoch archival experiment · Future accuracy unmeasured", 17.5, MUTED)
    text(58, 1249, "© Finnish Meteorological Institute · CC BY 4.0 · Run 29 Oct 2026", 12.5, MUTED)
    text(58, 1291, "FULL WALKTHROUGH ON MEDIUM", 11, TEXT, "bold")
    text(1024, 1291, "github.com/MiguelElGallo/SnowKumo", 10, MUTED, ha="right")

    OUTPUT.mkdir(exist_ok=True)
    for dpi, suffix in [(100, "1080x1350"), (200, "2160x2700")]:
        fig.savefig(OUTPUT / f"snowkumo-linkedin-{suffix}.png", dpi=dpi, facecolor=BG)
    fig.savefig(OUTPUT / "snowkumo-linkedin.pdf", facecolor=BG)
    plt.close(fig)
    print(f"Saved LinkedIn graphics to {OUTPUT}; verified MAE {mae:.4f} vs {baseline:.4f}°C")


if __name__ == "__main__":
    render()
