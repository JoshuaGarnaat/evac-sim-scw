from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Rect:
    id: str
    x: float
    y: float
    width: float
    depth: float
    kind: str
    floor: int

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.depth / 2

    def contains(self, x: float, y: float, margin: float = 0.0) -> bool:
        return (
            self.x + margin <= x <= self.x + self.width - margin
            and self.y + margin <= y <= self.y + self.depth - margin
        )


@dataclass(frozen=True, slots=True)
class Door:
    id: str
    floor: int
    x: float
    y: float
    width: float
    kind: str
    connects: tuple[str, str]


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


def validate_layout(data: dict[str, Any]) -> None:
    for key in ("dimensions", "floors", "corridors", "stairs", "exits"):
        if key not in data:
            raise ValueError(f"Layout missing required key: {key}")
    floor_ids = {int(f["level"]) for f in data["floors"]}
    if floor_ids != {0, 1, 2}:
        raise ValueError("The bundled example must define floors 0, 1, and 2")
