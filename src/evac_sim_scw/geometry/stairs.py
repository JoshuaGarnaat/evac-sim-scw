from __future__ import annotations

import math


def stair_position(
    stair, from_floor: int, progress: float, floor_height: float,
    lane: int = 0, lane_count: int = 1,
) -> tuple[float, float, float]:
    p = max(0.0, min(1.0, progress))
    top_z = from_floor * floor_height
    entrance_y = stair.y - stair.depth / 2 + 0.50
    landing_y = entrance_y + min(5.9, stair.depth - 1.9)
    lane_offset = stair.enclosure_width * 0.23
    lateral = (lane - (lane_count - 1) / 2) * stair.width / lane_count
    if p < 0.40:
        u = p / 0.40
        x = stair.x - lane_offset + lateral
        y = entrance_y + (landing_y - entrance_y) * u
        z = top_z - floor_height * 0.5 * u
    elif p < 0.60:
        u = (p - 0.40) / 0.10
        angle = math.pi * (1.0 - u)
        radius = lane_offset - lateral
        arc_height = 1.0 - 0.75 * lateral
        x = stair.x + radius * math.cos(angle)
        y = landing_y + arc_height * math.sin(angle)
        z = top_z - floor_height * 0.5
    else:
        u = (p - 0.60) / 0.80
        x = stair.x + lane_offset - lateral
        y = landing_y - (landing_y - entrance_y) * u
        z = top_z - floor_height * (0.5 + 0.5 * u)
    return x, y, z
