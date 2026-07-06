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
    result = argparse.ArgumentParser(prog="evac-sim", description="Run and inspect evacuation simulations")
    result.add_argument("--verbose", action="store_true", help="Enable debug logging")
    commands = result.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Run a simulation")
    run.add_argument("config", metavar="SCENARIO", help="Scenario YAML file")

    replay = commands.add_parser("replay", help="Open a simulation replay")
    replay.add_argument("result", metavar="RESULT", help="Result directory or replay JSONL file")
    replay.add_argument("--host", default="127.0.0.1")
    replay.add_argument("--port", type=int, default=8765)
    replay.add_argument("--no-browser", action="store_true")

    analyze = commands.add_parser("analyze", help="Generate charts from simulation results")
    analyze.add_argument("result", metavar="RESULT_DIR", help="Result directory")
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    configure_logging(args.verbose)
    if args.command == "analyze":
        from .analysis.charts import generate_charts

        result = _latest(args.result)
        charts = generate_charts(result)
        logging.info("Charts written to %s", charts)
        return
    if args.command == "run":
        from .analysis.charts import generate_charts
        from .config_loader import load_config
        from .simulation.engine import SimulationEngine

        output = SimulationEngine(load_config(args.config)).run()
        generate_charts(output)
        return
    if args.command == "replay":
        from .visualization.server import serve_replay

        replay = _latest(args.result)
        if replay.is_dir():
            replay /= "replay.jsonl"
        serve_replay(replay, args.host, args.port, not args.no_browser)
        return
