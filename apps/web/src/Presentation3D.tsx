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
   scene.fog=new THREE.Fog(0x07070b,7,18);
   camera=new THREE.PerspectiveCamera(38,1,.1,100);
   camera.position.set(0,variant==='compact'?1.1:1.45,variant==='match'?7.2:7.8);
   renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:'high-performance',preserveDrawingBuffer:true});
   renderer.setPixelRatio(Math.min(devicePixelRatio,1.75));
   renderer.setClearColor(0x000000,0);
   host.current.appendChild(renderer.domElement);
   scene.add(new THREE.AmbientLight(0x7d86a0,1.6));
   const purple=new THREE.PointLight(0xd052ff,variant==='match'?45:60,12);purple.position.set(3,4,3);scene.add(purple);
   const green=new THREE.PointLight(0xb7ff5f,35,10);green.position.set(-4,3,2);scene.add(green);
   const top=new THREE.DirectionalLight(0xffffff,2.4);top.position.set(0,7,5);scene.add(top);
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
    eyes.forEach(eye=>{const mat=eye.material as MeshStandardMaterial;mat.emissiveIntensity=s?.online?1.4+pulse:0.35;});
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
 const mat=new THREE.MeshStandardMaterial({color:0x11141d,roughness:.74,metalness:.18});
 const floor=new THREE.Mesh(new THREE.CylinderGeometry(2.8,3.2,.16,6),mat);floor.position.y=-.7;floor.rotation.y=Math.PI/6;group.add(floor);
 const ring=new THREE.Mesh(new THREE.TorusGeometry(2.7,.018,8,96),new THREE.MeshStandardMaterial({color:0x7f6ab5,emissive:0x7f35ff,emissiveIntensity:.35}));ring.rotation.x=Math.PI/2;ring.position.y=-.55;group.add(ring);
 for(let i=0;i<8;i++){const angle=i*Math.PI/4,x=Math.cos(angle)*2.9,z=Math.sin(angle)*2.9;const post=new THREE.Mesh(new THREE.BoxGeometry(.04,1.2,.04),new THREE.MeshStandardMaterial({color:i<4?0xc8ff72:0xd15dff,emissive:i<4?0x6fff23:0xa100ff,emissiveIntensity:.25}));post.position.set(x,-.05,z);group.add(post);}
 if(variant!=='compact')for(let i=0;i<18;i++){const light=new THREE.Mesh(new THREE.BoxGeometry(.08,.08,.08),new THREE.MeshStandardMaterial({color:0xf2f5ff,emissive:i%2?0xd95cff:0xbaff63,emissiveIntensity:.8}));light.position.set((i-8.5)*.34,2.2,-2.4);group.add(light);}
 return group;
}

function createFly(THREE:typeof import('three')){
 const group=new THREE.Group();
 const bodyMat=new THREE.MeshStandardMaterial({color:0x8c42d7,emissive:0x6211a8,emissiveIntensity:.55,roughness:.42,metalness:.08});
 const headMat=new THREE.MeshStandardMaterial({color:0xb56bff,emissive:0x8f2cff,emissiveIntensity:.5,roughness:.38});
 const wingMat=new THREE.MeshStandardMaterial({color:0xecf2ff,transparent:true,opacity:.43,roughness:.2,metalness:.05});
 const eyeMat=new THREE.MeshStandardMaterial({color:0x171018,emissive:0xf05cff,emissiveIntensity:1.2});
 const body=new THREE.Mesh(new THREE.SphereGeometry(.42,32,18),bodyMat);body.scale.set(.78,1.05,.62);group.add(body);
 const head=new THREE.Mesh(new THREE.SphereGeometry(.28,32,18),headMat);head.position.set(0,.42,.08);head.scale.set(1.08,.9,1);group.add(head);
 for(const x of [-.13,.13]){const eye=new THREE.Mesh(new THREE.SphereGeometry(.07,16,10),eyeMat);eye.name='eye';eye.position.set(x,.47,.32);group.add(eye);}
 for(const x of [-.36,.36]){const wing=new THREE.Mesh(new THREE.SphereGeometry(.32,24,12),wingMat);wing.name='wing';wing.position.set(x,.12,-.05);wing.scale.set(.32,.08,.95);group.add(wing);}
 const legMat=new THREE.MeshStandardMaterial({color:0xbadf6e,emissive:0x648f31,emissiveIntensity:.35});
 for(const x of [-.24,0,.24])for(const side of [-1,1]){const leg=new THREE.Mesh(new THREE.CapsuleGeometry(.015,.42,4,8),legMat);leg.position.set(x+side*.24,-.35,.05);leg.rotation.z=side*.72;leg.rotation.x=.7;group.add(leg);}
 for(const x of [-.09,.09]){const antenna=new THREE.Mesh(new THREE.CapsuleGeometry(.01,.3,4,8),legMat);antenna.position.set(x,.72,.08);antenna.rotation.z=x<0?.55:-.55;group.add(antenna);}
 return group;
}

function createController(THREE:typeof import('three')){
 const group=new THREE.Group();
 const shell=new THREE.Mesh(new THREE.BoxGeometry(1.45,.32,.42),new THREE.MeshStandardMaterial({color:0x1b2028,roughness:.62,metalness:.22,emissive:0x15102a,emissiveIntensity:.2}));group.add(shell);
 const colors=[0xbaff63,0xbaff63,0x7ee8ff,0xd75cff,0xff8652,0xffd166];
 colors.forEach((color,index)=>{const button=new THREE.Mesh(new THREE.CylinderGeometry(.07,.07,.04,20),new THREE.MeshStandardMaterial({color,emissive:color,emissiveIntensity:.5}));button.name='button'+index;button.rotation.x=Math.PI/2;button.position.set(-.5+index*.2,.05,.13);group.add(button);});
 return group;
}
