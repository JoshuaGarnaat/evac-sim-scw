from __future__ import annotations

from collections import Counter, defaultdict
import math
from pathlib import Path

from ..io.csv_writer import write_rows


class MetricsCollector:
    def __init__(self):
        self.time_series: list[dict] = []
        self.exit_events: list[dict] = []
        self.door_events: list[dict] = []
        self.stair_events: list[dict] = []
        self.hotspots: list[dict] = []
        self.step_times: list[float] = []

    def sample(self, timestamp: float, agents, building, stair_occupancy: dict, stair_queues: dict) -> None:
        active = [a for a in agents if a.state != "exited"]
        speeds = [a.speed for a in active]
        densities = [a.local_density for a in active]
        stair_agents = [a for a in active if a.on_stair]
        floor_density = Counter(a.floor for a in active if not a.on_stair)
        floor_area = building.width * building.depth
        peak = max(active, key=lambda a: a.local_density, default=None)
        queues = sum(1 for a in active if a.state == "queued")
        self.time_series.append({
            "time": round(timestamp, 3), "evacuated": len(agents) - len(active), "remaining": len(active),
            "mean_speed": _mean(speeds), "min_speed": min(speeds, default=0.0), "max_speed": max(speeds, default=0.0),
            "mean_stair_speed": _mean([a.current_stair_speed for a in stair_agents]),
            "mean_density": _mean(densities), "min_density": min(densities, default=0.0), "max_density": max(densities, default=0.0),
            "floor_0_density": floor_density[0] / floor_area, "floor_1_density": floor_density[1] / floor_area,
            "floor_2_density": floor_density[2] / floor_area,
            "stair_density": _mean([a.local_density for a in stair_agents]),
            "queue_length": queues, "stair_queue_length": sum(stair_queues.values()),
            "peak_density_location": "" if peak is None else f"floor={peak.floor};x={peak.x:.2f};y={peak.y:.2f}",
            "peak_pressure": max((a.pressure for a in active), default=0.0),
        })
        if peak is not None:
            self.hotspots.append({"time": round(timestamp, 3), "floor": peak.floor, "x": round(peak.x, 2), "y": round(peak.y, 2), "density": round(peak.local_density, 3), "pressure": round(peak.pressure, 3)})

    def record_exit(self, timestamp: float, exit_id: str, agent_id: int) -> None:
        self.exit_events.append({"time": round(timestamp, 3), "exit_id": exit_id, "agent_id": agent_id})

    def record_door(self, timestamp: float, door_id: str, agent_id: int) -> None:
        self.door_events.append({"time": round(timestamp, 3), "door_id": door_id, "agent_id": agent_id})

    def record_stair(self, timestamp: float, stair_id: str, floor: int, event: str, agent_id: int) -> None:
        self.stair_events.append({"time": round(timestamp, 3), "stair_id": stair_id, "floor": floor, "event": event, "agent_id": agent_id})

    def export(self, output: Path, agents, replay_meta: dict, total_time: float) -> None:
        evac_times = [a.evacuation_time for a in agents if a.evacuation_time is not None]
        all_speeds = [a.speed_sum / max(a.speed_samples, 1) for a in agents]
        summary = [{
            "total_evacuation_time": round(total_time, 3), "average_evacuation_time": _mean(evac_times),
            "minimum_evacuation_time": min(evac_times, default=0.0), "maximum_evacuation_time": max(evac_times, default=0.0),
            "mean_agent_speed": _mean(all_speeds), "minimum_agent_mean_speed": min(all_speeds, default=0.0),
            "maximum_agent_mean_speed": max(all_speeds, default=0.0), "number_of_reroutes": sum(a.reroutes for a in agents),
            "mean_simulation_step_ms": 1000 * _mean(self.step_times), "max_simulation_step_ms": 1000 * max(self.step_times, default=0.0),
            "replay_generation_time": replay_meta["replay_generation_seconds"], "replay_frame_count": replay_meta["frame_count"],
            "replay_file_size_bytes": replay_meta["file_size_bytes"], "recommended_playback_settings": replay_meta["recommended_playback"],
        }]
        per_agent = [{
            "agent_id": a.id, "age": a.age, "classroom_id": a.classroom_id, "selected_exit": a.selected_exit,
            "evacuation_time": a.evacuation_time, "mean_speed": a.speed_sum / max(a.speed_samples, 1),
            "minimum_speed": 0.0, "maximum_speed": a.max_speed, "time_congested": round(a.congested_time, 3),
            "time_on_stairs": round(a.stair_time, 3), "reroutes": a.reroutes,
        } for a in agents]
        write_rows(output / "metrics_summary.csv", summary)
        write_rows(output / "per_agent_metrics.csv", per_agent)
        write_rows(output / "time_series_metrics.csv", self.time_series)
        write_rows(output / "door_throughput.csv", _bin_events(self.door_events, "door_id"))
        write_rows(output / "stair_throughput.csv", _bin_events(self.stair_events, "stair_id"))
        write_rows(output / "density_grid.csv", self.hotspots)


def _mean(values) -> float:
    return round(sum(values) / len(values), 5) if values else 0.0


def _bin_events(events: list[dict], key: str) -> list[dict]:
    counts = defaultdict(int)
    for event in events:
        counts[(math.floor(event["time"]), event[key])] += 1
    return [{"time_bin": t, key: identifier, "throughput": value} for (t, identifier), value in sorted(counts.items())]
