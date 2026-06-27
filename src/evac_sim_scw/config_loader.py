from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    candidates = [base / path, Path.cwd() / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[-1].resolve()


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    required = {"scenario", "population", "movement", "simulation", "outputs"}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"Missing configuration sections: {sorted(missing)}")
    config["_config_path"] = str(config_path)
    config["building"]["layout_file"] = str(
        _resolve(config_path.parent, config["building"]["layout_file"])
    )
    return config


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)
