from __future__ import annotations


def density_speed_factor(density: float, config: dict, stairs: bool = False) -> float:
    values = config["stair_congestion"] if stairs else config["congestion"]
    free = values["free_density"]
    jam = values["jam_density"]
    if density <= free:
        return 1.0
    if density >= jam:
        return values["minimum_speed_factor"]
    fraction = (density - free) / (jam - free)
    return max(values["minimum_speed_factor"], 1.0 - fraction * (1.0 - values["minimum_speed_factor"]))


def classify_state(agent, config: dict) -> str:
    if agent.on_stair:
        return "on_stairs"
    if agent.local_density >= config["congestion"]["congested_density"]:
        return "congested"
    if agent.queue_entered is not None:
        return "queued"
    return "evacuating"
