from __future__ import annotations

import json
from pathlib import Path


def read_metadata(replay_path: str | Path) -> dict:
    """Read metadata stored alongside a replay stream."""
    path = Path(replay_path)
    with (path.parent / "replay_metadata.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def iter_frames(replay_path: str | Path):
    """Yield decoded replay frames without loading the entire file."""
    with Path(replay_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)
