from __future__ import annotations

import math


def update_local_density(agents, grid, radius: float) -> None:
    area = math.pi * radius * radius
    for agent in agents:
        if agent.state == "exited" or agent.on_stair:
            continue
        count = 0
        for index in grid.neighbors(agent.floor, agent.x, agent.y):
            other = agents[index]
            if other.id != agent.id and math.hypot(agent.x - other.x, agent.y - other.y) <= radius:
                count += 1
        agent.local_density = count / area
