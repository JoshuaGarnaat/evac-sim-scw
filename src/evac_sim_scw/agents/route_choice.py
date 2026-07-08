from __future__ import annotations

from ..geometry.nav_graph import Route, route_cost

# Cost based route finding
def choose_route(agent, building, queues: dict[str, int], config: dict) -> Route:
    candidates: list[Route] = []
    stairs = building.stairs if agent.floor > 0 else [None]
    for stair in stairs:
        for exit_door in building.exits:
            cost = route_cost(agent, exit_door, stair, queues, config)
            bias = agent.meta["route_bias"] * (1 + ((agent.id * 17 + len(candidates) * 13) % 7) / 7)
            candidates.append(Route(exit_door.id, stair.id if stair else None, cost + bias))
    return min(candidates, key=lambda route: route.estimated_cost)
