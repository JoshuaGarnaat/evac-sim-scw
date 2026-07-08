from __future__ import annotations

import math


def separate(agent, neighbors, max_correction: float = 0.04) -> tuple[float, float]:
    cx = cy = 0.0
    for other in neighbors:
        if other.id == agent.id or other.state == "exited":
            continue
        dx, dy = agent.x - other.x, agent.y - other.y
        distance = math.hypot(dx, dy)
        overlap = agent.radius + other.radius - distance
        if overlap > 0:
            correction = min(max_correction, overlap * 0.5)
            if distance < 1e-5:
                # Resolve coincident agents deterministically to preserve reproducible runs.
                angle = ((agent.id * 37 + other.id * 17) % 360) * math.pi / 180
                nx, ny = math.cos(angle), math.sin(angle)
            else:
                nx, ny = dx / distance, dy / distance
            cx += correction * nx
            cy += correction * ny
    magnitude = math.hypot(cx, cy)
    if magnitude > max_correction:
        cx *= max_correction / magnitude
        cy *= max_correction / magnitude
    return cx, cy
