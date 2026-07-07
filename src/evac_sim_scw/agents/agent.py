from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Agent:
    id: int
    age: int
    classroom_id: str
    group_id: str
    floor: int
    x: float
    y: float
    z: float
    radius: float
    preferred_speed: float
    max_speed: float
    reaction_time: float
    max_acceleration: float
    personal_space: float
    vx: float = 0.0
    vy: float = 0.0
    ax: float = 0.0
    ay: float = 0.0
    state: str = "waiting"
    phase: str = "room"
    target_x: float = 0.0
    target_y: float = 0.0
    selected_exit: str | None = None
    selected_stair: str | None = None
    on_stair: bool = False
    stair_progress: float = 0.0
    stair_from_floor: int = 0
    local_density: float = 0.0
    pressure: float = 0.0
    evacuation_time: float | None = None
    distance_walked: float = 0.0
    speed_sum: float = 0.0
    speed_samples: int = 0
    stair_time: float = 0.0
    congested_time: float = 0.0
    reroutes: int = 0
    last_route_check: float = 0.0
    hesitation_until: float = 0.0
    queue_entered: float | None = None
    last_motion_time: float = 0.0
    meta: dict = field(default_factory=dict)

    @property
    def speed(self) -> float:
        return (self.vx * self.vx + self.vy * self.vy) ** 0.5
