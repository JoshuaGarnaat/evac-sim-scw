import * as THREE from 'three';

const LOOK_SENSITIVITY = 0.0022;
const WALK_SPEED = 11;
const SPRINT_SPEED = 28;

export function installFreeCamera(camera, canvas) {
  // Install controls and return the per-frame camera updater.
  const pressedKeys = new Set();
  const direction = new THREE.Vector3();
  const right = new THREE.Vector3();
  const worldUp = new THREE.Vector3(0, 1, 0);
  let yaw = -0.55;
  let pitch = -0.35;

  document.addEventListener('keydown', event => pressedKeys.add(event.code));
  document.addEventListener('keyup', event => pressedKeys.delete(event.code));
  canvas.addEventListener('click', () => canvas.requestPointerLock());
  document.addEventListener('mousemove', event => {
    if (document.pointerLockElement !== canvas) {
      return;
    }

    yaw += event.movementX * LOOK_SENSITIVITY;
    pitch = THREE.MathUtils.clamp(
      pitch - event.movementY * LOOK_SENSITIVITY,
      -1.48,
      1.48,
    );
  });

  function update(delta) {
    // Move along the camera's current view plane using the pressed keys.
    direction.set(
      Math.sin(yaw) * Math.cos(pitch),
      Math.sin(pitch),
      -Math.cos(yaw) * Math.cos(pitch),
    );
    camera.lookAt(camera.position.clone().add(direction));
    right.crossVectors(direction, worldUp).normalize();

    const isSprinting = pressedKeys.has('ShiftLeft') || pressedKeys.has('ShiftRight');
    const distance = (isSprinting ? SPRINT_SPEED : WALK_SPEED) * delta;
    if (pressedKeys.has('KeyW')) camera.position.addScaledVector(direction, distance);
    if (pressedKeys.has('KeyS')) camera.position.addScaledVector(direction, -distance);
    if (pressedKeys.has('KeyA')) camera.position.addScaledVector(right, -distance);
    if (pressedKeys.has('KeyD')) camera.position.addScaledVector(right, distance);
    if (pressedKeys.has('Space')) camera.position.y += distance;
    if (pressedKeys.has('ControlLeft') || pressedKeys.has('ControlRight')) {
      camera.position.y -= distance;
    }
  }

  function overview() {
    // Reset to the default elevated view of the whole building.
    camera.position.set(45, 62, 69);
    yaw = 0;
    pitch = -0.65;
  }

  overview();
  return { update, overview };
}
