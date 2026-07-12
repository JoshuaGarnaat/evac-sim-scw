from __future__ import annotations


def crowd_pressure(agent, config: dict) -> float:
    """Calculate a simple density-and-speed crowd-pressure indicator."""
    threshold = config["crowd_pressure"]["density_threshold"]
    excess = max(0.0, agent.local_density - threshold)
    speed_deficit = max(0.0, agent.preferred_speed - agent.speed)
    return excess * speed_deficit * config["crowd_pressure"]["indicator_scale"]
