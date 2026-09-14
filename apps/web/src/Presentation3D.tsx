import {useEffect,useRef,useState} from 'react';
import type {Group,PerspectiveCamera,Scene,WebGLRenderer} from 'three';
import {presentationState,type PresentationState} from './presentation';
import type {Engine} from './engine';
import {animateFlyController,createController as createControllerRig,createDrosophila,type ControllerRig,type FlyRig} from './world3d';

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
  let renderer:WebGLRenderer|undefined,scene:Scene|undefined,camera:PerspectiveCamera|undefined,fly:FlyRig|undefined,controller:ControllerRig|undefined,arena:Group|undefined,raf=0,disposed=false;
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
   fly=createDrosophila(THREE);fly.group.position.set(0,.42,.12);fly.group.scale.setScalar(1.15);scene.add(fly.group);
   controller=createControllerRig(THREE);controller.group.position.set(0,-.26,.72);scene.add(controller.group);
   const resize=()=>{
    if(!host.current||!renderer||!camera)return;
    const rect=host.current.getBoundingClientRect(),w=Math.max(1,rect.width),h=Math.max(1,rect.height);
    renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
   };
   const draw=(time:number)=>{
    raf=requestAnimationFrame(draw);if(!renderer||!scene||!camera||!fly||!controller||!arena)return;
    resize();
    const s=stateRef.current,slow=reduced ? .15 : 1,t=time*.001*slow,pulse=s?.intensity??.25;
    animateFlyController(fly,controller,s?.action??0,s?.mood??'idle',s?.frame??0,t,reduced);
    fly.group.scale.setScalar(1.15+(s?.mood==='victory'? .08 : 0));
    fly.group.position.y=.42+Math.sin(t*(s?.mood==='offline'?1.4:6))*(.012+pulse*.015);
    controller.group.rotation.x=-.18+Math.sin(t*1.3)*.025;
    controller.group.rotation.z=Math.sin(t*1.1)*.04+(s?.mood==='dodge'? .13 : 0);
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
