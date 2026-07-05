from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .logging_setup import configure_logging


def _latest(path_value: str) -> Path:
    path = Path(path_value)
    if path.exists() or "latest" not in path.parts:
        return path
    index = path.parts.index("latest")
    root = Path(*path.parts[:index]) if index else Path(".")
    marker = root / "latest.txt"
    if not marker.exists():
        return path
    target = Path(marker.read_text(encoding="utf-8").strip())
    for part in path.parts[index + 1:]:
        target /= part
    return target


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="evac_sim_scw")
    result.add_argument("--mode", choices=("batch", "replay"))
    result.add_argument("--config", default="config/scenario.yaml")
    result.add_argument("--replay", help="Replay JSONL path")
    result.add_argument("--analyze", metavar="RESULT_DIR", help="Generate charts from a result directory")
    result.add_argument("--host", default="127.0.0.1")
    result.add_argument("--port", type=int, default=8765)
    result.add_argument("--no-browser", action="store_true")
    result.add_argument("--verbose", action="store_true")
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    configure_logging(args.verbose)
    if args.analyze:
        from .analysis.charts import generate_charts

        result = _latest(args.analyze)
        charts = generate_charts(result)
        logging.info("Charts written to %s", charts)
        return
    if args.mode == "batch":
        from .analysis.charts import generate_charts
        from .config_loader import load_config
        from .simulation.engine import SimulationEngine

        output = SimulationEngine(load_config(args.config)).run()
        generate_charts(output)
        return
    parser().error("choose --mode batch/replay, or provide --analyze RESULT_DIR")
