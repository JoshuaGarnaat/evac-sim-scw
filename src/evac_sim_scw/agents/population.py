from __future__ import annotations

import math
import numpy as np

from .agent import Agent


def _clipped_normal(rng, spec: dict, count: int) -> np.ndarray:
    values = rng.normal(spec["mean"], spec["std"], count)
    return np.clip(values, spec["min"], spec["max"])

# Create a population based on the configuration
def create_population(building, config: dict) -> list[Agent]:
    population = config["population"]
    movement = config["movement"]
    rng = np.random.default_rng(config["scenario"]["random_seed"])
    count = int(population["count"])
    rooms = [r for r in building.rooms if r.kind == "classroom"]
    ages = rng.integers(population["age_min"], population["age_max"] + 1, count)
    speeds = _clipped_normal(rng, movement["walking_speed"], count)
    reactions = _clipped_normal(rng, movement["reaction_time"], count)
    radii = _clipped_normal(rng, movement["body_radius"], count)
    accelerations = _clipped_normal(rng, movement["max_acceleration"], count)
    spaces = _clipped_normal(rng, movement["personal_space"], count)
    agents: list[Agent] = []
    for i in range(count):
        room = rooms[i % len(rooms)]
        slot = i // len(rooms)
        columns = max(2, int((room.width - 1.0) / 0.75))
        row, column = divmod(slot, columns)
        local_x = 0.7 + column * 0.75
        local_y = 0.7 + row * 0.72
        if local_y > room.depth - 0.7:
            local_y = 0.7 + (slot % max(1, int((room.depth - 1.4) / 0.72))) * 0.72
        x, y = room.local_to_world(
            local_x + rng.uniform(-0.08, 0.08),
            local_y + rng.uniform(-0.08, 0.08),
        )
        agents.append(Agent(
            id=i, age=int(ages[i]), classroom_id=room.id, group_id=room.id,
            floor=room.floor, x=x, y=y, z=room.floor * building.floor_height,
            radius=float(radii[i]), preferred_speed=float(speeds[i]),
            max_speed=float(speeds[i] * movement["maximum_speed_multiplier"]),
            reaction_time=float(reactions[i]), max_acceleration=float(accelerations[i]),
            personal_space=float(spaces[i]),
            meta={"route_bias": float(rng.normal(0.0, config["route_choice"]["randomness_std"]))},
        ))
    return agents
