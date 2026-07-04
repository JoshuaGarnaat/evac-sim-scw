from __future__ import annotations

from collections import defaultdict
import math

from ..geometry.stairs import stair_position


def stair_lane_count(stair, config: dict) -> int:
    return max(1, int(stair.width / config["stair_congestion"]["lane_width"]))


def advance_stair_groups(agents, building, dt: float, config: dict) -> list:
    finished = []
    values = config["stair_congestion"]
    for stair in building.stairs:
        occupants = [a for a in agents if a.on_stair and a.selected_stair == stair.id]
        if not occupants:
            continue
        density = len(occupants) / max(stair.width * stair.path_length, 0.1)
        if density <= values["free_density"]:
            density_factor = 1.0
        else:
            span = max(values["jam_density"] - values["free_density"], 0.1)
            density_factor = max(
                values["minimum_speed_factor"],
                1.0 - (density - values["free_density"]) / span,
            )
        lane_count = stair_lane_count(stair, config)
        streams = defaultdict(list)
        for agent in occupants:
            streams[(agent.stair_from_floor, agent.stair_lane)].append(agent)
        for stream in streams.values():
            stream.sort(key=lambda a: a.stair_progress, reverse=True)
            leader = None
            for agent in stream:
                agent.state = "on_stairs"
                agent.local_density = density
                desired = agent.stair_down_speed * density_factor
                acceleration = (desired - agent.current_stair_speed) / values["relaxation_time"]
                speed = max(0.0, agent.current_stair_speed + acceleration * dt)
                if leader is not None:
                    gap = (
                        (leader.stair_progress - agent.stair_progress) * stair.path_length
                        - leader.radius - agent.radius
                    )
                    desired_gap = values["minimum_longitudinal_gap"] + 0.5 * agent.personal_space
                    if gap < desired_gap * 2.0:
                        speed -= values["following_stiffness"] * max(0.0, desired_gap * 2.0 - gap) * dt
                    safe_speed = leader.current_stair_speed + max(0.0, gap - desired_gap) / dt
                    speed = min(speed, safe_speed)
                speed = min(max(0.0, speed), agent.stair_down_speed)
                old_progress = agent.stair_progress
                new_progress = old_progress + speed * dt / stair.path_length
                if leader is not None:
                    minimum_path_gap = leader.radius + agent.radius + values["minimum_longitudinal_gap"]
                    new_progress = min(new_progress, leader.stair_progress - minimum_path_gap / stair.path_length)
                agent.stair_progress = max(old_progress, new_progress)
                agent.current_stair_speed = (agent.stair_progress - old_progress) * stair.path_length / dt
                agent.x, agent.y, agent.z = stair_position(
                    stair, agent.stair_from_floor, agent.stair_progress,
                    building.floor_height, agent.stair_lane, lane_count,
                )
                agent.stair_time += dt
                if agent.stair_progress >= 1.0 - 1e-9:
                    agent.floor -= 1
                    agent.z = agent.floor * building.floor_height
                    agent.on_stair = False
                    agent.current_stair_speed = 0.0
                    agent.state = "leaving_stairwell"
                    agent.phase = "corridor"
                    agent.queue_entered = None
                    finished.append(agent)
                leader = agent
        _separate_stair_occupants(occupants, stair, values)
    return finished


def _separate_stair_occupants(occupants, stair, values: dict) -> None:
    xmin = stair.x - stair.enclosure_width / 2
    xmax = stair.x + stair.enclosure_width / 2
    ymin = stair.y - stair.depth / 2
    ymax = stair.y + stair.depth / 2
    for _ in range(5):
        corrected = False
        for index, first in enumerate(occupants):
            if not first.on_stair:
                continue
            for second in occupants[index + 1:]:
                if not second.on_stair or first.stair_from_floor != second.stair_from_floor:
                    continue
                required = first.radius + second.radius + values["minimum_longitudinal_gap"]
                dz = abs(first.z - second.z)
                if dz >= required:
                    continue
                required_planar = math.sqrt(max(0.0, required * required - dz * dz))
                dx, dy = first.x - second.x, first.y - second.y
                planar = math.hypot(dx, dy)
                if planar >= required_planar:
                    continue
                if planar < 1e-6:
                    angle = ((first.id * 37 + second.id * 17) % 360) * math.pi / 180
                    nx, ny = math.cos(angle), math.sin(angle)
                else:
                    nx, ny = dx / planar, dy / planar
                correction = (required_planar - planar) * 0.52
                first.x += nx * correction
                first.y += ny * correction
                second.x -= nx * correction
                second.y -= ny * correction
                first.x = min(max(first.x, xmin + first.radius), xmax - first.radius)
                second.x = min(max(second.x, xmin + second.radius), xmax - second.radius)
                first.y = min(max(first.y, ymin + first.radius), ymax - first.radius)
                second.y = min(max(second.y, ymin + second.radius), ymax - second.radius)
                corrected = True
        if not corrected:
            break
