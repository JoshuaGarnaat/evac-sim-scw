import * as THREE from 'three';

export function installFreeCamera(camera, canvas) {
  const keys = new Set();
  let yaw = -0.55, pitch = -0.35;
  document.addEventListener('keydown', e => keys.add(e.code));
  document.addEventListener('keyup', e => keys.delete(e.code));
  canvas.addEventListener('click', () => canvas.requestPointerLock());
  document.addEventListener('mousemove', e => {
    if (document.pointerLockElement !== canvas) return;
    yaw += e.movementX * 0.0022;
    pitch = THREE.MathUtils.clamp(pitch - e.movementY * 0.0022, -1.48, 1.48);
  });
  const direction = new THREE.Vector3(), right = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
  function update(dt) {
    direction.set(Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), -Math.cos(yaw) * Math.cos(pitch));
    camera.lookAt(camera.position.clone().add(direction));
    right.crossVectors(direction, up).normalize();
    const speed = (keys.has('ShiftLeft') || keys.has('ShiftRight') ? 28 : 11) * dt;
    if (keys.has('KeyW')) camera.position.addScaledVector(direction, speed);
    if (keys.has('KeyS')) camera.position.addScaledVector(direction, -speed);
    if (keys.has('KeyA')) camera.position.addScaledVector(right, -speed);
    if (keys.has('KeyD')) camera.position.addScaledVector(right, speed);
    if (keys.has('Space')) camera.position.y += speed;
    if (keys.has('ControlLeft') || keys.has('ControlRight')) camera.position.y -= speed;
  }
  function overview() {
    camera.position.set(45, 62, 69); yaw = 0; pitch = -0.65;
  }
  overview();
  return { update, overview };
}
