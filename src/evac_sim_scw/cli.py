from __future__ import annotations

import argparse
import logging
from pathlib import Path


def configure_logging(verbose: bool = False) -> None:
    """Configure the command-line logging format and verbosity."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _latest(path_value: str) -> Path:
    """Replace a ``latest`` path component using the output marker file."""
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
    """Build the command-line parser and its subcommands."""
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

    view = commands.add_parser("view-floorplan", help="Open a floorplan in the 3D viewer without running a simulation")
    view.add_argument("floorplan", metavar="FLOORPLAN", help="School building floorplan JSON file")
    view.add_argument("--host", default="127.0.0.1")
    view.add_argument("--port", type=int, default=8765)
    view.add_argument("--no-browser", action="store_true")

    validate = commands.add_parser("validate-floorplan", help="Validate and summarize a floorplan JSON file")
    validate.add_argument("floorplan", metavar="FLOORPLAN", help="Floorplan JSON file")
    return result


def main(argv: list[str] | None = None) -> None:
    """Dispatch the requested command-line action."""
    args = parser().parse_args(argv)
    configure_logging(args.verbose)
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
    if args.command == "view-floorplan":
        from .visualization.server import serve_floorplan

        serve_floorplan(args.floorplan, args.host, args.port, not args.no_browser)
        return
