from __future__ import annotations

from collections import Counter
from datetime import datetime
import logging
import math
from pathlib import Path
import time

from ..agents.behavior import classify_state, density_speed_factor
from ..agents.collision_avoidance import separate
from ..agents.population import create_population
from ..agents.route_choice import choose_route
from ..agents.social_force import movement_force, oriented_rectangular_wall_force, rectangular_wall_force
from ..geometry.building import Building
from ..geometry.spatial_index import SpatialGrid
from ..replay.writer import ReplayWriter
from .congestion import crowd_pressure
from .density import update_local_density
from .metrics import MetricsCollector


def reached(agent, x: float, y: float, tolerance: float) -> bool:
    return math.hypot(agent.x - x, agent.y - y) <= tolerance
    
class SimulationEngine:
    def __init__(self, config: dict):
        self.config = config
        self.building = Building(config["building"]["layout_file"])
        self.agents = create_population(self.building, config)
        self.by_id = {a.id: a for a in self.agents}
        self.grid = SpatialGrid(config["simulation"]["neighbor_radius"])
        self.metrics = MetricsCollector()
        self.time = 0.0
        self.evacuated = 0
        self.door_seen: set[int] = set()
        self.rng_state = config["scenario"]["random_seed"]
        for agent in self.agents:
            self._select_route(agent, {})
            door = self.building.room_door(agent.classroom_id)
            agent.target_x, agent.target_y = door.x, door.y

    def run(self) -> Path:
        output = self._make_output_dir()
        replay = ReplayWriter(output, self.building, self.config)
        dt = float(self.config["simulation"]["dt"])
        replay_interval = float(self.config["simulation"]["replay_sample_interval"])
        metrics_interval = float(self.config["simulation"]["metrics_sample_interval"])
        next_replay = next_metrics = 0.0
        max_time = float(self.config["simulation"]["max_time"])
        logging.info("Starting %d-agent simulation", len(self.agents))
        while self.evacuated < len(self.agents) and self.time <= max_time:
            started = time.perf_counter()
            self.step(dt)
            self.metrics.step_times.append(time.perf_counter() - started)
            # The epsilon prevents accumulated binary rounding from skipping a sample boundary.
            if self.time + 1e-9 >= next_replay:
                replay.write_frame(self.time, self.agents, self.evacuated)
                next_replay += replay_interval
            if self.time + 1e-9 >= next_metrics:
                occupancy, queues = self._stair_counts()
                self.metrics.sample(self.time, self.agents, self.building, occupancy, queues)
                next_metrics += metrics_interval
            if int(self.time / 10) != int((self.time - dt) / 10):
                logging.info("t=%5.1fs evacuated=%d/%d", self.time, self.evacuated, len(self.agents))
        if replay.last_timestamp < self.time - 1e-9:
            replay.write_frame(self.time, self.agents, self.evacuated)
        replay_meta = replay.close()
        self.metrics.export(output, self.agents, replay_meta, self.time)
        (Path(self.config["outputs"]["root"]) / "latest.txt").write_text(str(output.resolve()), encoding="utf-8")
        logging.info("Finished at %.1fs; output: %s", self.time, output)
        return output

    def step(self, dt: float) -> None:
        self.time += dt
        self.grid.rebuild(self.agents)
        update_local_density(self.agents, self.grid, self.config["simulation"]["density_radius"])
        occupancy, queues = self._stair_counts()
        route_load = Counter(queues)
        occupancy_weight = self.config["route_choice"]["stair_occupancy_queue_equivalent"]
        for stair_id, count in occupancy.items():
            route_load[stair_id] += count * occupancy_weight
        for agent in self.agents:
            if agent.state == "exited":
                continue
            if agent.state == "waiting":
                if self.time < agent.reaction_time:
                    continue
                agent.state = "evacuating"
                agent.last_motion_time = self.time
            self._advance_phase(agent, route_load)
            if agent.state in {"queued", "exited"} or self.time < agent.hesitation_until:
                agent.vx = agent.vy = 0.0
                continue
            neighbor_ids = self.grid.neighbors(agent.floor, agent.x, agent.y)
            neighbors = [self.by_id[index] for index in neighbor_ids]
            target_key = (
                agent.floor, agent.phase,
                round(agent.target_x, 2), round(agent.target_y, 2),
            )
            target_distance = math.hypot(
                agent.target_x - agent.x, agent.target_y - agent.y,
            )
            if agent.meta.get("progress_target") != target_key:
                agent.meta["progress_target"] = target_key
                agent.meta["best_target_distance"] = target_distance
                agent.meta["last_progress_time"] = self.time
            elif target_distance < agent.meta.get("best_target_distance", math.inf) - 0.025:
                agent.meta["best_target_distance"] = target_distance
                agent.meta["last_progress_time"] = self.time
            progress_stalled = (
                agent.phase == "corridor"
                and self.time - agent.meta.get("last_progress_time", self.time) > 2.5
            )
            near_exit = False
            if agent.floor == 0 and agent.phase == "corridor":
                exit_door = self._exit(agent.selected_exit)
                near_exit = math.hypot(
                    agent.x - exit_door.x, agent.y - exit_door.y,
                ) <= max(2.0, exit_door.width)
            factor = density_speed_factor(agent.local_density, self.config)
            if agent.on_stair:
                factor = max(factor, 0.55)
            elif progress_stalled or near_exit:
                factor = max(factor, 0.55)
            desired = agent.preferred_speed * factor
            if agent.on_stair:
                desired *= self.config["movement"]["stair_speed_multiplier"]
            force_neighbors = neighbors
            separation_neighbors = neighbors
            if agent.on_stair:
                same_stream = [
                    other for other in neighbors
                    if other.on_stair
                    and other.selected_stair == agent.selected_stair
                    and other.phase == agent.phase
                ]
                force_neighbors = []
                separation_neighbors = same_stream
            elif progress_stalled or near_exit:
                force_neighbors = []
            agent.ax, agent.ay = movement_force(
                agent, agent.target_x, agent.target_y, desired,
                force_neighbors, self.config["social_force"],
            )
            stalled_for = self.time - agent.last_motion_time
            if agent.phase == "corridor" and stalled_for > 3.0 and agent.local_density < 1.5:
                # Apply a bounded lateral nudge to break low-density force equilibria.
                dx, dy = agent.target_x - agent.x, agent.target_y - agent.y
                length = max(math.hypot(dx, dy), 0.01)
                direction = -1.0 if agent.id % 2 else 1.0
                if self.building.schema_version == 2:
                    lateral_x, lateral_y = -dy / length, dx / length
                    probe = max(agent.radius + 0.08, 0.25)
                    left_open = self.building.corridor_contains(
                        agent.floor,
                        agent.x + lateral_x * probe,
                        agent.y + lateral_y * probe,
                        agent.radius,
                    )
                    right_open = self.building.corridor_contains(
                        agent.floor,
                        agent.x - lateral_x * probe,
                        agent.y - lateral_y * probe,
                        agent.radius,
                    )
                    if left_open != right_open:
                        direction = 1.0 if left_open else -1.0
                yield_force = min(1.2, 0.35 + 0.08 * stalled_for)
                agent.ax += direction * -dy / length * yield_force
                agent.ay += direction * dx / length * yield_force
            wall_x, wall_y = self._wall_force(agent)
            agent.ax += wall_x
            agent.ay += wall_y
            force = math.hypot(agent.ax, agent.ay)
            if force > agent.max_acceleration:
                agent.ax *= agent.max_acceleration / force
                agent.ay *= agent.max_acceleration / force
            agent.vx += agent.ax * dt
            agent.vy += agent.ay * dt
            speed = agent.speed
            cap = min(agent.max_speed, desired * 1.12)
            if speed > cap and speed > 0:
                agent.vx *= cap / speed
                agent.vy *= cap / speed
            approach_direction = None
            if near_exit:
                dx = agent.target_x - agent.x
                dy = agent.target_y - agent.y
                length = max(math.hypot(dx, dy), 1e-6)
                approach_direction = (dx / length, dy / length)
                forward_speed = (
                    agent.vx * approach_direction[0]
                    + agent.vy * approach_direction[1]
                )
                if forward_speed < 0.0:
                    agent.vx -= forward_speed * approach_direction[0]
                    agent.vy -= forward_speed * approach_direction[1]
            old_x, old_y = agent.x, agent.y
            agent.x += agent.vx * dt
            agent.y += agent.vy * dt
            cx, cy = separate(agent, separation_neighbors)
            if approach_direction is not None:
                forward_correction = (
                    cx * approach_direction[0] + cy * approach_direction[1]
                )
                if forward_correction < 0.0:
                    cx -= forward_correction * approach_direction[0]
                    cy -= forward_correction * approach_direction[1]
            agent.x += cx
            agent.y += cy
            self._constrain(agent, old_x, old_y)
            if agent.on_stair:
                self._update_stair_elevation(agent)
            distance = math.hypot(agent.x - old_x, agent.y - old_y)
            if distance >= 0.01:
                agent.last_motion_time = self.time
            agent.distance_walked += distance
            agent.speed_sum += agent.speed
            agent.speed_samples += 1
            if agent.floor == 0 and agent.phase == "corridor":
                exit_door = self._exit(agent.selected_exit)
                if self._reached_exit(agent, exit_door, self.config["simulation"]["waypoint_tolerance"]):
                    self._mark_exited(agent, exit_door)
                    continue
            agent.pressure = crowd_pressure(agent, self.config)
            agent.state = classify_state(agent, self.config)
            if agent.state == "congested":
                agent.congested_time += dt
            if agent.on_stair:
                agent.stair_time += dt

    def _advance_phase(self, agent, queues: dict[str, int]) -> None:
        tolerance = self.config["simulation"]["waypoint_tolerance"]
        if agent.on_stair:
            self._advance_stair_phase(agent)
            if agent.on_stair:
                return
        if agent.phase == "room" and reached(agent, agent.target_x, agent.target_y, tolerance):
            if agent.id not in self.door_seen:
                self.metrics.record_door(self.time, self.building.room_door(agent.classroom_id).id, agent.id)
                self.door_seen.add(agent.id)
            agent.phase = "door_transition"
            door = self.building.room_door(agent.classroom_id)
            agent.target_x, agent.target_y = door.transition_target
        elif agent.phase == "door_transition" and reached(agent, agent.target_x, agent.target_y, tolerance):
            agent.phase = "corridor"
        if agent.phase != "corridor":
            return
        if self.time - agent.last_route_check >= self.config["route_choice"]["reconsider_interval"]:
            self._maybe_reroute(agent, queues)
        if agent.floor > 0:
            stair = self._stair(agent.selected_stair)
            local_x, local_y = stair.world_to_local(agent.x, agent.y)
            lateral_limit = max(0.0, stair.width / 2 - agent.radius)
            target_local_x = min(max(local_x, -stair.enclosure_width * 0.23 - lateral_limit), -stair.enclosure_width * 0.23 + lateral_limit)
            destination = stair.local_to_world(target_local_x, stair.entry_offset)
            final_leg = self._follow_corridor_path(agent, destination, strict_end=True)
            crossed_entry = (
                final_leg
                and local_y >= stair.entry_offset - 1e-9
                and abs(local_x + stair.enclosure_width * 0.23)
                <= lateral_limit + tolerance
            )
            if crossed_entry:
                agent.state = "on_stairs"
                agent.on_stair = True
                agent.stair_from_floor = agent.floor
                agent.stair_progress = 0.0
                agent.phase = "stair_first_flight"
                target_x = self._stair_flight_target_x(agent, -stair.enclosure_width * 0.23, stair)
                agent.target_x, agent.target_y = stair.local_to_world(target_x, self._stair_landing_y(stair))
        else:
            exit_door = self._exit(agent.selected_exit)
            final_leg = self._follow_corridor_path(agent, self._exit_target(agent, exit_door))
            if final_leg and self._reached_exit(agent, exit_door, tolerance):
                self._mark_exited(agent, exit_door)

    def _mark_exited(self, agent, exit_door) -> None:
        if agent.state == "exited":
            return
        agent.state = "exited"
        agent.evacuation_time = self.time
        agent.vx = agent.vy = 0.0
        self.evacuated += 1
        self.metrics.record_exit(self.time, exit_door.id, agent.id)

    def _select_route(self, agent, queues: dict[str, int]) -> None:
        route = choose_route(agent, self.building, queues, self.config)
        agent.selected_exit = route.exit_id
        agent.selected_stair = route.stair_id

    def _maybe_reroute(self, agent, queues: dict[str, int]) -> None:
        agent.last_route_check = self.time
        old_exit, old_stair = agent.selected_exit, agent.selected_stair
        old_route = choose_route(agent, self.building, queues, self.config)
        if (old_route.exit_id, old_route.stair_id) != (old_exit, old_stair):
            threshold = self.config["route_choice"]["reroute_improvement_threshold"]
            current_exit = self._exit(old_exit)
            current_stair = self._stair(old_stair) if old_stair else None
            from ..geometry.nav_graph import route_cost
            current_cost = route_cost(agent, current_exit, current_stair, queues, self.config, self.building)
            if old_route.estimated_cost < current_cost * (1.0 - threshold):
                agent.selected_exit, agent.selected_stair = old_route.exit_id, old_route.stair_id
                agent.reroutes += 1
                agent.state = "rerouting"
                agent.meta.pop("corridor_path", None)
                agent.meta.pop("corridor_path_key", None)

    def _follow_corridor_path(
        self, agent, destination: tuple[float, float], strict_end: bool = False,
    ) -> bool:
        tolerance = self.config["simulation"]["waypoint_tolerance"]
        grid = self.building.navigation_grid_size
        key = (
            agent.floor, strict_end,
            round(destination[0] / grid), round(destination[1] / grid),
        )
        if agent.meta.get("corridor_path_key") != key:
            agent.meta["corridor_path_key"] = key
            agent.meta["corridor_path"] = self.building.corridor_path(
                agent.floor, (agent.x, agent.y), destination, strict_end,
            )
            agent.meta["corridor_previous_waypoint"] = (agent.x, agent.y)
        path = agent.meta["corridor_path"]
        if not path:
            self._select_route(agent, {})
            agent.meta.pop("corridor_path_key", None)
            return False
        check_visibility = (
            strict_end
            and self.time >= agent.meta.get("next_path_visibility_check", 0.0)
        )
        if check_visibility:
            agent.meta["next_path_visibility_check"] = self.time + 1.0
        if check_visibility and not self.building.corridor_segment_visible(
            agent.floor, (agent.x, agent.y), path[0], agent.radius,
        ):
            path = self.building.corridor_path(
                agent.floor, (agent.x, agent.y), destination, strict_end,
            )
            agent.meta["corridor_path"] = path
            agent.meta["corridor_previous_waypoint"] = (agent.x, agent.y)
            if not path:
                return False
        while len(path) > 1:
            waypoint = path[0]
            previous = agent.meta.get(
                "corridor_previous_waypoint", (agent.x, agent.y),
            )
            segment_x = waypoint[0] - previous[0]
            segment_y = waypoint[1] - previous[1]
            segment_length_sq = segment_x * segment_x + segment_y * segment_y
            crossed_waypoint = False
            if segment_length_sq > 1e-8:
                progress = (
                    (agent.x - previous[0]) * segment_x
                    + (agent.y - previous[1]) * segment_y
                ) / segment_length_sq
                crossed_waypoint = progress >= 1.0
            if not reached(agent, *waypoint, tolerance) and not crossed_waypoint:
                break
            agent.meta["corridor_previous_waypoint"] = waypoint
            path.pop(0)
        agent.target_x, agent.target_y = path[0]
        return len(path) == 1

    def _constrain(self, agent, old_x: float | None = None, old_y: float | None = None) -> None:
        agent.x = min(max(agent.x, 0.1), self.building.width - 0.1)
        agent.y = min(max(agent.y, 0.1), self.building.depth - 0.1)
        if agent.on_stair:
            stair = self._stair(agent.selected_stair)
            half_width = stair.width / 2
            local_x, local_y = stair.world_to_local(agent.x, agent.y)
            entry_y = stair.entry_offset
            landing_y = self._stair_landing_y(stair)
            if agent.phase == "stair_landing":
                local_x = min(max(local_x, -stair.enclosure_width * 0.23 - half_width), stair.enclosure_width * 0.23 + half_width)
                local_y = min(max(local_y, landing_y), landing_y + stair.width)
            else:
                centre_x = -stair.enclosure_width * 0.23 if agent.phase == "stair_first_flight" else stair.enclosure_width * 0.23
                local_x = min(max(local_x, centre_x - half_width), centre_x + half_width)
                local_y = min(max(local_y, entry_y), landing_y)
            agent.x, agent.y = stair.local_to_world(local_x, local_y)
            return
        if agent.phase == "corridor":
            if self.building.schema_version == 2:
                corridors = self.building.corridors_on(agent.floor)
                margin = agent.radius
                inside = lambda x, y: self.building.corridor_contains(agent.floor, x, y, margin)
                if corridors and not inside(agent.x, agent.y):
                    previous = (
                        (old_x, old_y)
                        if old_x is not None and old_y is not None
                        else (agent.x, agent.y)
                    )
                    projected = self.building.project_to_corridor(
                        agent.floor, (agent.x, agent.y), previous, margin,
                    )
                    proposed = (agent.x, agent.y)
                    candidates = (
                        projected,
                        (previous[0], proposed[1]),
                        (proposed[0], previous[1]),
                    )
                    valid = [point for point in candidates if inside(*point)]
                    if valid:
                        agent.x, agent.y = min(
                            valid, key=lambda point: math.dist(point, proposed)
                        )
                    else:
                        agent.x, agent.y = previous
                        agent.vx = agent.vy = 0.0
                return
            nav = self.building.raw["navigation"]
            agent.y = min(max(agent.y, nav["corridor_min_y"]), nav["corridor_max_y"])

    def _wall_force(self, agent) -> tuple[float, float]:
        social = self.config["social_force"]
        if agent.on_stair:
            return 0.0, 0.0
        if agent.phase == "room":
            room = self.building.room(agent.classroom_id)
            door = self.building.room_door(agent.classroom_id)
            side = door.side or ("north" if door.y > room.center[1] else "south")
            local_x, local_y = room.world_to_local(door.x, door.y)
            coordinate = local_x if side in {"north", "south"} else local_y
            return oriented_rectangular_wall_force(agent, room, [(side, coordinate, door.width)], social)
        if self.building.schema_version == 2:
            return 0.0, 0.0
        nav = self.building.raw["navigation"]
        openings = [("north", stair.x, stair.enclosure_width) for stair in self.building.stairs]
        if agent.floor == 0:
            for exit_door in self.building.exits:
                if exit_door.x < 1.0:
                    openings.append(("west", exit_door.y, exit_door.width))
                elif exit_door.x > self.building.width - 1.0:
                    openings.append(("east", exit_door.y, exit_door.width))
                elif exit_door.y <= nav["corridor_min_y"] + 0.2:
                    openings.append(("south", exit_door.x, exit_door.width))
        return rectangular_wall_force(
            agent, (0.0, self.building.width, nav["corridor_min_y"], nav["corridor_max_y"]),
            openings, social,
        )

    def _stair_entry(self, stair) -> tuple[float, float]:
        return stair.local_to_world(-stair.enclosure_width * 0.23, stair.entry_offset)

    def _stair_landing_y(self, stair) -> float:
        return stair.entry_offset + min(5.9, stair.depth - 1.9)

    @staticmethod
    def _stair_flight_target_x(agent, centre_x: float, stair) -> float:
        usable_half_width = max(0.0, stair.width / 2 - agent.radius)
        local_x, _ = stair.world_to_local(agent.x, agent.y)
        return min(max(local_x, centre_x - usable_half_width), centre_x + usable_half_width)

    def _advance_stair_phase(self, agent) -> None:
        stair = self._stair(agent.selected_stair)
        entry_y = stair.entry_offset
        landing_y = self._stair_landing_y(stair)
        left_x, right_x = -stair.enclosure_width * 0.23, stair.enclosure_width * 0.23
        local_x, local_y = stair.world_to_local(agent.x, agent.y)
        tolerance = min(0.18, self.config["simulation"]["waypoint_tolerance"])
        if agent.phase == "stair_first_flight":
            target_x = self._stair_flight_target_x(agent, left_x, stair)
            agent.target_x, agent.target_y = stair.local_to_world(target_x, landing_y)
            if local_y >= landing_y - 1e-9:
                agent.phase = "stair_landing"
                agent.target_x, agent.target_y = stair.local_to_world(right_x, landing_y)
        elif agent.phase == "stair_landing":
            agent.target_x, agent.target_y = stair.local_to_world(right_x, landing_y)
            if local_x >= right_x - tolerance and local_y <= landing_y + 0.05:
                agent.phase = "stair_second_flight"
                target_x = self._stair_flight_target_x(agent, right_x, stair)
                agent.target_x, agent.target_y = stair.local_to_world(target_x, entry_y)
        else:
            target_x = self._stair_flight_target_x(agent, right_x, stair)
            agent.target_x, agent.target_y = stair.local_to_world(target_x, entry_y)
            if local_y <= entry_y + 0.05:
                agent.floor = agent.stair_from_floor - 1
                agent.z = agent.floor * self.building.floor_height
                agent.on_stair = False
                agent.phase = "corridor"
                agent.state = "evacuating"
                agent.stair_progress = 1.0

    def _update_stair_elevation(self, agent) -> None:
        stair = self._stair(agent.selected_stair)
        entry_y = stair.entry_offset
        landing_y = self._stair_landing_y(stair)
        run = max(landing_y - entry_y, 0.01)
        local_x, local_y = stair.world_to_local(agent.x, agent.y)
        top_z = agent.stair_from_floor * self.building.floor_height
        # Reserve 40/20/40 percent of progress for the two flights and landing.
        if agent.phase == "stair_first_flight":
            fraction = min(max((local_y - entry_y) / run, 0.0), 1.0)
            agent.stair_progress = 0.4 * fraction
            agent.z = top_z - self.building.floor_height * 0.5 * fraction
        elif agent.phase == "stair_landing":
            width = max(stair.enclosure_width * 0.46, 0.01)
            fraction = min(max((local_x + stair.enclosure_width * 0.23) / width, 0.0), 1.0)
            agent.stair_progress = 0.4 + 0.2 * fraction
            agent.z = top_z - self.building.floor_height * 0.5
        else:
            fraction = min(max((landing_y - local_y) / run, 0.0), 1.0)
            agent.stair_progress = 0.6 + 0.4 * fraction
            agent.z = top_z - self.building.floor_height * (0.5 + 0.5 * fraction)

    def _exit_target(self, agent, exit_door) -> tuple[float, float]:
        usable_width = max(0.0, exit_door.width - 2 * agent.radius)
        # Stable hashing distributes agents across the opening without adding RNG state.
        unit = ((agent.id * 2654435761 + 1013904223) % 10007) / 10006
        offset = (unit - 0.5) * usable_width
        angle = math.radians(exit_door.rotation)
        target = (
            exit_door.x + math.cos(angle) * offset,
            exit_door.y + math.sin(angle) * offset,
        )
        if self.building.schema_version == 2:
            normal = -math.sin(angle), math.cos(angle)
            candidates = [
                (target[0] + normal[0] * agent.radius, target[1] + normal[1] * agent.radius),
                (target[0] - normal[0] * agent.radius, target[1] - normal[1] * agent.radius),
            ]
            valid = [
                point for point in candidates
                if self.building.corridor_contains(0, *point, agent.radius)
            ]
            if valid:
                return valid[0]
        return target

    def _reached_exit(self, agent, exit_door, tolerance: float) -> bool:
        angle = math.radians(-exit_door.rotation)
        dx, dy = agent.x - exit_door.x, agent.y - exit_door.y
        along = dx * math.cos(angle) - dy * math.sin(angle)
        normal = dx * math.sin(angle) + dy * math.cos(angle)
        return abs(normal) <= tolerance and abs(along) <= exit_door.width / 2

    def _stair_counts(self):
        occupancy = Counter(a.selected_stair for a in self.agents if a.on_stair)
        queues = Counter(a.selected_stair for a in self.agents if a.state == "queued")
        return occupancy, queues

    def _stair(self, identifier):
        return next(s for s in self.building.stairs if s.id == identifier)

    def _exit(self, identifier):
        return next(e for e in self.building.exits if e.id == identifier)

    def _make_output_dir(self) -> Path:
        root = Path(self.config["outputs"]["root"])
        root.mkdir(parents=True, exist_ok=True)
        output = root / datetime.now().strftime("%Y-%m-%d_%H%M%S")
        suffix = 1
        while output.exists():
            output = root / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_{suffix}"
            suffix += 1
        output.mkdir(parents=True)
        return output
