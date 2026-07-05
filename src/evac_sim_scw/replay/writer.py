from __future__ import annotations

import json
from pathlib import Path
import time

from ..io.json_writer import write_json


STATE_CODES = {
    "waiting": 0, "evacuating": 1, "queued": 2, "congested": 3,
    "on_stairs": 4, "entering_stairwell": 5, "leaving_stairwell": 6,
    "rerouting": 7, "exited": 8,
}


class ReplayWriter:
    def __init__(self, output_dir: Path, building, config: dict):
        self.path = output_dir / "replay.jsonl"
        self.metadata_path = output_dir / "replay_metadata.json"
        self.handle = self.path.open("w", encoding="utf-8", buffering=1024 * 1024)
        self.frame_count = 0
        self.last_timestamp = -1.0
        self.started = time.perf_counter()
        self.metadata = {
            "format": "evac_sim_scw-1", "building_layout_reference": str(building.path),
            "building": building.serializable(), "population": config["population"]["count"],
            "simulation_dt": config["simulation"]["dt"],
            "sample_interval": config["simulation"]["replay_sample_interval"],
            "interpolation": config["replay"]["interpolation"],
            "state_codes": STATE_CODES,
        }

    def write_frame(self, timestamp: float, agents, evacuated: int) -> None:
        packed = []
        for a in agents:
            stair = a.selected_stair if a.on_stair else None
            packed.append([
                a.id, round(a.x, 3), round(a.y, 3), round(a.z, 3), a.floor,
                STATE_CODES[a.state], round(a.speed, 3), round(a.local_density, 3), stair,
            ])
        frame = {"t": round(timestamp, 3), "e": evacuated, "r": len(agents) - evacuated, "a": packed}
        self.handle.write(json.dumps(frame, separators=(",", ":")) + "\n")
        self.frame_count += 1
        self.last_timestamp = timestamp

    def close(self) -> dict:
        self.handle.close()
        elapsed = time.perf_counter() - self.started
        self.metadata.update({
            "frame_count": self.frame_count,
            "replay_generation_seconds": round(elapsed, 3),
            "file_size_bytes": self.path.stat().st_size,
            "recommended_playback": "1x; use 2x or 4x for long full-population runs",
        })
        write_json(self.metadata_path, self.metadata)
        return self.metadata
