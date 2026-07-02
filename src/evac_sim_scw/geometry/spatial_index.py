from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
import math


class SpatialGrid:
    def __init__(self, cell_size: float):
        self.cell_size = cell_size
        self.cells: dict[tuple[int, int, int], list[int]] = defaultdict(list)

    def rebuild(self, agents: Iterable) -> None:
        self.cells.clear()
        for agent in agents:
            if agent.state == "exited" or agent.on_stair:
                continue
            self.cells[self.key(agent.floor, agent.x, agent.y)].append(agent.id)

    def key(self, floor: int, x: float, y: float) -> tuple[int, int, int]:
        return floor, math.floor(x / self.cell_size), math.floor(y / self.cell_size)

    def neighbors(self, floor: int, x: float, y: float) -> list[int]:
        floor_id, cx, cy = self.key(floor, x, y)
        result: list[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                result.extend(self.cells.get((floor_id, cx + dx, cy + dy), ()))
        return result
