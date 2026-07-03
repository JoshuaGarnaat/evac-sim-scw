from __future__ import annotations

import math


def reached(agent, x: float, y: float, tolerance: float) -> bool:
    return math.hypot(agent.x - x, agent.y - y) <= tolerance
