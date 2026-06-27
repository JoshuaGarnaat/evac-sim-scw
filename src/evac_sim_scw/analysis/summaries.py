from __future__ import annotations

import csv
from pathlib import Path


def read_summary(result_dir: str | Path) -> dict[str, str]:
    with (Path(result_dir) / "metrics_summary.csv").open("r", encoding="utf-8") as handle:
        return next(csv.DictReader(handle))
