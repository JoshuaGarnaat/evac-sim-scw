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
from ..agents.social_force import movement_force, rectangular_wall_force
from ..geometry.building import Building
from ..geometry.spatial_index import SpatialGrid
from ..replay.writer import ReplayWriter
from .congestion import crowd_pressure
from .density import update_local_density
from .evacuation import reached
from .metrics import MetricsCollector
from .stair_movement import advance_stair_groups, stair_lane_count


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
        self.stair_lane_last_entry = {
            (stair.id, floor, lane): -100.0
            for stair in self.building.stairs
            for floor in stair.floors if floor > 0
            for lane in range(stair_lane_count(stair, config))
        }
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
        self._admit_stair_queues(occupancy)
        for agent in advance_stair_groups(self.agents, self.building, dt, self.config):
            self.metrics.record_stair(self.time, agent.selected_stair, agent.floor, "leave", agent.id)
            agent.hesitation_until = self.time + self.config["movement"]["landing_adjustment_time"]
        for agent in self.agents:
            if agent.state == "exited":
                continue
            if agent.state == "waiting":
                if self.time < agent.reaction_time:
                    continue
                agent.state = "evacuating"
                agent.last_motion_time = self.time
            if agent.on_stair:
                continue
            self._advance_phase(agent, route_load)
            if agent.state in {"queued", "exited"} or self.time < agent.hesitation_until:
                agent.vx = agent.vy = 0.0
                continue
            neighbor_ids = self.grid.neighbors(agent.floor, agent.x, agent.y)
            neighbors = [self.by_id[index] for index in neighbor_ids]
            factor = density_speed_factor(agent.local_density, self.config)
            desired = agent.preferred_speed * factor
            agent.ax, agent.ay = movement_force(agent, agent.target_x, agent.target_y, desired, neighbors, self.config["social_force"])
            stalled_for = self.time - agent.last_motion_time
            if agent.phase == "corridor" and stalled_for > 3.0 and agent.local_density < 1.5:
                dx, dy = agent.target_x - agent.x, agent.target_y - agent.y
                length = max(math.hypot(dx, dy), 0.01)
                direction = -1.0 if agent.id % 2 else 1.0
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
            old_x, old_y = agent.x, agent.y
            agent.x += agent.vx * dt
            agent.y += agent.vy * dt
            cx, cy = separate(agent, neighbors)
            agent.x += cx
            agent.y += cy
            self._constrain(agent)
            distance = math.hypot(agent.x - old_x, agent.y - old_y)
            if distance >= 0.01:
                agent.last_motion_time += self.time
            agent.distance_walked += distance
            agent.speed_sum += agent.speed
            agent.speed_samples += 1
            agent.pressure = crowd_pressure(agent, self.config)
            agent.state = classify_state(agent, self.config)
            if agent.state == "congested":
                agent.congested_time += dt

    def _advance_phase(self, agent, queues: dict[str, int]) -> None:
        tolerance = self.config["simulation"]["waypoint_tolerance"]
        if agent.phase == "room" and reached(agent, agent.target_x, agent.target_y, tolerance):
            if agent.id not in self.door_seen:
                self.metrics.record_door(self.time, f"D_{agent.classroo_id}", agent.id)
                self.door_seen.add(agent.id)
            agent.phase = "door_transition"
            nav = self.building.raw["navigation"]
            door = self.building.room_door(agent.classroo_id)
            agent.target_y = nav["corridor_min_y"] + 0.45 if door.y < nav["corridor_center_y"] else nav["corridor_max_y"] - 0.45
        elif agent.phase == "door_transition" and reached(agent, agent.target_x, agent.target_y, tolerance):
            agent.phase = "corridor"
        if agent.phase != "corridor":
            return
        if self.time - agent.last_route_check >= self.config["corridor"]["reconsider_interval"]:
            self._maybe_reroute(agent, queues)
        if agent.floor > 0:
            stair = self._stair(agent.selected_stair)
            entry_x, entry_y = self._stair_entry(stair)
            agent.target_x, agent.target_y = entry_x, entry_y
            if reached(agent, entry_x, entry_y, tolerance + stair.width * 0.2):
                agent.state = "queued"
                agent.queue_entered = agent.queue_entered or self.time
                agent.vx = agent.vy = 0.0
        else:
            exit_door = self._exit(agent.selected_exit)
            agent.target_x, agent.target_y = self._exit_target(agent, exit_door)
            if self._reached_exit(agent, exit_door, tolerance):
                agent.state = "exited"
                agent.evacuation_time = self.time
                agent.vx = agent.vy = 0.0
                self.evacuated += 1
                self.metrics.record_exit(self.time, exit_door.id, agent.id)

    def _admit_stair_queues(self, occupancy: Counter) -> None:
        specific_flow = self.config["stair_congestion"]["entry_specific_flow"]
        for stair in self.building.stairs:
            capacity = max(1, int(stair.width * stair.path_length * stair.capacity_per_m2))
            lane_count = stair_lane_count(stair, self.config)
            interval = lane_count / max(specific_flow * stair.width, 0.1)
            for floor in (value for value in stair.floors if value > 0):
                candidates = sorted(
                    (
                        a for a in self.agents
                        if a.state == "queued" and a.selected_stair == stair.id and a.floor == floor
                    ),
                    key=lambda a: (a.queue_entered or self.time, a.id),
                )
                for lane in range(lane_count):
                    if not candidates or occupancy[stair.id] >= capacity:
                        break
                    last_entry = self.stair_lane_last_entry[(stair.id, floor, lane)]
                    entrance_clear = all(
                        not (
                            a.on_stair and a.selected_stair != stair.id
                            and a.stair_from_floor != floor and a.stair_lane != lane
                            and a.stair_progress * stair.path_length < self.config["stair_congestion"]["entry_clearance"]
                        )
                        for a in self.agents
                    )
                    if self.time - last_entry < interval or not entrance_clear:
                        continue
                    agent = candidates.pop(0)
                    agent.state = "entering_stairwell"
                    agent.on_stair = True
                    agent.stair_from_floor = agent.floor
                    agent.stair_lane = lane
                    agent.stair_progress = 0.0
                    agent.current_stair_speed = 0.0
                    agent.queue_entered = None
                    agent.vx = agent.vy = 0.0
                    self.stair_lane_last_entry[(stair.id, floor, lane)] = self.time
                    occupancy[stair.id] += 1
                    self.metrics.record_stair(self.time, stair.id, agent.floor, "enter", agent.id)

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
            current_cost = route_cost(agent, current_exit, current_stair, queues, self.config)
            if old_route.estimated_cost < current_cost * (1.0 - threshold):
                agent.selected_exit, agent.selected_stair = old_route.exit_id, old_route.stair_id
                agent.reroutes += 1
                agent.state = "rerouting"

    def _constrain(self, agent) -> None:
        agent.x = min(max(agent.x, 0.1), self.building.width - 0.1)
        agent.y = min(max(agent.y, 0.1), self.building.depth - 0.1)
        if agent.phase == "corridor" and agent.floor > 0:
            nav = self.building.raw["navigation"]
            agent.y = min(max(agent.y, nav["corridor_min_y"]), nav["corridor_max_y"])

    def _wall_force(self, agent) -> tuple[float, float]:
        social = self.config["social_force"]
        if agent.phase == "room":
            room = next(r for r in self.building.rooms if r.id == agent.classroom_id)
            door = self.building.room_door(agent.classroom_id)
            side = "north" if door.y > room.center[1] else "south"
            return rectangular_wall_force(
                agent, (room.x, room.x + room.width, room.y, room.y + room.depth),
                [(side, door.x, door.width)], social,
            )
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
        return (
            stair.x - stair.enclosure_width * 0.23,
            self.building.raw["navigation"]["corridor_max_y"],
        )

    def _exit_target(self, agent, exit_door) -> tuple[float, float]:
        usable_width = max(0.0, exit_door.width - 2 * agent.radius)
        unit = ((agent.id * 2654435761 + 1013904223) % 10007) / 10006
        offset = (unit - 0.5) * usable_width
        if exit_door.x < 1.0 or exit_door.x > self.building.width - 1.0:
            return exit_door.x, exit_door.y + offset
        return exit_door.x + offset, exit_door.y

    def _reached_exit(self, agent, exit_door, tolerance: float) -> bool:
        if exit_door.x < 1.0 or exit_door.x > self.building.width - 1.0:
            return abs(agent.x - exit_door.x) <= tolerance and abs(agent.y - exit_door.y) <= exit_door.width / 2
        return abs(agent.y - exit_door.y) <= tolerance and abs(agent.x - exit_door.x) <= exit_door.width / 2

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
