import {useEffect,useRef,useState} from 'react';
import type {Group,Mesh,MeshStandardMaterial,PerspectiveCamera,Scene,WebGLRenderer} from 'three';
import {presentationState,type PresentationState} from './presentation';
import type {Engine} from './engine';

type Variant='hero'|'match'|'compact';

function canUseWebGL(){
 try{
  const canvas=document.createElement('canvas');
  return !!(canvas.getContext('webgl2')||canvas.getContext('webgl'));
 }catch{return false;}
}

export function Presentation3D({engine,variant='hero'}:{engine:Engine;variant?:Variant}){
 const host=useRef<HTMLDivElement>(null),stateRef=useRef<PresentationState|null>(null);
 const[failed,setFailed]=useState(false);
 stateRef.current=presentationState(engine.state,engine.online,engine.checkpoint,engine.state.fighters[1].action);
 useEffect(()=>{
  if(!host.current||!canUseWebGL()){setFailed(true);return;}
  let renderer:WebGLRenderer|undefined,scene:Scene|undefined,camera:PerspectiveCamera|undefined,fly:Group|undefined,controller:Group|undefined,arena:Group|undefined,raf=0,disposed=false;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  import('three').then(THREE=>{
   if(disposed||!host.current)return;
   scene=new THREE.Scene();
   scene.fog=new THREE.Fog(0x080909,7,18);
   camera=new THREE.PerspectiveCamera(38,1,.1,100);
   camera.position.set(0,variant==='compact'?1.1:1.45,variant==='match'?7.2:7.8);
   renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:'high-performance',preserveDrawingBuffer:true});
   renderer.setPixelRatio(Math.min(devicePixelRatio,1.75));
   renderer.setClearColor(0x000000,0);
   host.current.appendChild(renderer.domElement);
   scene.add(new THREE.AmbientLight(0x77808a,1.25));
   const key=new THREE.PointLight(0xf2c27d,variant==='match'?24:34,10);key.position.set(3,4,4);scene.add(key);
   const fill=new THREE.PointLight(0x8ca9bd,14,9);fill.position.set(-4,3,3);scene.add(fill);
   const top=new THREE.DirectionalLight(0xffffff,2.8);top.position.set(0,7,5);scene.add(top);
   arena=createArena(THREE,variant);scene.add(arena);
   fly=createFly(THREE);fly.position.set(0,.75,0);scene.add(fly);
   controller=createController(THREE);controller.position.set(0,-.25,.8);scene.add(controller);
   const resize=()=>{
    if(!host.current||!renderer||!camera)return;
    const rect=host.current.getBoundingClientRect(),w=Math.max(1,rect.width),h=Math.max(1,rect.height);
    renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
   };
   const draw=(time:number)=>{
    raf=requestAnimationFrame(draw);if(!renderer||!scene||!camera||!fly||!controller||!arena)return;
    resize();
    const s=stateRef.current,slow=reduced?.15:1,t=time*.001*slow,pulse=s?.intensity??.25;
    fly.rotation.y=Math.sin(t*.8)*.22+(s?.mood==='move'?.35:0);
    fly.rotation.z=(s?.mood==='attack'?-.18:s?.mood==='guard'?.18:0)+Math.sin(t*2)*.035;
    fly.position.y=.72+Math.sin(t*(s?.mood==='offline'?1.4:6))*(.018+pulse*.028);
    fly.scale.setScalar(1+(s?.mood==='victory'?.08:0));
    const wings=fly.children.filter(child=>child.name==='wing');
    wings.forEach((wing,index)=>{wing.rotation.z=(index?1:-1)*(1.05+Math.sin(t*(s?.mood==='offline'?3:18))*.42);});
    const eyes=fly.children.filter(child=>child.name==='eye') as Mesh[];
    eyes.forEach(eye=>{const mat=eye.material as MeshStandardMaterial;mat.emissiveIntensity=s?.online ? .55+pulse*.25 : .18;});
    controller.rotation.x=-.18+Math.sin(t*1.3)*.025;
    controller.rotation.z=Math.sin(t*1.1)*.04+(s?.mood==='dodge'?.13:0);
    controller.children.forEach((child,index)=>{
     if(!child.name.startsWith('button'))return;
     const active=index-1===s?.button;
     child.position.z=active?.05:.11;
     child.scale.setScalar(active?1.25:1);
    });
    arena.rotation.y=Math.sin(t*.18)*.06;
    camera.position.x=Math.sin(t*.25)*(.05+pulse*.05);
    camera.lookAt(0,.45,0);
    renderer.render(scene,camera);
   };
   resize();draw(0);
  }).catch(()=>setFailed(true));
  return()=>{disposed=true;cancelAnimationFrame(raf);renderer?.dispose();if(renderer?.domElement.parentElement)renderer.domElement.remove();};
 },[variant]);
 return <div className={`presentation3d ${variant} ${failed?'fallback':''}`} ref={host} aria-label="3D fly mascot presentation">{failed&&<MascotFallback state={stateRef.current}/>}<div className="presentation-readout"><b>{stateRef.current?.actionLabel}</b><span>{stateRef.current?.mood}</span></div></div>;
}

function MascotFallback({state}:{state:PresentationState|null}){
 return <div className={`fly-fallback ${state?.mood??'idle'}`}><span className="wing left"/><span className="body"/><span className="head"><i/><i/></span><span className="wing right"/><b>{state?.actionLabel??'Waiting'}</b></div>;
}

function createArena(THREE:typeof import('three'),variant:Variant){
 const group=new THREE.Group();
 const mat=new THREE.MeshStandardMaterial({color:0x181a19,roughness:.82,metalness:.12});
 const floor=new THREE.Mesh(new THREE.CylinderGeometry(2.8,3.2,.16,6),mat);floor.position.y=-.7;floor.rotation.y=Math.PI/6;group.add(floor);
 const ring=new THREE.Mesh(new THREE.TorusGeometry(2.7,.014,8,96),new THREE.MeshStandardMaterial({color:0x6d706b,roughness:.65,metalness:.3}));ring.rotation.x=Math.PI/2;ring.position.y=-.55;group.add(ring);
 for(let i=0;i<8;i++){const angle=i*Math.PI/4,x=Math.cos(angle)*2.9,z=Math.sin(angle)*2.9;const post=new THREE.Mesh(new THREE.BoxGeometry(.035,1.1,.035),new THREE.MeshStandardMaterial({color:0x3a3d3a,roughness:.7,metalness:.25}));post.position.set(x,-.08,z);group.add(post);}
 if(variant!=='compact')for(let i=0;i<14;i++){const light=new THREE.Mesh(new THREE.BoxGeometry(.07,.05,.07),new THREE.MeshStandardMaterial({color:0xd6d2c9,emissive:i%2?0xc28a4f:0x6f8fab,emissiveIntensity:.28}));light.position.set((i-6.5)*.34,2.05,-2.4);group.add(light);}
 return group;
}

function createFly(THREE:typeof import('three')){
 const group=new THREE.Group();
 const bodyMat=new THREE.MeshStandardMaterial({color:0xb87935,roughness:.48,metalness:.02});
 const abdomenMat=new THREE.MeshStandardMaterial({color:0xc99347,roughness:.52,metalness:.02});
 const stripeMat=new THREE.MeshStandardMaterial({color:0x3f2719,roughness:.6});
 const headMat=new THREE.MeshStandardMaterial({color:0xb98543,roughness:.42});
 const wingMat=new THREE.MeshStandardMaterial({color:0xdfe8ec,transparent:true,opacity:.36,roughness:.18,metalness:.02});
 const eyeMat=new THREE.MeshStandardMaterial({color:0x8d1818,emissive:0x5d0707,emissiveIntensity:.55,roughness:.32});
 const thorax=new THREE.Mesh(new THREE.SphereGeometry(.34,32,18),bodyMat);thorax.scale.set(.82,1,.7);thorax.position.set(0,.12,0);group.add(thorax);
 const abdomen=new THREE.Mesh(new THREE.SphereGeometry(.38,32,18),abdomenMat);abdomen.scale.set(.7,1.2,.62);abdomen.position.set(0,-.28,-.03);group.add(abdomen);
 for(let i=0;i<4;i++){const stripe=new THREE.Mesh(new THREE.TorusGeometry(.25+i*.018,.008,6,42),stripeMat);stripe.scale.set(1.25,.28,.5);stripe.position.set(0,-.08-i*.1,-.03);stripe.rotation.x=Math.PI/2;group.add(stripe);}
 const head=new THREE.Mesh(new THREE.SphereGeometry(.25,32,18),headMat);head.position.set(0,.49,.07);head.scale.set(1.1,.88,1);group.add(head);
 for(const x of [-.13,.13]){const eye=new THREE.Mesh(new THREE.SphereGeometry(.088,20,12),eyeMat);eye.name='eye';eye.position.set(x,.5,.28);eye.scale.set(1.05,1.2,.72);group.add(eye);}
 for(const x of [-.37,.37]){const wing=new THREE.Mesh(new THREE.SphereGeometry(.34,32,12),wingMat);wing.name='wing';wing.position.set(x,.14,-.04);wing.scale.set(.34,.055,1.08);wing.rotation.y=x<0?-.22:.22;group.add(wing);}
 const legMat=new THREE.MeshStandardMaterial({color:0x241c16,roughness:.68});
 for(const z of [-.16,.02,.2])for(const side of [-1,1]){const upper=new THREE.Mesh(new THREE.CapsuleGeometry(.012,.34,4,8),legMat);upper.position.set(side*.2,-.28,z);upper.rotation.z=side*.95;upper.rotation.x=.85;group.add(upper);const lower=new THREE.Mesh(new THREE.CapsuleGeometry(.01,.3,4,8),legMat);lower.position.set(side*.43,-.48,z+.05);lower.rotation.z=side*1.25;lower.rotation.x=1.1;group.add(lower);}
 for(const x of [-.09,.09]){const antenna=new THREE.Mesh(new THREE.CapsuleGeometry(.008,.27,4,8),legMat);antenna.position.set(x,.72,.08);antenna.rotation.z=x<0?.55:-.55;group.add(antenna);}
 return group;
}

function createController(THREE:typeof import('three')){
 const group=new THREE.Group();
 const shell=new THREE.Mesh(new THREE.BoxGeometry(1.45,.28,.42),new THREE.MeshStandardMaterial({color:0x191b1d,roughness:.62,metalness:.28}));group.add(shell);
 const colors=[0x9aa5a8,0x9aa5a8,0x7892a8,0xd18a35,0xc77e35,0xe2b36f];
 colors.forEach((color,index)=>{const button=new THREE.Mesh(new THREE.CylinderGeometry(.07,.07,.04,20),new THREE.MeshStandardMaterial({color,emissive:color,emissiveIntensity:.5}));button.name='button'+index;button.rotation.x=Math.PI/2;button.position.set(-.5+index*.2,.05,.13);group.add(button);});
 return group;
}
