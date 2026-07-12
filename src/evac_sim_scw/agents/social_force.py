from __future__ import annotations

import math
from types import SimpleNamespace

from ..geometry.layout_schema import rotate

#
# Force models
#

def movement_force(agent, target_x: float, target_y: float, desired_speed: float, neighbors, config: dict) -> tuple[float, float]:
    """Calculate desired-motion and pedestrian-repulsion acceleration."""
    dx, dy = target_x - agent.x, target_y - agent.y
    distance = max(math.hypot(dx, dy), 1e-6)
    tau = config["relaxation_time"]
    fx = (desired_speed * dx / distance - agent.vx) / tau
    fy = (desired_speed * dy / distance - agent.vy) / tau
    strength = config["pedestrian_repulsion_strength"]
    decay = config["pedestrian_repulsion_range"]
    contact_k = config["contact_stiffness"]
    for other in neighbors:
        if other.id == agent.id or other.state == "exited":
            continue
        rx, ry = agent.x - other.x, agent.y - other.y
        d = max(math.hypot(rx, ry), 0.05)
        nx, ny = rx / d, ry / d
        preferred = agent.radius + other.radius + 0.5 * agent.personal_space
        # Repulsion grows smoothly before contact, then stiffens if bodies overlap.
        repulsion = strength * math.exp((preferred - d) / decay)
        overlap = max(0.0, agent.radius + other.radius - d)
        fx += (repulsion + contact_k * overlap) * nx
        fy += (repulsion + contact_k * overlap) * ny
        closing = (agent.vx - other.vx) * nx + (agent.vy - other.vy) * ny
        if closing < 0 and d < preferred * 1.8:
            # Start steering away when the two agents are still approaching each other.
            fx -= config["predictive_avoidance"] * closing * nx
            fy -= config["predictive_avoidance"] * closing * ny
    magnitude = math.hypot(fx, fy)
    if magnitude > agent.max_acceleration:
        scale = agent.max_acceleration / magnitude
        fx *= scale
        fy *= scale
    return fx, fy


def rectangular_wall_force(agent, bounds: tuple[float, float, float, float], openings: list[tuple[str, float, float]], config: dict) -> tuple[float, float]:
    """Calculate wall repulsion for an axis-aligned rectangle with openings."""
    xmin, xmax, ymin, ymax = bounds
    strength = config["wall_repulsion_strength"]
    decay = config["wall_repulsion_range"]
    fx = fy = 0.0

    def is_open(side: str, coordinate: float) -> bool:
        """Return whether a wall coordinate falls within an opening."""
        return any(item_side == side and abs(coordinate - center) <= width / 2 for item_side, center, width in openings)

    if not is_open("west", agent.y):
        fx += strength * math.exp((agent.radius - (agent.x - xmin)) / decay)
    if not is_open("east", agent.y):
        fx -= strength * math.exp((agent.radius - (xmax - agent.x)) / decay)
    if not is_open("south", agent.x):
        fy += strength * math.exp((agent.radius - (agent.y - ymin)) / decay)
    if not is_open("north", agent.x):
        fy -= strength * math.exp((agent.radius - (ymax - agent.y)) / decay)
    return fx, fy


def oriented_rectangular_wall_force(agent, rect, openings, config: dict) -> tuple[float, float]:
    """Evaluate the existing wall model in an oriented rectangle's local frame."""
    x, y = rect.world_to_local(agent.x, agent.y)
    local_agent = SimpleNamespace(x=x, y=y, radius=agent.radius)
    fx, fy = rectangular_wall_force(
        local_agent, (0.0, rect.width, 0.0, rect.depth), openings, config,
    )
    return rotate(fx, fy, rect.rotation)
