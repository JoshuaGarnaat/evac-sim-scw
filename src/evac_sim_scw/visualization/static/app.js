import * as THREE from 'three';

import { createHeatmap, renderBuilding } from './building_renderer.js';
import { installFreeCamera } from './camera.js';
import { framePair, loadReplay } from './replay.js';

const MAX_FRAME_DELTA = 0.05;
const HUD_UPDATE_INTERVAL = 0.1;
const HEATMAP_UPDATE_INTERVAL = 0.25;
const FPS_SAMPLE_INTERVAL_MS = 1000;
const LOW_FPS_THRESHOLD = 42;

const elements = {
  canvas: document.querySelector('#scene'),
  evacuated: document.querySelector('#evacuated'),
  floor: document.querySelector('#floor'),
  fps: document.querySelector('#fps'),
  loading: document.querySelector('#loading'),
  overview: document.querySelector('#overview'),
  play: document.querySelector('#play'),
  progress: document.querySelector('#progress'),
  remaining: document.querySelector('#remaining'),
  speed: document.querySelector('#speed'),
  timeline: document.querySelector('#timeline'),
  timer: document.querySelector('#timer'),
};

const renderer = new THREE.WebGLRenderer({
  canvas: elements.canvas,
  antialias: true,
  powerPreference: 'high-performance',
});
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.35));

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x071018);
scene.fog = new THREE.Fog(0x071018, 80, 180);

const camera = new THREE.PerspectiveCamera(58, innerWidth / innerHeight, 0.08, 350);
const cameraControls = installFreeCamera(camera, elements.canvas);

scene.add(new THREE.HemisphereLight(0xcdeaff, 0x16232d, 2.5));
const sun = new THREE.DirectionalLight(0xffffff, 2);
sun.position.set(30, 70, 20);
scene.add(sun);

const playback = {
  currentTime: 0,
  duration: 1,
  floor: 'all',
  playing: true,
  speed: 1,
};

function formatTime(seconds) {
  const minutes = String(Math.floor(seconds / 60)).padStart(2, '0');
  const remainder = (seconds % 60).toFixed(1).padStart(4, '0');
  return `${minutes}:${remainder}`;
}

function updateViewport() {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight, false);
}

async function startViewer() {
  const { metadata, frames } = await loadReplay();
  playback.duration = frames.at(-1).t;

  const floorGroups = renderBuilding(scene, metadata.building);
  const heatmap = createHeatmap(scene, metadata.building);
  const agents = createAgentMesh(metadata.population);
  scene.add(agents);

  bindControls(floorGroups, heatmap);
  elements.loading.remove();
  runAnimationLoop({ agents, frames, heatmap, metadata });
}

function createAgentMesh(population) {
  const geometry = new THREE.CapsuleGeometry(0.23, 0.72, 2, 5);
  const material = new THREE.MeshStandardMaterial({ color: 0x4cc9ff });
  const mesh = new THREE.InstancedMesh(geometry, material, population);
  mesh.instanceMatrix.setUsage(THREE.StreamDrawUsage);
  mesh.frustumCulled = false;
  return mesh;
}

function bindControls(floorGroups, heatmap) {
  elements.play.addEventListener('click', () => {
    playback.playing = !playback.playing;
    elements.play.textContent = playback.playing ? 'Pause' : 'Play';
  });

  elements.speed.addEventListener('change', event => {
    playback.speed = Number(event.target.value);
  });

  elements.floor.addEventListener('change', event => {
    playback.floor = event.target.value;
    floorGroups.forEach((group, floor) => {
      group.visible = playback.floor === 'all' || Number(playback.floor) === floor;
    });
    heatmap.setFloor(playback.floor);
  });

  elements.overview.addEventListener('click', cameraControls.overview);
  elements.timeline.addEventListener('input', event => {
    playback.currentTime = playback.duration * Number(event.target.value) / 1000;
  });
}

function runAnimationLoop({ agents, frames, heatmap, metadata }) {
  const dummy = new THREE.Object3D();
  const color = new THREE.Color();
  let previousTimestamp = performance.now();
  let lastColorFrame = -1;
  let lastHeatmapUpdate = -1;
  let lastHudUpdate = -1;
  let fpsFrames = 0;
  let fpsWindowStart = performance.now();
  let lowFpsWindows = 0;

  function drawReplayFrame() {
    const { a, b, alpha, index } = framePair(frames, playback.currentTime);
    const shouldUpdateColors = index !== lastColorFrame;

    a.a.forEach((agent, agentIndex) => {
      const nextAgent = b.a[agentIndex] ?? agent;
      const useNextState = alpha > 0.5;
      const state = useNextState ? nextAgent[5] : agent[5];
      const floor = useNextState ? nextAgent[4] : agent[4];
      const isVisible = playback.floor === 'all' || Number(playback.floor) === floor;

      const x = THREE.MathUtils.lerp(agent[1], nextAgent[1], alpha);
      const planY = THREE.MathUtils.lerp(agent[2], nextAgent[2], alpha);
      const elevation = THREE.MathUtils.lerp(agent[3], nextAgent[3], alpha);
      dummy.position.set(x, elevation + 0.5, planY);
      dummy.scale.setScalar(state === 8 || !isVisible ? 0.0001 : 1);
      dummy.updateMatrix();
      agents.setMatrixAt(agentIndex, dummy.matrix);

      if (shouldUpdateColors) {
        const density = Math.min(1, agent[7] / 5);
        color.setHSL(0.33 * (1 - density), 0.92, 0.48);
        agents.setColorAt(agentIndex, color);
      }
    });

    agents.instanceMatrix.needsUpdate = true;
    if (shouldUpdateColors && agents.instanceColor) {
      agents.instanceColor.needsUpdate = true;
      lastColorFrame = index;
    }

    if (
      playback.currentTime - lastHeatmapUpdate >= HEATMAP_UPDATE_INTERVAL
      || playback.currentTime < lastHeatmapUpdate
    ) {
      heatmap.update(a.a);
      lastHeatmapUpdate = playback.currentTime;
    }

    if (
      playback.currentTime - lastHudUpdate >= HUD_UPDATE_INTERVAL
      || playback.currentTime < lastHudUpdate
    ) {
      const evacuated = Math.round(THREE.MathUtils.lerp(a.e, b.e, alpha));
      updateHud(evacuated, metadata.population);
      lastHudUpdate = playback.currentTime;
    }
  }

  function animate(timestamp) {
    requestAnimationFrame(animate);
    const delta = Math.min(MAX_FRAME_DELTA, (timestamp - previousTimestamp) / 1000);
    previousTimestamp = timestamp;

    if (playback.playing) {
      playback.currentTime = Math.min(
        playback.duration,
        playback.currentTime + delta * playback.speed,
      );
    }

    drawReplayFrame();
    cameraControls.update(delta);
    renderer.render(scene, camera);

    fpsFrames += 1;
    const elapsed = timestamp - fpsWindowStart;
    if (elapsed >= FPS_SAMPLE_INTERVAL_MS) {
      const fps = Math.round(fpsFrames * 1000 / elapsed);
      elements.fps.textContent = fps;
      lowFpsWindows = fps < LOW_FPS_THRESHOLD ? lowFpsWindows + 1 : 0;

      if (lowFpsWindows >= 2 && renderer.getPixelRatio() > 1) {
        renderer.setPixelRatio(1);
        updateViewport();
        lowFpsWindows = 0;
      }

      fpsFrames = 0;
      fpsWindowStart = timestamp;
    }
  }

  requestAnimationFrame(animate);
}

function updateHud(evacuated, population) {
  elements.timer.textContent = formatTime(playback.currentTime);
  elements.evacuated.textContent = evacuated.toLocaleString();
  elements.remaining.textContent = (population - evacuated).toLocaleString();
  elements.progress.style.width = `${100 * evacuated / population}%`;
  elements.timeline.value = 1000 * playback.currentTime / playback.duration;
}

addEventListener('resize', updateViewport);
updateViewport();

try {
  await startViewer();
} catch (error) {
  elements.loading.textContent = error.message;
  elements.loading.classList.add('loading--error');
  console.error(error);
}
