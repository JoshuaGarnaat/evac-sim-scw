from __future__ import annotations

from dataclasses import asdict
import heapq
import math
from pathlib import Path
from typing import Any

from .layout_loader import load_floorplan
from .layout_schema import Door, Rect, Stairwell


class Building:
    def __init__(self, layout_path: str | Path):
        self.path = Path(layout_path).resolve()
        self.source, self.raw = load_floorplan(self.path)
        self.schema_version = int(self.source.get("schema_version", 1))
        dims = self.raw["dimensions"]
        self.width = float(dims["width"])
        self.depth = float(dims["depth"])
        self.floor_height = float(dims["floor_height"])
        self.floors = [int(f["level"]) for f in self.raw["floors"]]
        self.navigation_grid_size = float(self.raw.get("navigation", {}).get("grid_size", 0.5))
        self.navigation_clearance = float(self.raw.get("navigation", {}).get("clearance", 0.32))
        self._path_cache: dict[tuple, tuple[tuple[float, float], ...]] = {}
        self._walkable_cells: dict[int, frozenset[tuple[int, int]]] = {}
        self.corridors = [
            Rect(c["id"], c["x"], c["y"], c["width"], c["depth"], "corridor", c["floor"], c.get("rotation", 0.0), c.get("section"))
            for c in self.raw["corridors"]
        ]
        self.rooms = self._expand_rooms()
        self.stairs = [
            Stairwell(
                s["id"], s["x"],
                s["y"] if self.schema_version == 2 else float(self.raw["navigation"]["corridor_max_y"]),
                s["width"], s.get("enclosure_width", s["width"]), s["depth"],
                tuple(s["floors"]), s["path_length"], s["vertical_rise"], s["capacity_per_m2"],
                s.get("rotation", 0.0), s.get("entry_offset", 0.0), s.get("section")
            )
            for s in self.raw["stairs"]
        ]
        self.doors = self._make_doors()
        self.exits = [
            Door(
                e["id"], int(e.get("floor", 0)), e["x"], e["y"], e["width"], "exit", ("corridor", "outside"),
                e.get("rotation", 90.0 if self.schema_version == 1 and (e["x"] < 1.0 or e["x"] > self.width - 1.0) else 0.0),
                section=e.get("section"),
            )
            for e in self.raw["exits"]
        ]

    def _expand_rooms(self) -> list[Rect]:
        rooms: list[Rect] = []
        for item in self.raw.get("rooms", []):
            rooms.append(Rect(
                item["id"], item["x"], item["y"], item["width"], item["depth"], item["kind"], item["floor"],
                item.get("rotation", 0.0), item.get("section"),
            ))
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
        if self.schema_version == 2:
            return [Door(
                d["id"], d["floor"], d["x"], d["y"], d["width"], d["kind"], tuple(d["connects"]),
                d.get("rotation", 0.0), d.get("side"), d.get("target_x"), d.get("target_y"), d.get("section"),
            ) for d in self.raw["doors"]]
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

    def room(self, room_id: str) -> Rect:
        return next(room for room in self.rooms if room.id == room_id)

    def corridors_on(self, floor: int) -> list[Rect]:
        return [corridor for corridor in self.corridors if corridor.floor == floor]

    def corridor_contains(self, floor: int, x: float, y: float, clearance: float) -> bool:
        """Return whether a body centre is in corridor space and outside rooms."""
        corridors = self.corridors_on(floor)

        def in_walkable_union(px: float, py: float) -> bool:
            if any(corridor.contains(px, py) for corridor in corridors):
                return True
            for stair in self.stairs:
                if floor not in stair.floors:
                    continue
                local_x, local_y = stair.world_to_local(px, py)
                if (
                    -stair.enclosure_width / 2 <= local_x <= stair.enclosure_width / 2
                    and 0.0 <= local_y <= max(self.navigation_grid_size, clearance)
                ):
                    return True
            return False

        if not in_walkable_union(x, y):
            return False
        if clearance > 0:
            samples = 16
            if not all(
                in_walkable_union(
                    x + math.cos(2 * math.pi * index / samples) * clearance,
                    y + math.sin(2 * math.pi * index / samples) * clearance,
                )
                for index in range(samples)
            ):
                return False
        room_margin = -clearance + 1e-6
        return not any(
            room.kind != "stairwell"
            and room.floor == floor
            and room.contains(x, y, room_margin)
            for room in self.rooms
        )

    def project_to_corridor(
        self,
        floor: int,
        proposed: tuple[float, float],
        previous: tuple[float, float],
        clearance: float,
    ) -> tuple[float, float]:
        corridors = self.corridors_on(floor)
        previous_corridors = [
            corridor for corridor in corridors
            if corridor.contains(*previous, clearance - 1e-6)
        ]
        candidates = [corridor.clamp(*proposed, clearance) for corridor in previous_corridors]

        epsilon = 1e-5
        for room in self.rooms:
            if room.floor != floor or room.kind == "stairwell" or not room.contains(*proposed, -clearance):
                continue
            local_x, local_y = room.world_to_local(*proposed)
            xmin, xmax = -clearance, room.width + clearance
            ymin, ymax = -clearance, room.depth + clearance
            local_candidates = (
                (xmin - epsilon, min(max(local_y, ymin), ymax)),
                (xmax + epsilon, min(max(local_y, ymin), ymax)),
                (min(max(local_x, xmin), xmax), ymin - epsilon),
                (min(max(local_x, xmin), xmax), ymax + epsilon),
            )
            candidates.extend(room.local_to_world(x, y) for x, y in local_candidates)

        valid = [
            point for point in candidates
            if self.corridor_contains(floor, *point, clearance - 1e-6)
        ]
        if valid:
            return min(valid, key=lambda point: math.dist(point, proposed))

        low, high = 0.0, 1.0
        for _ in range(14):
            middle = (low + high) / 2
            point = (
                previous[0] + (proposed[0] - previous[0]) * middle,
                previous[1] + (proposed[1] - previous[1]) * middle,
            )
            if self.corridor_contains(floor, *point, clearance):
                low = middle
            else:
                high = middle
        return (
            previous[0] + (proposed[0] - previous[0]) * low,
            previous[1] + (proposed[1] - previous[1]) * low,
        )

    def corridor_path(
        self, floor: int, start: tuple[float, float], end: tuple[float, float],
        strict_end: bool = False,
    ) -> list[tuple[float, float]]:
        """Find a path through the union of arbitrary oriented corridor rectangles."""
        if self.schema_version == 1:
            return [end]
        size = self.navigation_grid_size
        if strict_end:
            key = (floor, strict_end, *(round(value, 5) for point in (start, end) for value in point))
        else:
            key = (floor, strict_end, *(round(value / size) for point in (start, end) for value in point))
        if key not in self._path_cache:
            self._path_cache[key] = tuple(self._grid_path(floor, start, end, size, strict_end))
        path = list(self._path_cache[key])
        if path:
            path[-1] = end
        return path

    def corridor_distance(
        self, floor: int, start: tuple[float, float], end: tuple[float, float]
    ) -> float:
        """Return walkable route length, or infinity for disconnected components."""
        if self.schema_version == 1:
            return math.dist(start, end)
        path = self.corridor_path(floor, start, end)
        if not path:
            return math.inf
        distance = 0.0
        previous = start
        for point in path:
            distance += math.dist(previous, point)
            previous = point
        return distance

    def corridor_segment_visible(
        self, floor: int, start: tuple[float, float], end: tuple[float, float],
        clearance: float,
    ) -> bool:
        """Return whether a straight body-centre segment stays in walkable space."""
        distance = math.dist(start, end)
        spacing = max(self.navigation_grid_size * 0.2, 0.05)
        samples = max(1, math.ceil(distance / spacing))
        return all(
            self.corridor_contains(
                floor,
                start[0] + (end[0] - start[0]) * index / samples,
                start[1] + (end[1] - start[1]) * index / samples,
                clearance,
            )
            for index in range(samples + 1)
        )

    def _grid_path(self, floor, start, end, size, strict_end=False) -> list[tuple[float, float]]:
        corridors = self.corridors_on(floor)
        if not corridors:
            return [end]

        columns = math.ceil(self.width / size)
        rows = math.ceil(self.depth / size)

        if floor not in self._walkable_cells:
            self._walkable_cells[floor] = frozenset(
                (column, row)
                for column in range(columns)
                for row in range(rows)
                if self.corridor_contains(
                    floor, column * size + size / 2, row * size + size / 2,
                    self.navigation_clearance,
                )
            )
        walkable = self._walkable_cells[floor]

        def point(cell):
            return (cell[0] * size + size / 2, cell[1] * size + size / 2)

        def allowed(cell):
            return cell in walkable

        def nearest(value):
            initial = (math.floor(value[0] / size), math.floor(value[1] / size))
            if allowed(initial):
                return initial
            for radius in range(1, max(columns, rows)):
                candidates = []
                for dx in range(-radius, radius + 1):
                    candidates.extend(((initial[0] + dx, initial[1] - radius), (initial[0] + dx, initial[1] + radius)))
                for dy in range(-radius + 1, radius):
                    candidates.extend(((initial[0] - radius, initial[1] + dy), (initial[0] + radius, initial[1] + dy)))
                valid = [cell for cell in candidates if allowed(cell)]
                if valid:
                    return min(valid, key=lambda cell: math.dist(point(cell), value))
            return None

        first, last = nearest(start), nearest(end)
        if first is None or last is None:
            return []
        queue = [(0.0, first)]
        cost = {first: 0.0}
        previous: dict[tuple[int, int], tuple[int, int]] = {}
        directions = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
        while queue:
            _, current = heapq.heappop(queue)
            if current == last:
                break
            for dx, dy in directions:
                neighbor = current[0] + dx, current[1] + dy
                if not allowed(neighbor):
                    continue
                if dx and dy and (not allowed((current[0] + dx, current[1])) or not allowed((current[0], current[1] + dy))):
                    continue
                candidate = cost[current] + math.hypot(dx, dy)
                if candidate >= cost.get(neighbor, math.inf):
                    continue
                cost[neighbor] = candidate
                previous[neighbor] = current
                priority = candidate + math.dist(neighbor, last)
                heapq.heappush(queue, (priority, neighbor))
        if last not in cost:
            return []
        cells = [last]
        while cells[-1] != first:
            cells.append(previous[cells[-1]])
        cells.reverse()
        
        def visible(left_cell, right_cell):
            left, right = point(left_cell), point(right_cell)
            distance = math.dist(left, right)
            samples = max(1, math.ceil(distance / (size * 0.4)))
            for index in range(samples + 1):
                fraction = index / samples
                x = left[0] + (right[0] - left[0]) * fraction
                y = left[1] + (right[1] - left[1]) * fraction
                if (math.floor(x / size), math.floor(y / size)) not in walkable:
                    return False
            return True

        def visible_world(left, right):
            distance = math.dist(left, right)
            samples = max(1, math.ceil(distance / (size * 0.25)))
            return all(
                self.corridor_contains(
                    floor,
                    left[0] + (right[0] - left[0]) * index / samples,
                    left[1] + (right[1] - left[1]) * index / samples,
                    self.navigation_clearance,
                )
                for index in range(samples + 1)
            )

        result: list[tuple[float, float]] = []
        anchor = 0
        while anchor < len(cells) - 1:
            candidate = len(cells) - 1
            anchor_point = start if anchor == 0 else point(cells[anchor])
            while candidate > anchor + 1 and (
                not visible(cells[anchor], cells[candidate])
                or (
                    strict_end
                    and not visible_world(
                        anchor_point,
                        end if candidate == len(cells) - 1 else point(cells[candidate]),
                    )
                )
            ):
                candidate -= 1
            result.append(end if candidate == len(cells) - 1 else point(cells[candidate]))
            anchor = candidate
        return result or [end]

    def serializable(self) -> dict[str, Any]:
        return {
            "id": self.raw["id"], "synthetic": self.raw.get("synthetic", True),
            "schema_version": self.schema_version,
            "dimensions": self.raw["dimensions"], "floors": self.raw["floors"],
            "rooms": [asdict(r) for r in self.rooms],
            "corridors": [asdict(c) for c in self.corridors],
            "doors": [asdict(d) for d in self.doors],
            "exits": [asdict(e) for e in self.exits],
            "stairs": [asdict(s) for s in self.stairs],
            "navigation": self.raw.get("navigation", {}),
        }
