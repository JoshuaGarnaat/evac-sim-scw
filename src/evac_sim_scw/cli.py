from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .logging_setup import configure_logging


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

    if args.mode == "batch":
        from .config_loader import load_config
        return
    parser().error("choose --mode batch/replay, or provide --analyze RESULT_DIR")
