from __future__ import annotations


def density_speed_factor(density: float, config: dict) -> float:
    """Convert local crowd density into a bounded walking-speed multiplier."""
    values = config["congestion"]
    free = values["free_density"]
    jam = values["jam_density"]
    if density <= free:
        return 1.0
    if density >= jam:
        return values["minimum_speed_factor"]
    fraction = (density - free) / (jam - free)
    return max(values["minimum_speed_factor"], 1.0 - fraction * (1.0 - values["minimum_speed_factor"]))


def classify_state(agent, config: dict) -> str:
    """Assign the reporting state that best describes an agent's condition."""
    if agent.on_stair:
        return "on_stairs"
    if agent.local_density >= config["congestion"]["congested_density"]:
        return "congested"
    if agent.queue_entered is not None:
        return "queued"
    return "evacuating"
