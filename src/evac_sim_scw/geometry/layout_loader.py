from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ..config_loader import load_json
from .layout_schema import rotate, validate_layout


def _pair(value: Any, name: str) -> tuple[float, float]:
    """Validate and convert a two-value coordinate sequence."""
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must be a two-number array")
    return float(value[0]), float(value[1])


def _identifier(value: str, section: str, floor: int, many_floors: bool) -> str:
    """Create a unique generated identifier for a floorplan item."""
    result = value.format(section=section, floor=floor)
    if "{" not in value and many_floors:
        result = f"{result}_F{floor}"
    return result


def _transform(origin: tuple[float, float], angle: float, point: tuple[float, float]) -> tuple[float, float]:
    """Rotate a local point and translate it to its section origin."""
    x, y = rotate(*point, angle)
    return origin[0] + x, origin[1] + y


def _wall_point(item: dict[str, Any], room: dict[str, Any]) -> tuple[tuple[float, float], float, str]:
    """Resolve a wall-relative opening into a world point, rotation, and side."""
    side = item["wall"].lower()
    width, depth = _pair(room["size"], "room size")
    offset = float(item.get("offset", (width if side in {"north", "south"} else depth) / 2))
    points = {
        "south": ((offset, 0.0), 0.0),
        "east": ((width, offset), 90.0),
        "north": ((offset, depth), 0.0),
        "west": ((0.0, offset), 90.0),
    }
    if side not in points:
        raise ValueError(f"Door wall must be north, east, south, or west; got {side!r}")
    point, rotation = points[side]
    return point, rotation, side


def compile_floorplan(data: dict[str, Any]) -> dict[str, Any]:
    """Expand schema-v2 sections into a flat floorplan."""
    validate_layout(data)
    if int(data.get("schema_version", 1)) == 1:
        return data

    result = {key: deepcopy(value) for key, value in data.items() if key != "sections"}
    result.update({"rooms": [], "corridors": [], "doors": [], "stairs": [], "exits": []})
    known_ids: set[tuple[str, int]] = set()
    section_ids: set[str] = set()
    floor_levels = {int(item["level"]) for item in data["floors"]}

    for section in data["sections"]:
        section_id = str(section["id"])
        if section_id in section_ids:
            raise ValueError(f"Duplicate section id {section_id!r}")
        section_ids.add(section_id)
        origin = _pair(section.get("at", [0, 0]), f"section {section_id} at")
        angle = float(section.get("rotation", 0.0))
        floors = tuple(int(f) for f in section.get("floors", [0]))
        if not floors or not set(floors) <= floor_levels:
            raise ValueError(f"Section {section_id!r} uses undefined floors {sorted(set(floors) - floor_levels)}")
        local_room_ids = [str(room["id"]) for room in section.get("rooms", [])]
        if len(local_room_ids) != len(set(local_room_ids)):
            raise ValueError(f"Section {section_id!r} contains duplicate local room ids")
        room_specs = {str(room["id"]): room for room in section.get("rooms", [])}

        for floor in floors:
            for collection, kind in (("rooms", None), ("corridors", "corridor")):
                for item in section.get(collection, []):
                    item_floors = tuple(int(f) for f in item.get("floors", floors))
                    if not set(item_floors) <= set(floors):
                        raise ValueError(f"{collection} {item['id']!r} uses a floor outside section {section_id!r}")
                    if floor not in item_floors:
                        continue
                    item_id = _identifier(str(item["id"]), section_id, floor, len(item_floors) > 1)
                    key = (item_id, floor)
                    if key in known_ids:
                        raise ValueError(f"Duplicate element id {item_id!r} on floor {floor}")
                    known_ids.add(key)
                    at = _pair(item.get("at", [0, 0]), f"{collection} {item_id} at")
                    size = _pair(item["size"], f"{collection} {item_id} size")
                    if min(size) <= 0:
                        raise ValueError(f"{collection} {item_id!r} must have a positive size")
                    x, y = _transform(origin, angle, at)
                    target = result[collection]
                    target.append({
                        "id": item_id, "floor": floor, "x": x, "y": y,
                        "width": size[0], "depth": size[1],
                        "kind": kind or item.get("kind", "room"),
                        "rotation": angle + float(item.get("rotation", 0.0)),
                        "section": section_id,
                    })

            for item in section.get("doors", []):
                item_floors = tuple(int(f) for f in item.get("floors", floors))
                if not set(item_floors) <= set(floors):
                    raise ValueError(f"Door {item['id']!r} uses a floor outside section {section_id!r}")
                if floor not in item_floors:
                    continue
                room_ref = str(item["room"])
                if room_ref not in room_specs:
                    raise ValueError(f"Door {item['id']!r} references unknown local room {room_ref!r}")
                room = room_specs[room_ref]
                room_at = _pair(room.get("at", [0, 0]), f"room {room_ref} at")
                point, door_angle, side = _wall_point(item, room)
                room_size = _pair(room["size"], f"room {room_ref} size")
                wall_length = room_size[0] if side in {"north", "south"} else room_size[1]
                width = float(item.get("width", result.get("defaults", {}).get("classroom_door_width", 1.0)))
                offset = float(item.get("offset", wall_length / 2))
                if width <= 0 or offset - width / 2 < 0 or offset + width / 2 > wall_length:
                    raise ValueError(f"Door {item['id']!r} does not fit on the {side} wall of room {room_ref!r}")
                point = _transform(room_at, float(room.get("rotation", 0.0)), point)
                x, y = _transform(origin, angle, point)
                target_distance = float(item.get("transition", 0.6))
                normals = {"south": (0, -1), "east": (1, 0), "north": (0, 1), "west": (-1, 0)}
                normal = rotate(*normals[side], angle + float(room.get("rotation", 0.0)))
                room_floors = tuple(int(f) for f in room.get("floors", floors))
                room_id = _identifier(room_ref, section_id, floor, len(room_floors) > 1)
                result["doors"].append({
                    "id": _identifier(str(item["id"]), section_id, floor, len(item_floors) > 1),
                    "floor": floor, "x": x, "y": y, "width": width,
                    "kind": item.get("kind", "interior"), "connects": [room_id, item.get("connects_to", "corridor")],
                    "rotation": angle + float(room.get("rotation", 0.0)) + door_angle,
                    "side": side, "target_x": x + normal[0] * target_distance,
                    "target_y": y + normal[1] * target_distance, "section": section_id,
                })

            for item in section.get("stairs", []):
                item_floors = tuple(int(f) for f in item.get("floors", floors))
                if not set(item_floors) <= set(floors):
                    raise ValueError(f"Stair {item['id']!r} uses a floor outside section {section_id!r}")
                if floor != item_floors[0]:
                    continue
                at = _pair(item["at"], f"stair {item['id']} at")
                x, y = _transform(origin, angle, at)
                result["stairs"].append({
                    "id": str(item["id"]), "x": x, "y": y,
                    "width": float(item["width"]), "enclosure_width": float(item.get("enclosure_width", item["width"] * 2.4)),
                    "depth": float(item["depth"]), "floors": list(item_floors),
                    "path_length": float(item["path_length"]), "vertical_rise": float(item.get("vertical_rise", result["dimensions"]["floor_height"])),
                    "capacity_per_m2": float(item.get("capacity_per_m2", 2.0)),
                    "rotation": angle + float(item.get("rotation", 0.0)),
                    "entry_offset": float(item.get("entry_offset", 0.0)), "section": section_id,
                })

            for item in section.get("exits", []):
                item_floors = tuple(int(f) for f in item.get("floors", [0]))
                if not set(item_floors) <= set(floors):
                    raise ValueError(f"Exit {item['id']!r} uses a floor outside section {section_id!r}")
                if floor not in item_floors:
                    continue
                at = _pair(item["at"], f"exit {item['id']} at")
                x, y = _transform(origin, angle, at)
                result["exits"].append({
                    "id": _identifier(str(item["id"]), section_id, floor, len(item_floors) > 1),
                    "floor": floor, "x": x, "y": y,
                    "width": float(item["width"]), "rotation": angle + float(item.get("rotation", 0.0)),
                    "section": section_id,
                })
    classrooms = {room["id"] for room in result["rooms"] if room["kind"] == "classroom"}
    rooms_with_doors = {door["connects"][0] for door in result["doors"]}
    room_ids = {room["id"] for room in result["rooms"]}
    unknown_rooms = rooms_with_doors - room_ids
    if unknown_rooms:
        raise ValueError(f"Doors reference rooms that do not exist on that floor: {sorted(unknown_rooms)}")
    missing_doors = classrooms - rooms_with_doors
    if missing_doors:
        raise ValueError(f"Classrooms missing a door: {sorted(missing_doors)}")
    if not result["corridors"]:
        raise ValueError("A schema v2 floorplan must define at least one corridor")
    if not result["exits"]:
        raise ValueError("A schema v2 floorplan must define at least one exit")
    for collection in ("rooms", "corridors", "doors", "stairs", "exits"):
        ids = [item["id"] for item in result[collection]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate ids in compiled {collection}")
    return result


def load_floorplan(path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load, validate, and compile a floorplan JSON file."""
    source = load_json(path)
    return source, compile_floorplan(source)
