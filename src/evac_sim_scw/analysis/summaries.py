from __future__ import annotations

import csv
from pathlib import Path


def read_summary(result_dir: str | Path) -> dict[str, str]:
    """Read the single metrics row from a result directory."""
    with (Path(result_dir) / "metrics_summary.csv").open("r", encoding="utf-8") as handle:
        return next(csv.DictReader(handle))
