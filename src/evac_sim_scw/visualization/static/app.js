import * as THREE from 'three';
import { loadReplay, framePair } from './replay.js';
import { installFreeCamera } from './camera.js';
import { renderBuilding, createHeatmap } from './building_renderer.js';

const canvas=document.querySelector('#scene');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,powerPreference:'high-performance'});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.35));
const scene=new THREE.Scene();
scene.background=new THREE.Color(0x071018);
scene.fog=new THREE.Fog(0x071018,80,180);
const camera=new THREE.PerspectiveCamera(58,innerWidth/innerHeight,.08,350);
scene.add(new THREE.HemisphereLight(0xcdeaff,0x16232d,2.5));
const sun=new THREE.DirectionalLight(0xffffff,2.0);
sun.position.set(30,70,20);
scene.add(sun);
const controls=installFreeCamera(camera,canvas);
let playing=true, speed=1, current=0, last=performance.now(), duration=1, floorMode='all', lastColorFrame=-1, lastHeatUpdate=-1, lastHudUpdate=-1;
let fpsFrames=0, fpsWindowStart=performance.now(), lowFpsWindows=0;

try {
  const {metadata,frames}=await loadReplay();
  duration=frames.at(-1).t;
  const floorGroups=renderBuilding(scene,metadata.building);
  const heatmap=createHeatmap(scene,metadata.building);
  const geometry=new THREE.CapsuleGeometry(.23,.72,2,5), agentMaterial=new THREE.MeshStandardMaterial({color:0x4cc9ff});
  const agents=new THREE.InstancedMesh(geometry,agentMaterial,metadata.population);
  agents.instanceMatrix.setUsage(THREE.StreamDrawUsage);
  agents.frustumCulled=false;
  scene.add(agents);
  const dummy=new THREE.Object3D(), color=new THREE.Color();

  function draw(time) {
    const {a,b,alpha,index}=framePair(frames,time);
    const updateColors=index!==lastColorFrame;
    a.a.forEach((v,i)=>{
      const n=b.a[i]||v, exited=(alpha>.5?n[5]:v[5])===8;
      const x=THREE.MathUtils.lerp(v[1],n[1],alpha), planarY=THREE.MathUtils.lerp(v[2],n[2],alpha), z=THREE.MathUtils.lerp(v[3],n[3],alpha);
      const visible=floorMode==='all'||Number(floorMode)===(alpha>.5?n[4]:v[4]);
      dummy.position.set(x,z+.5,planarY);
      dummy.scale.setScalar(exited||!visible?0.0001:1);
      dummy.updateMatrix();
      agents.setMatrixAt(i,dummy.matrix);
      if(updateColors){
        const density=Math.min(1,v[7]/5);
        color.setHSL(.33*(1-density),.92,.48);
        agents.setColorAt(i,color);
      }
    });
    agents.instanceMatrix.needsUpdate=true;
    if(updateColors&&agents.instanceColor){
      agents.instanceColor.needsUpdate=true;
      lastColorFrame=index;
    }
    if(time-lastHeatUpdate>=.25||time<lastHeatUpdate){
      heatmap.update(a.a);
      lastHeatUpdate=time;
    }
    const e=Math.round(THREE.MathUtils.lerp(a.e,b.e,alpha)), r=metadata.population-e;
    if(time-lastHudUpdate>=.1||time<lastHudUpdate){
      document.querySelector('#timer').textContent=`${String(Math.floor(time/60)).padStart(2,'0')}:${(time%60).toFixed(1).padStart(4,'0')}`;
      document.querySelector('#evacuated').textContent=e.toLocaleString();
      document.querySelector('#remaining').textContent=r.toLocaleString();
      document.querySelector('#progress').style.width=`${100*e/metadata.population}%`;
      document.querySelector('#timeline').value=1000*time/duration;
      lastHudUpdate=time;
    }
  }

  function animate(now) {
    requestAnimationFrame(animate);
    const dt=Math.min(.05,(now-last)/1000);
    last=now;
    if(playing)current=Math.min(duration,current+dt*speed);
    draw(current);
    controls.update(dt);
    renderer.render(scene,camera);
    fpsFrames++;
    const elapsed=now-fpsWindowStart;
    if(elapsed>=1000){
      const fps=Math.round(fpsFrames*1000/elapsed);
      document.querySelector('#fps').textContent=fps;
      lowFpsWindows=fps<42?lowFpsWindows+1:0;
      if(lowFpsWindows>=2&&renderer.getPixelRatio()>1){
        renderer.setPixelRatio(1);
        renderer.setSize(innerWidth,innerHeight,false);
        lowFpsWindows=0;
      }
      fpsFrames=0;
      fpsWindowStart=now;
    }
  }

  document.querySelector('#play').onclick=e=>{
    playing=!playing;
    e.target.textContent=playing?'Pause':'Play'
  };
  document.querySelector('#speed').onchange=e=>speed=Number(e.target.value);
  document.querySelector('#floor').onchange=e=>{
    floorMode=e.target.value;
    floorGroups.forEach((g,i)=>g.visible=floorMode==='all'||Number(floorMode)===i);
    heatmap.setFloor(floorMode)
  };
  document.querySelector('#overview').onclick=()=>controls.overview();
  document.querySelector('#timeline').oninput=e=>{
    current=duration*Number(e.target.value)/1000
  };
  document.querySelector('#loading').remove();
  requestAnimationFrame(animate);
} catch(error) {
  document.querySelector('#loading').textContent=error.message;
  console.error(error);
}

addEventListener('resize',()=>{
  camera.aspect=innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth,innerHeight,false)
});
renderer.setSize(innerWidth,innerHeight,false);
