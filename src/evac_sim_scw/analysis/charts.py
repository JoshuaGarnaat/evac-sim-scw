from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _read(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _chart(output: Path, name: str, title: str, x, series: list[tuple[str, list[float]]], ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 5.2), layout="constrained")
    for label, values in series:
        ax.plot(x, values, label=label, linewidth=1.8)
    ax.set(title=title, xlabel="Time (s)", ylabel=ylabel)
    ax.grid(alpha=0.25)
    if len(series) > 1:
        ax.legend()
    png = output / f"{name}.png"
    fig.savefig(png, dpi=145)
    plt.close(fig)


def generate_charts(result_dir: str | Path) -> Path:
    result = Path(result_dir)
    rows = _read(result / "time_series_metrics.csv")
    output = result / "charts"
    output.mkdir(exist_ok=True)
    t = [float(r["time"]) for r in rows]
    specs = [
        ("evacuation_curve", "Evacuation completion", [("Evacuated", [float(r["evacuated"]) for r in rows])], "People"),
        ("speed_over_time", "Mean level-ground speed", [("Speed", [float(r["mean_speed"]) for r in rows])], "m/s"),
        ("stair_speed_over_time", "Mean preferred stair speed of stair occupants", [("Stair speed", [float(r["mean_stair_speed"]) for r in rows])], "m/s"),
        ("density_over_time", "Density over time", [("Mean", [float(r["mean_density"]) for r in rows]), ("Maximum", [float(r["max_density"]) for r in rows])], "people/m²"),
        ("stair_density_over_time", "Stair density", [("Stairs", [float(r["stair_density"]) for r in rows])], "people/m²"),
        ("congestion_hotspots", "Peak density and pressure", [("Density", [float(r["max_density"]) for r in rows]), ("Pressure indicator", [float(r["peak_pressure"]) for r in rows])], "Indicator"),
    ]
    for name, title, series, ylabel in specs:
        _chart(output, name, title, t, series, ylabel)
    return output
