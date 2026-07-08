import * as THREE from 'three';

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

function localPoint(item, x, y) {
  const angle = THREE.MathUtils.degToRad(item.rotation || 0);
  return [
    item.x + x * Math.cos(angle) - y * Math.sin(angle),
    item.y + x * Math.sin(angle) + y * Math.cos(angle),
  ];
}

function addLocalBox(parent, item, size, localPosition, elevation, color, opacity = 1) {
  const [x, z] = localPoint(item, localPosition[0], localPosition[1]);
  const mesh = addBox(parent, size, [x, elevation, z], color, opacity);
  mesh.rotation.y = -THREE.MathUtils.degToRad(item.rotation || 0);
  return mesh;
}

function renderFloorSlab(building, floor, elevation, group) {
  if ((building.schema_version || 1) >= 2) {
    return;
  }
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

  if (room.kind === 'stairwell') {
    addLocalBox(group, room, [wallThickness, wallHeight, room.depth], [0, room.depth / 2], wallElevation, WALL_COLOR, 0.3);
    addLocalBox(group, room, [wallThickness, wallHeight, room.depth], [room.width, room.depth / 2], wallElevation, WALL_COLOR, 0.3);
    addLocalBox(group, room, [room.width, wallHeight, wallThickness], [room.width / 2, room.depth], wallElevation, WALL_COLOR, 0.3);
    return;
  }

  if (!door) {
    addLocalBox(group, room, [wallThickness, wallHeight, room.depth], [0, room.depth / 2], wallElevation, WALL_COLOR, 0.3);
    addLocalBox(group, room, [wallThickness, wallHeight, room.depth], [room.width, room.depth / 2], wallElevation, WALL_COLOR, 0.3);
    addLocalBox(group, room, [room.width, wallHeight, wallThickness], [room.width / 2, 0], wallElevation, WALL_COLOR, 0.3);
    addLocalBox(group, room, [room.width, wallHeight, wallThickness], [room.width / 2, room.depth], wallElevation, WALL_COLOR, 0.3);
    return;
  }

  const corridorSide = door.side || (door.y === room.y ? 'south' : 'north');
  if (corridorSide !== 'west') {
    addLocalBox(group, room, [wallThickness, wallHeight, room.depth], [0, room.depth / 2], wallElevation, WALL_COLOR, 0.3);
  }
  if (corridorSide !== 'east') {
    addLocalBox(group, room, [wallThickness, wallHeight, room.depth], [room.width, room.depth / 2], wallElevation, WALL_COLOR, 0.3);
  }
  const [doorLocalX, doorLocalY] = (() => {
    const angle = -THREE.MathUtils.degToRad(room.rotation || 0);
    const dx = door.x - room.x;
    const dy = door.y - room.y;
    return [dx * Math.cos(angle) - dy * Math.sin(angle), dx * Math.sin(angle) + dy * Math.cos(angle)];
  })();
  const opposite = corridorSide === 'south' ? room.depth : 0;
  addLocalBox(group, room, [room.width, wallHeight, wallThickness], [room.width / 2, opposite], wallElevation, WALL_COLOR, 0.3);

  if (corridorSide === 'east' || corridorSide === 'west') {
    const wallX = corridorSide === 'east' ? room.width : 0;
    const bottom = doorLocalY - door.width / 2;
    const top = room.depth - (doorLocalY + door.width / 2);
    if (bottom > 0) addLocalBox(group, room, [wallThickness, wallHeight, bottom], [wallX, bottom / 2], wallElevation, WALL_COLOR, 0.3);
    if (top > 0) addLocalBox(group, room, [wallThickness, wallHeight, top], [wallX, doorLocalY + door.width / 2 + top / 2], wallElevation, WALL_COLOR, 0.3);
    return;
  }
  const wallY = corridorSide === 'north' ? room.depth : 0;
  const leftSegmentWidth = doorLocalX - door.width / 2;
  const rightSegmentWidth = room.width - (doorLocalX + door.width / 2);
  if (leftSegmentWidth > 0) {
    addLocalBox(group, room, [leftSegmentWidth, wallHeight, wallThickness], [leftSegmentWidth / 2, wallY], wallElevation, WALL_COLOR, 0.3);
  }
  if (rightSegmentWidth > 0) {
    addLocalBox(group, room, [rightSegmentWidth, wallHeight, wallThickness], [doorLocalX + door.width / 2 + rightSegmentWidth / 2, wallY], wallElevation, WALL_COLOR, 0.3);
  }
}

function renderStairFlight(stair, floor, firstFlight, floorHeight, entrance, landing, frame) {
  const enclosureWidth = stair.enclosure_width || stair.width * 2.4;
  const flightOffset = enclosureWidth * 0.23;
  const run = landing - entrance;
  const rise = floorHeight * 0.5;
  const slopeLength = Math.hypot(run, rise);
  const localX = firstFlight ? -flightOffset : flightOffset;
  const top = firstFlight ? floor * floorHeight : floor * floorHeight - rise;

  const mesh = addBox(
    frame,
    [stair.width * 0.96, 0.14, slopeLength],
    [localX, top - rise / 2, (entrance + landing) / 2],
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
      addLocalBox(group, corridor, [corridor.width, 0.035, corridor.depth], [corridor.width / 2, corridor.depth / 2], elevation + 0.02, 0x6c8292, 0.78);
    });

  building.rooms
    .filter(room => room.floor === floor)
    .forEach((room, index) => {
      const door = building.doors.find(
        candidate => candidate.floor === floor && candidate.connects[0] === room.id,
      );

      if (room.kind !== 'stairwell') {
        addLocalBox(group, room, [room.width, 0.025, room.depth], [room.width / 2, room.depth / 2], elevation + 0.03, index % 2 ? 0x345366 : 0x3d5d70, 0.74);
      }
      renderRoomWalls(room, door, elevation, group);
    });

  building.doors
    .filter(door => door.floor === floor)
    .forEach(door => {
      const marker = addBox(
        group,
        [door.width, 0.035, 0.18],
        [door.x, elevation + 0.06, door.y],
        door.kind === 'stair_entry' ? 0xff9f43 : 0xe0bd77,
        0.95,
      );
      marker.rotation.y = -THREE.MathUtils.degToRad(door.rotation || 0);
    });
}

function renderExits(building, groundFloorGroup) {
  building.exits.forEach(exit => {
    const size = [exit.width, 2.5, 0.18];
    const marker = addBox(
      groundFloorGroup,
      size,
      [exit.x, 1.25, exit.y],
      0x37ef79,
      0.75,
    );
    marker.material.emissive.setHex(0x126b34);
    marker.rotation.y = -THREE.MathUtils.degToRad(exit.rotation || 0);
  });
}

function renderStairs(building, floorGroups) {
  const floorHeight = building.dimensions.floor_height;
  building.stairs.forEach(stair => {
    stair.floors.filter(floor => floor > 0).forEach(floor => {
      const group = floorGroups[floor - 1];
      if (!group) return;
      const enclosureWidth = stair.enclosure_width || stair.width * 2.4;
      const entrance = stair.entry_offset || 0;
      const landing = entrance + Math.min(5.9, stair.depth - 1.9);
      const run = landing - entrance;
      const railElevation = floor * floorHeight - floorHeight * 0.5;
      const frame = new THREE.Group();
      frame.position.set(stair.x, 0, stair.y);
      frame.rotation.y = -THREE.MathUtils.degToRad(stair.rotation || 0);
      group.add(frame);

      renderStairFlight(stair, floor, true, floorHeight, entrance, landing, frame);
      renderStairFlight(stair, floor, false, floorHeight, entrance, landing, frame);
      addBox(frame, [enclosureWidth * 0.94, 0.14, stair.width], [0, railElevation, landing + stair.width / 2], 0xd7b47e);
      addBox(frame, [0.07, 1, run], [-enclosureWidth * 0.49, railElevation, entrance + run / 2], 0x9faab0, 0.9);
      addBox(frame, [0.07, 1, run], [enclosureWidth * 0.49, railElevation, entrance + run / 2], 0x9faab0, 0.9);
    });
  });
}

export function renderBuilding(scene, building) {
  const floorCount = Math.max(...building.floors.map(floor => floor.level)) + 1;
  const floorGroups = Array.from({ length: floorCount }, () => new THREE.Group());
  floorGroups.forEach(group => scene.add(group));

  floorGroups.forEach((group, floor) => renderFloor(building, floor, group));
  renderExits(building, floorGroups[0]);
  renderStairs(building, floorGroups);
  return floorGroups;
}

export function createHeatmap(scene, building) {
  const floorCount = Math.max(...building.floors.map(floor => floor.level)) + 1;
  const cellWidth = building.dimensions.width / HEATMAP_COLUMNS;
  const cellDepth = building.dimensions.depth / HEATMAP_ROWS;
  const cellsPerFloor = HEATMAP_COLUMNS * HEATMAP_ROWS;
  const geometry = new THREE.BoxGeometry(cellWidth - 0.08, 0.025, cellDepth - 0.08);
  const floorMeshes = [];
  const dummy = new THREE.Object3D();
  const color = new THREE.Color();

  for (let floor = 0; floor < floorCount; floor += 1) {
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
    const counts = new Uint16Array(floorCount * cellsPerFloor);
    agents.forEach(agent => {
      if (agent[5] === 8) {
        return;
      }

      const column = THREE.MathUtils.clamp(Math.floor(agent[1] / cellWidth), 0, HEATMAP_COLUMNS - 1);
      const row = THREE.MathUtils.clamp(Math.floor(agent[2] / cellDepth), 0, HEATMAP_ROWS - 1);
      const floor = THREE.MathUtils.clamp(agent[4], 0, floorCount - 1);
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
