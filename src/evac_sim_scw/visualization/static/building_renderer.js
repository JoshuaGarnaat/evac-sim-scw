import * as THREE from 'three';

const FLOOR_COUNT = 3;
const FLOOR_SLAB_COLOR = 0x253746;
const WALL_COLOR = 0xb9c8cf;
const HEATMAP_COLUMNS = 12;
const HEATMAP_ROWS = 6;

function createMaterial(color, opacity = 1) {
  return new THREE.MeshStandardMaterial({
    color,
    opacity,
    side: THREE.DoubleSide,
    transparent: opacity < 1,
  });
}

function addBox(parent, size, position, color, opacity = 1) {
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(...size),
    createMaterial(color, opacity),
  );
  mesh.position.set(...position);
  parent.add(mesh);
  return mesh;
}

function renderFloorSlab(building, floor, elevation, group) {
  const thickness = 0.18;
  const slabElevation = elevation - 0.12;
  const stairRooms = building.rooms
    .filter(room => room.floor === floor && room.kind === 'stairwell')
    .sort((left, right) => left.x - right.x);

  if (stairRooms.length === 0) {
    addBox(
      group,
      [building.dimensions.width, thickness, building.dimensions.depth],
      [building.dimensions.width / 2, slabElevation, building.dimensions.depth / 2],
      FLOOR_SLAB_COLOR,
      0.92,
    );
    return;
  }

  const openingStartY = stairRooms[0].y;
  const openingEndY = stairRooms[0].y + stairRooms[0].depth;
  addBox(
    group,
    [building.dimensions.width, thickness, openingStartY],
    [building.dimensions.width / 2, slabElevation, openingStartY / 2],
    FLOOR_SLAB_COLOR,
    0.92,
  );

  if (openingEndY < building.dimensions.depth) {
    addBox(
      group,
      [building.dimensions.width, thickness, building.dimensions.depth - openingEndY],
      [
        building.dimensions.width / 2,
        slabElevation,
        (openingEndY + building.dimensions.depth) / 2,
      ],
      FLOOR_SLAB_COLOR,
      0.92,
    );
  }

  let cursorX = 0;
  stairRooms.forEach(room => {
    if (room.x > cursorX) {
      addBox(
        group,
        [room.x - cursorX, thickness, openingEndY - openingStartY],
        [(cursorX + room.x) / 2, slabElevation, (openingStartY + openingEndY) / 2],
        FLOOR_SLAB_COLOR,
        0.92,
      );
    }
    cursorX = room.x + room.width;
  });

  if (cursorX < building.dimensions.width) {
    addBox(
      group,
      [building.dimensions.width - cursorX, thickness, openingEndY - openingStartY],
      [
        (cursorX + building.dimensions.width) / 2,
        slabElevation,
        (openingStartY + openingEndY) / 2,
      ],
      FLOOR_SLAB_COLOR,
      0.92,
    );
  }
}

function renderRoomWalls(room, door, elevation, group) {
  const wallHeight = 1.3;
  const wallThickness = 0.1;
  const wallElevation = elevation + wallHeight / 2;

  addBox(
    group,
    [wallThickness, wallHeight, room.depth],
    [room.x, wallElevation, room.y + room.depth / 2],
    WALL_COLOR,
    0.3,
  );
  addBox(
    group,
    [wallThickness, wallHeight, room.depth],
    [room.x + room.width, wallElevation, room.y + room.depth / 2],
    WALL_COLOR,
    0.3,
  );

  if (room.kind === 'stairwell') {
    addBox(
      group,
      [room.width, wallHeight, wallThickness],
      [room.x + room.width / 2, wallElevation, room.y + room.depth],
      WALL_COLOR,
      0.3,
    );
    return;
  }

  const corridorSide = door.y === room.y ? 'south' : 'north';
  const outerWallY = corridorSide === 'south' ? room.y + room.depth : room.y;
  addBox(
    group,
    [room.width, wallHeight, wallThickness],
    [room.x + room.width / 2, wallElevation, outerWallY],
    WALL_COLOR,
    0.3,
  );

  const leftSegmentWidth = door.x - door.width / 2 - room.x;
  const rightSegmentWidth = room.x + room.width - (door.x + door.width / 2);
  if (leftSegmentWidth > 0) {
    addBox(
      group,
      [leftSegmentWidth, wallHeight, wallThickness],
      [room.x + leftSegmentWidth / 2, wallElevation, door.y],
      WALL_COLOR,
      0.3,
    );
  }
  if (rightSegmentWidth > 0) {
    addBox(
      group,
      [rightSegmentWidth, wallHeight, wallThickness],
      [door.x + door.width / 2 + rightSegmentWidth / 2, wallElevation, door.y],
      WALL_COLOR,
      0.3,
    );
  }
}

function renderStairFlight(stair, floor, firstFlight, floorHeight, entrance, landing, group) {
  const enclosureWidth = stair.enclosure_width || stair.width * 2.4;
  const flightOffset = enclosureWidth * 0.23;
  const run = landing - entrance;
  const rise = floorHeight * 0.5;
  const slopeLength = Math.hypot(run, rise);
  const x = stair.x + (firstFlight ? -flightOffset : flightOffset);
  const top = firstFlight ? floor * floorHeight : floor * floorHeight - rise;

  const mesh = addBox(
    group,
    [stair.width * 0.96, 0.14, slopeLength],
    [x, top - rise / 2, (entrance + landing) / 2],
    firstFlight ? 0xc49a62 : 0xb8834f,
  );
  mesh.rotation.x = firstFlight ? Math.atan2(rise, run) : -Math.atan2(rise, run);
}

function renderFloor(building, floor, group) {
  const floorHeight = building.dimensions.floor_height;
  const elevation = floor * floorHeight;
  renderFloorSlab(building, floor, elevation, group);

  building.corridors
    .filter(corridor => corridor.floor === floor)
    .forEach(corridor => {
      addBox(
        group,
        [corridor.width, 0.035, corridor.depth],
        [corridor.x + corridor.width / 2, elevation + 0.02, corridor.y + corridor.depth / 2],
        0x6c8292,
        0.78,
      );
    });

  building.rooms
    .filter(room => room.floor === floor)
    .forEach((room, index) => {
      const door = building.doors.find(
        candidate => candidate.floor === floor && candidate.connects[0] === room.id,
      );

      if (room.kind !== 'stairwell') {
        addBox(
          group,
          [room.width, 0.025, room.depth],
          [room.x + room.width / 2, elevation + 0.03, room.y + room.depth / 2],
          index % 2 ? 0x345366 : 0x3d5d70,
          0.74,
        );
      }
      renderRoomWalls(room, door, elevation, group);
    });

  building.doors
    .filter(door => door.floor === floor)
    .forEach(door => {
      addBox(
        group,
        [door.width, 0.035, 0.18],
        [door.x, elevation + 0.06, door.y],
        door.kind === 'stair_entry' ? 0xff9f43 : 0xe0bd77,
        0.95,
      );
    });
}

function renderExits(building, groundFloorGroup) {
  building.exits.forEach(exit => {
    const isSideExit = exit.x < 1 || exit.x > building.dimensions.width - 1;
    const size = isSideExit ? [0.18, 2.5, exit.width] : [exit.width, 2.5, 0.18];
    const marker = addBox(
      groundFloorGroup,
      size,
      [exit.x, 1.25, exit.y],
      0x37ef79,
      0.75,
    );
    marker.material.emissive.setHex(0x126b34);
  });
}

function renderStairs(building, floorGroups) {
  const floorHeight = building.dimensions.floor_height;
  building.stairs.forEach(stair => {
    for (let floor = 1; floor < FLOOR_COUNT; floor += 1) {
      const group = floorGroups[floor - 1];
      const enclosureWidth = stair.enclosure_width || stair.width * 2.4;
      const entrance = building.navigation.corridor_max_y;
      const landing = entrance + Math.min(5.9, stair.depth - 1.9);
      const run = landing - entrance;
      const railElevation = floor * floorHeight - floorHeight * 0.5;

      renderStairFlight(stair, floor, true, floorHeight, entrance, landing, group);
      renderStairFlight(stair, floor, false, floorHeight, entrance, landing, group);
      addBox(
        group,
        [enclosureWidth * 0.94, 0.14, stair.width],
        [stair.x, railElevation, landing + stair.width / 2],
        0xd7b47e,
      );
      addBox(
        group,
        [0.07, 1, run],
        [stair.x - enclosureWidth * 0.49, railElevation, landing - run / 2],
        0x9faab0,
        0.9,
      );
      addBox(
        group,
        [0.07, 1, run],
        [stair.x + enclosureWidth * 0.49, railElevation, landing - run / 2],
        0x9faab0,
        0.9,
      );
    }
  });
}

export function renderBuilding(scene, building) {
  const floorGroups = Array.from({ length: FLOOR_COUNT }, () => new THREE.Group());
  floorGroups.forEach(group => scene.add(group));

  floorGroups.forEach((group, floor) => renderFloor(building, floor, group));
  renderExits(building, floorGroups[0]);
  renderStairs(building, floorGroups);
  return floorGroups;
}

export function createHeatmap(scene, building) {
  const cellWidth = building.dimensions.width / HEATMAP_COLUMNS;
  const cellDepth = building.dimensions.depth / HEATMAP_ROWS;
  const cellsPerFloor = HEATMAP_COLUMNS * HEATMAP_ROWS;
  const geometry = new THREE.BoxGeometry(cellWidth - 0.08, 0.025, cellDepth - 0.08);
  const floorMeshes = [];
  const dummy = new THREE.Object3D();
  const color = new THREE.Color();

  for (let floor = 0; floor < FLOOR_COUNT; floor += 1) {
    const material = new THREE.MeshBasicMaterial({
      depthWrite: false,
      opacity: 0.3,
      transparent: true,
      vertexColors: true,
    });
    const mesh = new THREE.InstancedMesh(geometry, material, cellsPerFloor);

    let index = 0;
    for (let row = 0; row < HEATMAP_ROWS; row += 1) {
      for (let column = 0; column < HEATMAP_COLUMNS; column += 1) {
        dummy.position.set(
          column * cellWidth + cellWidth / 2,
          floor * building.dimensions.floor_height + 0.07,
          row * cellDepth + cellDepth / 2,
        );
        dummy.updateMatrix();
        mesh.setMatrixAt(index, dummy.matrix);
        mesh.setColorAt(index, new THREE.Color(0x123d20));
        index += 1;
      }
    }

    mesh.instanceMatrix.needsUpdate = true;
    mesh.instanceColor.needsUpdate = true;
    scene.add(mesh);
    floorMeshes.push(mesh);
  }

  function update(agents) {
    const counts = new Uint16Array(FLOOR_COUNT * cellsPerFloor);
    agents.forEach(agent => {
      if (agent[5] === 8) {
        return;
      }

      const column = THREE.MathUtils.clamp(Math.floor(agent[1] / cellWidth), 0, HEATMAP_COLUMNS - 1);
      const row = THREE.MathUtils.clamp(Math.floor(agent[2] / cellDepth), 0, HEATMAP_ROWS - 1);
      const floor = THREE.MathUtils.clamp(agent[4], 0, FLOOR_COUNT - 1);
      counts[floor * cellsPerFloor + row * HEATMAP_COLUMNS + column] += 1;
    });

    floorMeshes.forEach((mesh, floor) => {
      for (let index = 0; index < cellsPerFloor; index += 1) {
        const density = Math.min(1, counts[floor * cellsPerFloor + index] / 18);
        color.setHSL(0.33 * (1 - density), 0.92, 0.18 + density * 0.35);
        mesh.setColorAt(index, color);
      }
      mesh.instanceColor.needsUpdate = true;
    });
  }

  function setFloor(selectedFloor) {
    floorMeshes.forEach((mesh, floor) => {
      mesh.visible = selectedFloor === 'all' || Number(selectedFloor) === floor;
    });
  }

  return { groups: floorMeshes, setFloor, update };
}
