import {useEffect,useRef,useState} from 'react';
import type {Group,Mesh,PerspectiveCamera,Scene,WebGLRenderer} from 'three';
import type {Engine} from './engine';
import {createController,createDrosophila,createFighter,createTestChamber,animateFlyController,moodForAction,updateFighter,type ControllerRig,type FighterRig,type FlyRig} from './world3d';

function canUseWebGL(){
 try{
  const canvas=document.createElement('canvas');
  return !!(canvas.getContext('webgl2')||canvas.getContext('webgl'));
 }catch{return false;}
}

export function CombatWorld3D({engine}:{engine:Engine}){
 const host=useRef<HTMLDivElement>(null);
 const [failed,setFailed]=useState(false);
 useEffect(()=>{
  if(!host.current||!canUseWebGL()){setFailed(true);return;}
  let renderer:WebGLRenderer|undefined,scene:Scene|undefined,camera:PerspectiveCamera|undefined,fly:FlyRig|undefined,controller:ControllerRig|undefined;
  let opponent:FighterRig|undefined,neural:FighterRig|undefined,station:Group|undefined;const sparks:Mesh[]=[];let raf=0,last=performance.now(),disposed=false;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  import('three').then(THREE=>{
   if(disposed||!host.current)return;
   scene=new THREE.Scene();
   scene.fog=new THREE.Fog(0x111312,8,17);
   camera=new THREE.PerspectiveCamera(35,1,.1,80);
   camera.position.set(-.15,2.45,7.25);
   renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,powerPreference:'high-performance',preserveDrawingBuffer:true});
   renderer.setPixelRatio(Math.min(devicePixelRatio,1.6));
   renderer.setClearColor(0x111312,1);
   renderer.shadowMap.enabled=true;
   renderer.shadowMap.type=THREE.PCFSoftShadowMap;
   host.current.appendChild(renderer.domElement);

   scene.add(createTestChamber(THREE));
   scene.add(new THREE.HemisphereLight(0xaab8c0,0x19120d,.85));
   const key=new THREE.SpotLight(0xf3c68a,54,12,.48,.45,1.3);key.position.set(-3.4,5.2,3.7);key.castShadow=true;key.shadow.mapSize.set(1024,1024);scene.add(key);
   const flyKey=new THREE.SpotLight(0xffd59b,42,9,.55,.35,1.2);flyKey.position.set(2.8,3.4,2.7);flyKey.castShadow=true;scene.add(flyKey);
   const rim=new THREE.DirectionalLight(0xa8c6d8,2.4);rim.position.set(3.5,2.8,-3.5);scene.add(rim);

   opponent=createFighter(THREE,false);neural=createFighter(THREE,true);
   scene.add(opponent.shadow,neural.shadow,opponent.group,neural.group);

   station=new THREE.Group();
   fly=createDrosophila(THREE);controller=createController(THREE);
   const table=new THREE.Mesh(new THREE.BoxGeometry(2.45,.13,1.18),new THREE.MeshStandardMaterial({color:0x2a2c2a,roughness:.72,metalness:.16}));
   table.position.set(0,-.08,0);table.castShadow=true;table.receiveShadow=true;station.add(table);
   controller.group.position.set(0,.08,.1);controller.group.rotation.x=-.06;station.add(controller.group);
   fly.group.position.set(0,.38,.26);fly.group.scale.setScalar(1.08);station.add(fly.group);
   station.position.set(-2.12,.44,1.02);station.rotation.y=.44;station.scale.setScalar(1.02);scene.add(station);
   flyKey.target=station;scene.add(flyKey.target);

   const sparkMat=new THREE.MeshBasicMaterial({color:0xf3bf66,transparent:true,opacity:0,depthWrite:false});
   for(let i=0;i<12;i++){
    const spark=new THREE.Mesh(new THREE.SphereGeometry(.045,12,8),sparkMat.clone());
    spark.visible=false;scene.add(spark);sparks.push(spark);
   }

   const resize=()=>{
    if(!host.current||!renderer||!camera)return;
    const rect=host.current.getBoundingClientRect();
    const w=Math.max(1,Math.floor(rect.width)),h=Math.max(1,Math.floor(rect.height));
    renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
   };
   const draw=(now:number)=>{
    raf=requestAnimationFrame(draw);if(!renderer||!scene||!camera||!opponent||!neural||!fly||!controller||!station)return;
    resize();
    const delta=now-last;last=now;engine.update(delta);
    const state=engine.state,t=now*.001;
    updateFighter(opponent,state.fighters[0],state.frame,false);
    updateFighter(neural,state.fighters[1],state.frame,true);
    const action=state.fighters[1].action;
    animateFlyController(fly,controller,action,moodForAction(action,state.winner),state.frame,t,reduced);
    station.position.y=.44+Math.sin(t*1.2)*.012;
    station.rotation.y=.44+Math.sin(t*.35)*.025;
    state.hits.forEach((hit,i)=>{
     const spark=sparks[i];if(!spark)return;
     const life=Math.max(0,1-(state.frame-hit.frame)/18);
     spark.visible=life>0;spark.position.set((hit.x-500)/125,.28+hit.y/95,hit.blocked?-.09:.12);
     spark.scale.setScalar((hit.blocked ? .7 : 1.1)*life);
     const mat=spark.material as import('three').MeshBasicMaterial;
     mat.color.setHex(hit.blocked?0xb6c2c5:0xf3bf66);mat.opacity=life*.78;
    });
    for(let i=state.hits.length;i<sparks.length;i++)sparks[i].visible=false;
    const leader=state.fighters[1],stress=state.hits.some(hit=>state.frame-hit.frame<8) ? .06 : 0;
    camera.position.x=-.08+(leader.x-500)/1200+Math.sin(t*.7)*.025+stress*Math.sin(t*38);
    camera.position.y=2.34+Math.sin(t*.23)*.035;
    camera.position.z=7.1+Math.sin(t*.31)*.04;
    camera.lookAt(-.12,.88,.05);
    renderer.render(scene,camera);
   };
   resize();draw(last);
  }).catch(()=>setFailed(true));
  const down=(e:KeyboardEvent)=>{
   if(document.querySelector('dialog[open]'))return;
   if(e.code==='Space'&&e.target instanceof HTMLButtonElement)return;
   if(e.target instanceof HTMLInputElement||e.target instanceof HTMLSelectElement||e.target instanceof HTMLTextAreaElement)return;
   if(['a','d','w','s','c','j','k','l',' '].includes(e.key.toLowerCase())){e.preventDefault();engine.keys.add(e.key.toLowerCase());}
   if(e.code==='Space'&&!e.repeat)engine.paused=!engine.paused;
  };
  const up=(e:KeyboardEvent)=>engine.keys.delete(e.key.toLowerCase());
  const blur=()=>{engine.keys.clear();engine.paused=true;};
  window.addEventListener('keydown',down);window.addEventListener('keyup',up);window.addEventListener('blur',blur);
  return()=>{
   disposed=true;cancelAnimationFrame(raf);
   window.removeEventListener('keydown',down);window.removeEventListener('keyup',up);window.removeEventListener('blur',blur);
   renderer?.dispose();if(renderer?.domElement.parentElement)renderer.domElement.remove();
  };
 },[engine]);
 return <div className={`combat-world3d ${failed?'fallback':''}`} ref={host} aria-label="3D neural combat test chamber">{failed&&<div className="combat-fallback">3D renderer unavailable</div>}</div>;
}
