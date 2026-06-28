from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..config_loader import load_json
from .layout_schema import Door, Rect, Stairwell, validate_layout


class Building:
    def __init__(self, layout_path: str | Path):
        self.path = Path(layout_path).resolve()
        self.raw = load_json(self.path)
        validate_layout(self.raw)
        dims = self.raw["dimensions"]
        self.width = float(dims["width"])
        self.depth = float(dims["depth"])
        self.floor_height = float(dims["floor_height"])
        self.floors = [int(f["level"]) for f in self.raw["floors"]]
        self.corridors = [
            Rect(c["id"], c["x"], c["y"], c["width"], c["depth"], "corridor", c["floor"])
            for c in self.raw["corridors"]
        ]
        self.rooms = self._expand_rooms()
        self.stairs = [
            Stairwell(
                s["id"], s["x"], s["y"], s["width"], s.get("enclosure_width", s["width"]), s["depth"],
                tuple(s["floors"]), s["path_length"], s["vertical_rise"], s["capacity_per_m2"]
            )
            for s in self.raw["stairs"]
        ]
        self.doors = self._make_doors()
        self.exits = [
            Door(e["id"], 0, e["x"], e["y"], e["width"], "exit", ("corridor", "outside"))
            for e in self.raw["exits"]
        ]

    def _expand_rooms(self) -> list[Rect]:
        rooms: list[Rect] = []
        for item in self.raw.get("rooms", []):
            rooms.append(Rect(item["id"], item["x"], item["y"], item["width"], item["depth"], item["kind"], item["floor"]))
        for generator in self.raw.get("room_generators", []):
            for floor in generator["floors"]:
                for side in ("south", "north"):
                    y = generator["south_y"] if side == "south" else generator["north_y"]
                    for index in range(generator["count_per_side"]):
                        if index in generator.get("skip_indices", {}).get(side, []):
                            continue
                        x = generator["start_x"] + index * (generator["room_width"] + generator["gap"])
                        rooms.append(Rect(
                            f"F{floor}_{side[0].upper()}{index + 1:02d}", x, y,
                            generator["room_width"], generator["room_depth"], "classroom", floor
                        ))
        return rooms

    def _make_doors(self) -> list[Door]:
        doors: list[Door] = []
        width = float(self.raw["defaults"]["classroom_door_width"])
        corridor_y = float(self.raw["navigation"]["corridor_center_y"])
        for room in self.rooms:
            if room.kind != "classroom":
                continue
            x = room.x + room.width / 2
            y = room.y + room.depth if room.center[1] < corridor_y else room.y
            doors.append(Door(f"D_{room.id}", room.floor, x, y, width, "interior", (room.id, "corridor")))
        stair_door_y = float(self.raw["navigation"]["corridor_max_y"]) + 0.2
        for stair in self.stairs:
            for floor in stair.floors:
                for transition, direction in (("ENTRY", -1.0), ("EXIT", 1.0)):
                    doors.append(Door(
                        f"D_{stair.id}_{transition}_F{floor}", floor,
                        stair.x + direction * stair.enclosure_width * 0.23, stair_door_y,
                        stair.width, "stair_entry", (f"{stair.id}_F{floor}", "corridor"),
                    ))
        return doors

    def room_door(self, room_id: str) -> Door:
        return next(d for d in self.doors if d.connects[0] == room_id)

    def serializable(self) -> dict[str, Any]:
        return {
            "id": self.raw["id"], "synthetic": self.raw["synthetic"],
            "dimensions": self.raw["dimensions"], "floors": self.raw["floors"],
            "rooms": [asdict(r) for r in self.rooms],
            "corridors": [asdict(c) for c in self.corridors],
            "doors": [asdict(d) for d in self.doors],
            "exits": [asdict(e) for e in self.exits],
            "stairs": [asdict(s) for s in self.stairs],
            "navigation": self.raw["navigation"],
        }
