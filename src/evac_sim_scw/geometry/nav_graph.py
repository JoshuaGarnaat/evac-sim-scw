from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(slots=True)
class Route:
    exit_id: str
    stair_id: str | None
    estimated_cost: float


def route_cost(agent, exit_door, stair, queues: dict[str, int], config: dict) -> float:
    route = config["route_choice"]
    if agent.floor > 0 and stair is not None:
        horizontal = abs(agent.x - stair.x) + abs(stair.x - exit_door.x)
        stair_cost = agent.floor * stair.path_length * route["stair_cost_multiplier"]
        queue = queues.get(stair.id, 0) / max(stair.width, 0.1)
    else:
        horizontal = math.hypot(agent.x - exit_door.x, agent.y - exit_door.y)
        stair_cost = 0.0
        queue = 0.0
    width_penalty = route["width_penalty"] / max(exit_door.width, 0.1)
    return horizontal + stair_cost + route["queue_cost"] * queue + width_penalty
