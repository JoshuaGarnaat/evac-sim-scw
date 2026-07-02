from __future__ import annotations

import math


def separate(agent, neighbors, max_correction: float = 0.04) -> tuple[float, float]:
    cx = cy = 0.0
    for other in neighbors:
        if other.id == agent.id or other.state == "exited" or other.on_stair:
            continue
        dx, dy = agent.x - other.x, agent.y - other.y
        distance = max(math.hypot(dx, dy), 1e-5)
        overlap = agent.radius + other.radius - distance
        if overlap > 0:
            correction = min(max_correction, overlap * 0.5)
            cx += correction * dx / distance
            cy += correction * dy / distance
    return cx, cy
