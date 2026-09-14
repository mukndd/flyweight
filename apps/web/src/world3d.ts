import type {Action} from '../../../packages/protocol';
import type {Fighter} from '../../../packages/sim/core';
import {actionButton,actionMood,type ActionMood} from './presentation';

type Three=typeof import('three');
type Mat=import('three').MeshStandardMaterial;
type Group=import('three').Group;
type Mesh=import('three').Mesh;

export interface FlyRig{
 group:Group;
 eyes:Mesh[];
 wings:Mesh[];
 antennae:Mesh[];
 frontLegs:Group[];
 legs:Group[];
 abdomen:Mesh;
 thorax:Mesh;
 head:Mesh;
}

export interface ControllerRig{
 group:Group;
 buttons:Mesh[];
 stick:Group;
 lever:Mesh;
}

export interface FighterRig{
 group:Group;
 root:Group;
 torso:Mesh;
 head:Mesh;
 pelvis:Mesh;
 leftArm:Group;
 rightArm:Group;
 leftLeg:Group;
 rightLeg:Group;
 visor:Mesh;
 badge?:Mesh;
 shadow:Mesh;
 material:Mat;
 accent:Mat;
}

export function createTestChamber(THREE:Three){
 const group=new THREE.Group();
 const floorMat=new THREE.MeshStandardMaterial({color:0x242521,roughness:.86,metalness:.05});
 const floor=new THREE.Mesh(new THREE.PlaneGeometry(9.6,6.2),floorMat);
 floor.rotation.x=-Math.PI/2;floor.receiveShadow=true;group.add(floor);
 const center=new THREE.Mesh(new THREE.PlaneGeometry(7.7,3.4),new THREE.MeshStandardMaterial({color:0x2d2f2b,roughness:.82,metalness:.08}));
 center.rotation.x=-Math.PI/2;center.position.y=.006;center.receiveShadow=true;group.add(center);
 const lineMat=new THREE.LineBasicMaterial({color:0x858981,transparent:true,opacity:.26});
 for(let x=-4.4;x<=4.41;x+=.4){
  const geo=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x,.016,-2.85),new THREE.Vector3(x,.016,2.85)]);
  group.add(new THREE.Line(geo,lineMat));
 }
 for(let z=-2.8;z<=2.81;z+=.4){
  const geo=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-4.55,.017,z),new THREE.Vector3(4.55,.017,z)]);
  group.add(new THREE.Line(geo,lineMat));
 }
 const laneMat=new THREE.LineBasicMaterial({color:0xd19a4d,transparent:true,opacity:.55});
 for(const x of [-3.65,0,3.65]){
  const geo=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x,.025,-1.82),new THREE.Vector3(x,.025,1.82)]);
  group.add(new THREE.Line(geo,laneMat));
 }
 const wallMat=new THREE.MeshStandardMaterial({color:0x2b2d2b,roughness:.74,metalness:.08});
 const backWall=new THREE.Mesh(new THREE.BoxGeometry(9.8,2.5,.14),wallMat);
 backWall.position.set(0,1.25,-3.14);backWall.receiveShadow=true;group.add(backWall);
 const sideMat=new THREE.MeshStandardMaterial({color:0x1e211f,roughness:.76,metalness:.12});
 for(const x of [-4.86,4.86]){
  const wall=new THREE.Mesh(new THREE.BoxGeometry(.14,1.55,6.2),sideMat);
  wall.position.set(x,.78,0);wall.receiveShadow=true;group.add(wall);
 }
 const railMat=new THREE.MeshStandardMaterial({color:0x666a63,roughness:.52,metalness:.42});
 for(const z of [-1.92,1.92]){
  const rail=new THREE.Mesh(new THREE.BoxGeometry(7.6,.07,.08),railMat);
  rail.position.set(0,.08,z);rail.castShadow=true;rail.receiveShadow=true;group.add(rail);
 }
 for(const x of [-3.8,3.8]){
  const rail=new THREE.Mesh(new THREE.BoxGeometry(.08,.07,3.9),railMat);
  rail.position.set(x,.08,0);rail.castShadow=true;rail.receiveShadow=true;group.add(rail);
 }
 const glassMat=new THREE.MeshStandardMaterial({color:0x6f8390,transparent:true,opacity:.18,roughness:.18,metalness:.05});
 const glass=new THREE.Mesh(new THREE.PlaneGeometry(3.3,.72),glassMat);
 glass.position.set(0,1.34,-3.055);group.add(glass);
 const fixtureMat=new THREE.MeshStandardMaterial({color:0xded4c2,emissive:0xc28a4f,emissiveIntensity:.55,roughness:.32});
 for(const x of [-2.8,0,2.8]){
  const lamp=new THREE.Mesh(new THREE.BoxGeometry(1.1,.08,.18),fixtureMat);
  lamp.position.set(x,2.45,-1.55);lamp.castShadow=false;group.add(lamp);
 }
 return group;
}

export function createDrosophila(THREE:Three):FlyRig{
 const group=new THREE.Group();
 const bodyMat=new THREE.MeshStandardMaterial({color:0xb56e2d,roughness:.48,metalness:.02});
 const abdomenMat=new THREE.MeshStandardMaterial({color:0xc99143,roughness:.54,metalness:.02});
 const stripeMat=new THREE.MeshStandardMaterial({color:0x352016,roughness:.68});
 const headMat=new THREE.MeshStandardMaterial({color:0xa96631,roughness:.44});
 const eyeMat=new THREE.MeshStandardMaterial({color:0x8e1719,emissive:0x5a0708,emissiveIntensity:.62,roughness:.28});
 const wingMat=new THREE.MeshStandardMaterial({color:0xe5eef0,transparent:true,opacity:.38,roughness:.14,metalness:.02,side:THREE.DoubleSide});
 const legMat=new THREE.MeshStandardMaterial({color:0x201712,roughness:.7});
 const thorax=new THREE.Mesh(new THREE.SphereGeometry(.34,40,22),bodyMat);
 thorax.scale.set(.9,.74,1.1);thorax.castShadow=true;thorax.position.set(0,.36,0);group.add(thorax);
 const abdomen=new THREE.Mesh(new THREE.SphereGeometry(.39,44,24),abdomenMat);
 abdomen.scale.set(.78,.62,1.46);abdomen.castShadow=true;abdomen.position.set(0,.31,-.46);group.add(abdomen);
 for(let i=0;i<5;i++){
  const stripe=new THREE.Mesh(new THREE.TorusGeometry(.23+i*.018,.008,6,48),stripeMat);
  stripe.scale.set(1.42,.18,.58);stripe.rotation.x=Math.PI/2;stripe.position.set(0,.33,-.22-i*.105);group.add(stripe);
 }
 const head=new THREE.Mesh(new THREE.SphereGeometry(.25,38,20),headMat);
 head.scale.set(1.1,.92,.88);head.castShadow=true;head.position.set(0,.44,.43);group.add(head);
 const eyes:Mesh[]=[];
 for(const x of [-.17,.17]){
  const eye=new THREE.Mesh(new THREE.SphereGeometry(.115,24,16),eyeMat);
  eye.position.set(x,.46,.59);eye.scale.set(1.02,1.18,.72);eye.castShadow=true;group.add(eye);eyes.push(eye);
 }
 const wingShape=new THREE.Shape();
 wingShape.moveTo(0,0);wingShape.bezierCurveTo(.2,.18,.62,.23,.88,.05);wingShape.bezierCurveTo(.58,-.18,.18,-.18,0,0);
 const wingGeo=new THREE.ShapeGeometry(wingShape,18);
 const wings:Mesh[]=[];
 for(const side of [-1,1]){
  const wing=new THREE.Mesh(wingGeo,wingMat);
  wing.position.set(side*.2,.52,-.22);wing.rotation.set(-.18,side*.32,side*.22);wing.scale.set(side*.92,.92,.92);wing.castShadow=true;group.add(wing);wings.push(wing);
  for(let i=0;i<3;i++){
   const vein=new THREE.Mesh(new THREE.CapsuleGeometry(.003,.62-i*.1,3,5),new THREE.MeshStandardMaterial({color:0xd8e2e4,transparent:true,opacity:.38,roughness:.2}));
   vein.position.set(side*(.33+i*.09),.53,-.2-i*.02);vein.rotation.set(1.38,side*(.7+i*.1),side*(.55+i*.16));group.add(vein);
  }
 }
 const antennae:Mesh[]=[];
 for(const x of [-.09,.09]){
  const antenna=new THREE.Mesh(new THREE.CapsuleGeometry(.007,.31,4,8),legMat);
  antenna.position.set(x,.62,.58);antenna.rotation.set(.95,0,x<0 ? .5 : -.5);antenna.castShadow=true;group.add(antenna);antennae.push(antenna);
 }
 const legs:Group[]=[];const frontLegs:Group[]=[];
 const legSpec=[{z:.28,y:.27,reach:.47,front:true},{z:.02,y:.24,reach:.58},{z:-.26,y:.22,reach:.52}];
 for(const spec of legSpec)for(const side of [-1,1]){
  const leg=new THREE.Group();leg.position.set(side*.23,spec.y,spec.z);
  const upper=new THREE.Mesh(new THREE.CapsuleGeometry(.014,.34,4,8),legMat);
  upper.rotation.set(.88,0,side*1.05);upper.position.set(side*.11,-.11,.02);upper.castShadow=true;leg.add(upper);
  const lower=new THREE.Mesh(new THREE.CapsuleGeometry(.011,.38,4,8),legMat);
  lower.rotation.set(1.02,0,side*1.38);lower.position.set(side*spec.reach,-.29,.08);lower.castShadow=true;leg.add(lower);
  const foot=new THREE.Mesh(new THREE.CapsuleGeometry(.008,.18,3,6),legMat);
  foot.rotation.set(Math.PI/2,0,side*Math.PI/2);foot.position.set(side*(spec.reach+.13),-.48,.14);foot.castShadow=true;leg.add(foot);
  group.add(leg);legs.push(leg);if(spec.front)frontLegs.push(leg);
 }
 group.rotation.x=-.08;
 return {group,eyes,wings,antennae,frontLegs,legs,abdomen,thorax,head};
}

export function createController(THREE:Three):ControllerRig{
 const group=new THREE.Group();
 const shellMat=new THREE.MeshStandardMaterial({color:0x191b1e,roughness:.56,metalness:.2});
 const rubberMat=new THREE.MeshStandardMaterial({color:0x090a0b,roughness:.8,metalness:.04});
 const shell=new THREE.Mesh(new THREE.BoxGeometry(1.65,.2,.64),shellMat);
 shell.castShadow=true;shell.receiveShadow=true;group.add(shell);
 const bevel=new THREE.Mesh(new THREE.BoxGeometry(1.82,.08,.48),new THREE.MeshStandardMaterial({color:0x24272a,roughness:.55,metalness:.24}));
 bevel.position.y=.08;bevel.castShadow=true;group.add(bevel);
 const stick=new THREE.Group();stick.position.set(-.55,.17,.03);
 const base=new THREE.Mesh(new THREE.CylinderGeometry(.16,.16,.045,28),rubberMat);base.castShadow=true;stick.add(base);
 const lever=new THREE.Mesh(new THREE.CapsuleGeometry(.025,.2,5,10),rubberMat);lever.position.y=.12;lever.castShadow=true;stick.add(lever);
 const cap=new THREE.Mesh(new THREE.SphereGeometry(.075,20,12),rubberMat);cap.position.y=.24;cap.castShadow=true;stick.add(cap);
 group.add(stick);
 const buttons:Mesh[]=[];
 const colors=[0x6f7f88,0xd1974c,0xc47438,0xe3ba70,0x8f9aa4,0xb88945];
 const coords:[[number,number],... [number,number][]]=[[.15,.07],[.38,.16],[.62,.04],[.4,-.1],[-.18,-.18],[-.78,-.2]];
 coords.forEach(([x,z],i)=>{
  const button=new THREE.Mesh(new THREE.CylinderGeometry(.083,.083,.052,24),new THREE.MeshStandardMaterial({color:colors[i],emissive:colors[i],emissiveIntensity:.18,roughness:.42}));
  button.rotation.x=Math.PI/2;button.position.set(x,.15,z);button.castShadow=true;group.add(button);buttons.push(button);
 });
 return {group,buttons,stick,lever};
}

export function animateFlyController(fly:FlyRig,controller:ControllerRig,action:Action,mood:ActionMood,frame:number,time:number,reduced=false){
 const pulse=mood==='attack'||mood==='victory'||mood==='ko'
  ? .9
  : mood==='dodge'||mood==='jump'
   ? .62
   : mood==='guard'
    ? .44
    : .28;
 const t=reduced?time*.25:time;
 fly.group.position.y=.02+Math.sin(t*5.1)*(.012+pulse*.012);
 fly.group.rotation.y=Math.sin(t*.9)*.06+(action===1 ? .12 : action===2 ? -.12 : 0);
 fly.group.rotation.z=(mood==='attack' ? -0.055 : mood==='guard' ? .045 : 0)+Math.sin(t*1.7)*.018;
 fly.wings.forEach((wing,i)=>{wing.rotation.z=(i?1:-1)*(.2+Math.sin(t*(mood==='idle'?8:22))*(.13+pulse*.12));});
 fly.antennae.forEach((antenna,i)=>{antenna.rotation.z=(i?-.52:.52)+Math.sin(t*3+i)*.08;});
 fly.eyes.forEach(eye=>{(eye.material as Mat).emissiveIntensity=.32+pulse*.42;});
 const button=actionButton(action);
 controller.buttons.forEach((mesh,i)=>{
  const active=i===button||(action===13&&(i===1||i===2||i===3));
  mesh.position.y=active ? .118 : .15;
  mesh.scale.setScalar(active?1.18:1);
 });
 controller.stick.rotation.z=action===1 ? .34 : action===2 ? -.34 : action===7 ? Math.sin(t*22)*.28 : 0;
 controller.stick.rotation.x=action===3||action===11 ? -.24 : action===4||action===8 ? .22 : 0;
 fly.frontLegs.forEach((leg,i)=>{
  const side=i===0?-1:1;
  const press=i===0&&(action===1||action===2||action===7)||i===1&&button>0;
  leg.rotation.x=press?-.3+Math.sin(t*18)*.035:Math.sin(t*3+i)*.045;
  leg.rotation.z=side*(press ? .2 : .05);
 });
 if(mood==='victory')fly.group.rotation.y=Math.sin(t*5)*.18;
 if(mood==='ko'){fly.group.rotation.z=.24;fly.group.position.y-=.08;}
}

export function createFighter(THREE:Three,neural:boolean):FighterRig{
 const color=neural?0xc87d32:0x6f8798;
 const accentColor=neural?0xf0c06d:0xaab8bf;
 const material=new THREE.MeshStandardMaterial({color,roughness:.58,metalness:.18});
 const dark=new THREE.MeshStandardMaterial({color:0x15171a,roughness:.62,metalness:.22});
 const accent=new THREE.MeshStandardMaterial({color:accentColor,emissive:accentColor,emissiveIntensity:.08,roughness:.44,metalness:.18});
 const group=new THREE.Group();
 const root=new THREE.Group();group.add(root);
 const pelvis=new THREE.Mesh(new THREE.BoxGeometry(.38,.2,.22),dark);pelvis.position.y=.72;pelvis.castShadow=true;root.add(pelvis);
 const torso=new THREE.Mesh(new THREE.CapsuleGeometry(.18,.62,6,12),material);torso.position.y=1.13;torso.rotation.z=.05;torso.castShadow=true;root.add(torso);
 const head=new THREE.Mesh(new THREE.BoxGeometry(.34,.3,.28),material);head.position.y=1.62;head.castShadow=true;root.add(head);
 const visor=new THREE.Mesh(new THREE.BoxGeometry(.24,.045,.295),dark);visor.position.set(.04,1.65,.015);visor.castShadow=true;root.add(visor);
 const badge=neural?new THREE.Mesh(new THREE.BoxGeometry(.08,.24,.026),accent):undefined;
 if(badge){badge.position.set(-.19,1.18,.13);badge.castShadow=true;root.add(badge);}
 const limb=(upperLen:number,lowerLen:number,mat:Mat)=>{
  const limbGroup=new THREE.Group();
  const upper=new THREE.Mesh(new THREE.CapsuleGeometry(.055,upperLen,5,10),mat);upper.name='upper';upper.position.y=-upperLen/2;upper.castShadow=true;limbGroup.add(upper);
  const lowerPivot=new THREE.Group();lowerPivot.name='lowerPivot';lowerPivot.position.y=-upperLen;
  const lower=new THREE.Mesh(new THREE.CapsuleGeometry(.047,lowerLen,5,10),mat);lower.name='lower';lower.position.y=-lowerLen/2;lower.castShadow=true;lowerPivot.add(lower);
  limbGroup.add(lowerPivot);return limbGroup;
 };
 const leftArm=limb(.42,.36,material),rightArm=limb(.42,.36,material);
 leftArm.position.set(-.25,1.34,0);rightArm.position.set(.25,1.34,0);root.add(leftArm,rightArm);
 const leftLeg=limb(.48,.5,material),rightLeg=limb(.48,.5,material);
 leftLeg.position.set(-.14,.64,0);rightLeg.position.set(.14,.64,0);root.add(leftLeg,rightLeg);
 const shadow=new THREE.Mesh(new THREE.CircleGeometry(.55,36),new THREE.MeshBasicMaterial({color:0x000000,transparent:true,opacity:.32,depthWrite:false}));
 shadow.rotation.x=-Math.PI/2;shadow.position.y=.018;group.add(shadow);
 return {group,root,torso,head,pelvis,leftArm,rightArm,leftLeg,rightLeg,visor,badge,shadow,material,accent};
}

export function updateFighter(rig:FighterRig,f:Fighter,frame:number,neural:boolean){
 const worldX=(f.x-500)/125;
 rig.group.position.set(worldX,Math.max(0,f.y/88),neural ? .03 : -.03);
 const facing=f.face>0?1:-1;
 rig.root.rotation.y=facing>0 ? .45 : -.45;
 const walk=Math.sin(frame*.34)*Math.min(1,Math.abs(f.vx)/4);
 const crouch=f.crouch ? .26 : f.block ? .11 : 0;
 const hit=f.stun?Math.sin(frame*1.8)*.08:0;
 rig.root.position.y=-crouch;
 rig.root.rotation.z=hit+(f.invul?Math.sin(frame*.8)*.06:0);
 poseLimb(rig.leftLeg,.16+walk*.35,.36-walk*.22);
 poseLimb(rig.rightLeg,-.16-walk*.35,-.36+walk*.22);
 poseLimb(rig.leftArm,.12,.4);
 poseLimb(rig.rightArm,-.12,.35);
 const attack=f.attack;
 if(f.block){poseLimb(rig.leftArm,-.95,.72);poseLimb(rig.rightArm,-.72,.62);}
 if(attack){
  const phase=Math.sin(Math.min(1,f.attackFrame/(attack===6||attack===13?17:11))*Math.PI);
  if(attack===9||attack===11){poseLimb(rig.rightLeg,-1.28*phase,.45);rig.root.rotation.z+=facing*.08*phase;}
  else if(attack===12){poseLimb(rig.leftArm,-1.05*phase,.2);poseLimb(rig.rightArm,-1.05*phase,.2);}
  else{poseLimb(rig.rightArm,-1.35*phase,.12);rig.root.rotation.z+=facing*.05*phase;}
 }
 if(f.action===7){rig.group.position.x+=facing*.12*Math.sin(frame*.8);rig.root.rotation.z+=facing*.18;}
 rig.head.rotation.z=f.stun?Math.sin(frame*1.9)*.08:0;
 rig.shadow.position.x=rig.group.position.x;rig.shadow.position.z=rig.group.position.z;
 rig.shadow.scale.setScalar(Math.max(.62,1-f.y/240));
 (rig.shadow.material as import('three').MeshBasicMaterial).opacity=.32*Math.max(.25,1-f.y/170);
 const glow=f.attack||f.stun?0.18:0.06;
 rig.material.emissive.setHex(f.stun?0xffffff:0x000000);
 rig.material.emissiveIntensity=f.stun ? .1 : 0;
 rig.accent.emissiveIntensity=neural ? .16+glow : .08+glow*.5;
}

function poseLimb(limb:Group,upperRot:number,lowerRot:number){
 limb.rotation.z=upperRot;
 const lower=limb.getObjectByName('lowerPivot');
 if(lower)lower.rotation.z=lowerRot;
}

export function moodForAction(action:Action,winner:null|0|1|2){
 if(winner===1)return 'victory';
 if(winner===0)return 'ko';
 return actionMood(action);
}
