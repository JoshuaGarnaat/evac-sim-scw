from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


def rotate(x: float, y: float, angle_degrees: float) -> tuple[float, float]:
    """Rotate a two-dimensional vector by the supplied angle."""
    angle = math.radians(angle_degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return x * cosine - y * sine, x * sine + y * cosine


@dataclass(frozen=True, slots=True)
class Rect:

    id: str
    x: float
    y: float
    width: float
    depth: float
    kind: str
    floor: int
    rotation: float = 0.0
    section: str | None = None

    def local_to_world(self, x: float, y: float) -> tuple[float, float]:
        """Transform rectangle-local coordinates into world coordinates."""
        dx, dy = rotate(x, y, self.rotation)
        return self.x + dx, self.y + dy

    def world_to_local(self, x: float, y: float) -> tuple[float, float]:
        """Transform world coordinates into this rectangle's local frame."""
        return rotate(x - self.x, y - self.y, -self.rotation)

    @property
    def center(self) -> tuple[float, float]:
        """Return the rectangle's world-space centre point."""
        return self.local_to_world(self.width / 2, self.depth / 2)

    @property
    def corners(self) -> tuple[tuple[float, float], ...]:
        """Return the four world-space corners."""
        return tuple(self.local_to_world(x, y) for x, y in (
            (0.0, 0.0), (self.width, 0.0),
            (self.width, self.depth), (0.0, self.depth),
        ))

    def contains(self, x: float, y: float, margin: float = 0.0) -> bool:
        """Return whether a point lies inside the rectangle after a margin."""
        local_x, local_y = self.world_to_local(x, y)
        epsilon = 1e-9
        return (
            margin - epsilon <= local_x <= self.width - margin + epsilon
            and margin - epsilon <= local_y <= self.depth - margin + epsilon
        )

    def clamp(self, x: float, y: float, margin: float = 0.0) -> tuple[float, float]:
        """Clamp a world-space point to the rectangle's usable interior."""
        local_x, local_y = self.world_to_local(x, y)
        local_x = min(max(local_x, margin), self.width - margin)
        local_y = min(max(local_y, margin), self.depth - margin)
        return self.local_to_world(local_x, local_y)


@dataclass(frozen=True, slots=True)
class Door:
    id: str
    floor: int
    x: float
    y: float
    width: float
    kind: str
    connects: tuple[str, str]
    rotation: float = 0.0
    side: str | None = None
    target_x: float | None = None
    target_y: float | None = None
    section: str | None = None

    @property
    def transition_target(self) -> tuple[float, float]:
        """Return the optional post-door target, falling back to the doorway."""
        return (
            self.x if self.target_x is None else self.target_x,
            self.y if self.target_y is None else self.target_y,
        )


@dataclass(frozen=True, slots=True)
class Stairwell:
    id: str
    x: float
    y: float
    width: float
    enclosure_width: float
    depth: float
    floors: tuple[int, ...]
    path_length: float
    vertical_rise: float
    capacity_per_m2: float
    rotation: float = 0.0
    entry_offset: float = 0.0
    section: str | None = None

    def local_to_world(self, across: float, forward: float) -> tuple[float, float]:
        """Transform stair-local coordinates into world coordinates."""
        dx, dy = rotate(across, forward, self.rotation)
        return self.x + dx, self.y + dy

    def world_to_local(self, x: float, y: float) -> tuple[float, float]:
        """Transform world coordinates into this stairwell's local frame."""
        return rotate(x - self.x, y - self.y, -self.rotation)


def validate_layout(data: dict[str, Any]) -> None:
    """Validate the required top-level floorplan schema fields."""
    version = int(data.get("schema_version", 1))
    if version not in (1, 2):
        raise ValueError(f"Unsupported floorplan schema_version {version}; expected 1 or 2")
    for key in ("dimensions", "floors"):
        if key not in data:
            raise ValueError(f"Floorplan missing required key: {key}")
    levels = [int(f["level"]) for f in data["floors"]]
    if not levels or len(levels) != len(set(levels)):
        raise ValueError("Floor levels must be present and unique")
    if version == 2 and not data.get("sections"):
        raise ValueError("A schema v2 floorplan must define at least one section")
