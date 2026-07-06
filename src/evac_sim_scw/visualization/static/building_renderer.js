import * as THREE from 'three';

const material = (color, opacity=1) => new THREE.MeshStandardMaterial({color, transparent: opacity < 1, opacity, side: THREE.DoubleSide});

function box(scene, size, position, color, opacity=1, group=null) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), material(color, opacity));
  mesh.position.set(...position);
  (group || scene).add(mesh);
  return mesh;
}

function slabWithStairOpenings(scene, building, floor, elevation, group) {
  const stairRooms=building.rooms.filter(r=>r.floor===floor&&r.kind==='stairwell').sort((a,b)=>a.x-b.x);
  const thickness=.18, color=0x253746;
  if(!stairRooms.length){
    box(scene,[building.dimensions.width,thickness,building.dimensions.depth],[building.dimensions.width/2,elevation-.12,building.dimensions.depth/2],color,.92,group);
    return;
  }
  const y0=stairRooms[0].y, y1=stairRooms[0].y+stairRooms[0].depth;
  box(scene,[building.dimensions.width,thickness,y0],[building.dimensions.width/2,elevation-.12,y0/2],color,.92,group);
  if(y1<building.dimensions.depth) box(scene,[building.dimensions.width,thickness,building.dimensions.depth-y1],[building.dimensions.width/2,elevation-.12,(y1+building.dimensions.depth)/2],color,.92,group);
  let cursor=0;
  stairRooms.forEach(room=>{
    if(room.x>cursor)box(scene,[room.x-cursor,thickness,y1-y0],[(cursor+room.x)/2,elevation-.12,(y0+y1)/2],color,.92,group);
    cursor=room.x+room.width;
  });
  if(cursor<building.dimensions.width)box(scene,[building.dimensions.width-cursor,thickness,y1-y0],[(cursor+building.dimensions.width)/2,elevation-.12,(y0+y1)/2],color,.92,group);
}

function roomWalls(scene, room, door, elevation, group) {
  const wallH=1.3,t=.10,color=0xb9c8cf;
  box(scene,[t,wallH,room.depth],[room.x,elevation+wallH/2,room.y+room.depth/2],color,.30,group);
  box(scene,[t,wallH,room.depth],[room.x+room.width,elevation+wallH/2,room.y+room.depth/2],color,.30,group);
  if(room.kind==='stairwell'){
    box(scene,[room.width,wallH,t],[room.x+room.width/2,elevation+wallH/2,room.y+room.depth],color,.30,group);
    return;
  }
  const corridorSide=door.y===room.y?'south':'north';
  const outerY=corridorSide==='south'?room.y+room.depth:room.y;
  box(scene,[room.width,wallH,t],[room.x+room.width/2,elevation+wallH/2,outerY],color,.30,group);
  const left=door.x-door.width/2-room.x, right=room.x+room.width-(door.x+door.width/2);
  if(left>0)box(scene,[left,wallH,t],[room.x+left/2,elevation+wallH/2,door.y],color,.30,group);
  if(right>0)box(scene,[right,wallH,t],[door.x+door.width/2+right/2,elevation+wallH/2,door.y],color,.30,group);
}

function ramp(scene, stair, floor, firstFlight, floorHeight, group) {
  const enclosureWidth=stair.enclosure_width||stair.width*2.4;
  const laneOffset=enclosureWidth*.23, entrance=stair.y-stair.depth/2+.05, landing=entrance+Math.min(5.9,stair.depth-1.9);
  const run=landing-entrance, rise=floorHeight*.5, slopeLength=Math.hypot(run,rise);
  const x=stair.x+(firstFlight?-laneOffset:laneOffset);
  const verticalTop=firstFlight?floor*floorHeight:floor*floorHeight-rise;
  const y=verticalTop-rise/2, z=(entrance+landing)/2;
  const mesh=box(scene,[stair.width*.96,.14,slopeLength],[x,y,z],firstFlight?0xc49a62:0xb8834f,1,group);
  mesh.rotation.x=firstFlight?Math.atan2(rise,run):-Math.atan2(rise,run);
}

export function renderBuilding(scene, building) {
  const groups=[new THREE.Group(),new THREE.Group(),new THREE.Group()];
  groups.forEach(g=>scene.add(g));
  const h=building.dimensions.floor_height;
  for(let floor=0;floor<3;floor++){
    const elevation=floor*h;
    slabWithStairOpenings(scene,building,floor,elevation,groups[floor]);
    building.corridors.filter(c=>c.floor===floor).forEach(c=>box(scene,[c.width,.035,c.depth],[c.x+c.width/2,elevation+.02,c.y+c.depth/2],0x6c8292,.78,groups[floor]));
    building.rooms.filter(r=>r.floor===floor).forEach((room,index)=>{
      const door=building.doors.find(d=>d.floor===floor&&d.connects[0]===room.id);
      if(room.kind!=='stairwell')box(scene,[room.width,.025,room.depth],[room.x+room.width/2,elevation+.03,room.y+room.depth/2],index%2?0x345366:0x3d5d70,.74,groups[floor]);
      roomWalls(scene,room,door,elevation,groups[floor]);
    });
    building.doors.filter(d=>d.floor===floor).forEach(d=>box(scene,[d.width,.035,.18],[d.x,elevation+.06,d.y],d.kind==='stair_entry'?0xff9f43:0xe0bd77,.95,groups[floor]));
  }
  building.exits.forEach(exit=>{
    const side=exit.x<1||exit.x>building.dimensions.width-1,size=side?[.18,2.5,exit.width]:[exit.width,2.5,.18];
    const marker=box(scene,size,[exit.x,1.25,exit.y],0x37ef79,.75,groups[0]);
    marker.material.emissive.setHex(0x126b34);
  });
  building.stairs.forEach(stair=>{
    for(let floor=1;floor<=2;floor++){
      const enclosureWidth=stair.enclosure_width||stair.width*2.4, entrance=stair.y-stair.depth/2+.05, landing=entrance+Math.min(5.9,stair.depth-1.9), run=landing-entrance;
      ramp(scene,stair,floor,true,h,groups[floor-1]);
      ramp(scene,stair,floor,false,h,groups[floor-1]);
      box(scene,[enclosureWidth*.94,.14,1.9],[stair.x,floor*h-h*.5,landing+.8],0xd7b47e,1,groups[floor-1]);
      const railY=floor*h-h*.5;
      box(scene,[.07,1.0,run],[stair.x-enclosureWidth*.49,railY,landing-run/2],0x9faab0,.9,groups[floor-1]);
      box(scene,[.07,1.0,run],[stair.x+enclosureWidth*.49,railY,landing-run/2],0x9faab0,.9,groups[floor-1]);
    }
  });
  return groups;
}

export function createHeatmap(scene,building){
  const cols=12,rows=6,cw=building.dimensions.width/cols,cd=building.dimensions.depth/rows,h=building.dimensions.floor_height;
  const geometry=new THREE.BoxGeometry(cw-.08,.025,cd-.08),groups=[],dummy=new THREE.Object3D(),color=new THREE.Color();
  for(let f=0;f<3;f++){
    const mesh=new THREE.InstancedMesh(geometry,new THREE.MeshBasicMaterial({vertexColors:true,transparent:true,opacity:.3,depthWrite:false}),cols*rows);
    let index=0;
    for(let y=0;y<rows;y++)for(let x=0;x<cols;x++){
      dummy.position.set(x*cw+cw/2,f*h+.07,y*cd+cd/2);
      dummy.updateMatrix();
      mesh.setMatrixAt(index,dummy.matrix);
      mesh.setColorAt(index,new THREE.Color(0x123d20));
      index++;
    }
    mesh.instanceMatrix.needsUpdate=true;
    mesh.instanceColor.needsUpdate=true;
    scene.add(mesh);
    groups.push(mesh);
  }
  function update(agents){
    const counts=new Uint16Array(3*cols*rows);
    agents.forEach(a=>{
      if(a[5]===8)return;
      const x=Math.max(0,Math.min(cols-1,Math.floor(a[1]/cw))),y=Math.max(0,Math.min(rows-1,Math.floor(a[2]/cd))),f=Math.max(0,Math.min(2,a[4]));
      counts[f*cols*rows+y*cols+x]++;
    });
    groups.forEach((mesh,f)=>{
      for(let i=0;i<cols*rows;i++){
        const v=Math.min(1,counts[f*cols*rows+i]/18);
        color.setHSL(.33*(1-v),.92,.18+v*.35);
        mesh.setColorAt(i,color);
      }
      mesh.instanceColor.needsUpdate=true;
    });
  }
  function setFloor(value){
    groups.forEach((mesh,f)=>mesh.visible=value==='all'||Number(value)===f);
  }
  return{groups,update,setFloor};
}
