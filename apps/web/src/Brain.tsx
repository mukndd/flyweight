import {useEffect,useRef,useState} from 'react';
import type {Engine} from './engine';
const COLORS=['#4e606b','#7d919b','#d29343'];
export function Brain({engine}:{engine:Engine}){
 const canvas=useRef<HTMLCanvasElement>(null),points=useRef<{x:number;y:number;z:number}[]>([]),display=useRef<number[]>([]);const[info,setInfo]=useState('');
 useEffect(()=>{
  let raf=0,last=0;const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const draw=(time:number)=>{
   raf=requestAnimationFrame(draw);if(time-last<(reduced?200:50))return;last=time;
   const el=canvas.current;if(!el)return;const ctx=el.getContext('2d');if(!ctx)return;const dpr=Math.min(devicePixelRatio,2),w=el.clientWidth,h=el.clientHeight;if(!w||!h)return;
   if(el.width!==w*dpr||el.height!==h*dpr){el.width=w*dpr;el.height=h*dpr;}ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
   const graph=engine.graph,live=engine.online&&engine.isNeural&&engine.mode!=='replay';
   const bg=ctx.createLinearGradient(0,0,w,h);bg.addColorStop(0,'#0b0f10');bg.addColorStop(1,'#11100d');ctx.fillStyle=bg;ctx.fillRect(0,0,w,h);
   ctx.strokeStyle='rgba(105,118,119,.12)';ctx.lineWidth=.5;for(let x=18;x<w;x+=30){ctx.beginPath();ctx.moveTo(x,12);ctx.lineTo(x,h-12);ctx.stroke();}for(let y=18;y<h;y+=30){ctx.beginPath();ctx.moveTo(12,y);ctx.lineTo(w-12,y);ctx.stroke();}
   if(live&&graph&&graph.ids.length){
    const n=graph.ids.length;
    if(display.current.length!==n)display.current=new Array(n).fill(0);
    const positions=graph.ids.map((_,i)=>{const role=graph.roles[i],angle=i*2.3999632297,rad=Math.sqrt((i+.5)/n),z=Math.sin(i*1.71)*.5+.5;return{x:role===1?w*.14:role===2?w*.86:w*.5+Math.cos(angle)*rad*w*.32,y:role===0?h*.5+Math.sin(angle)*rad*h*.35:h*.14+((i*7)%23)/23*h*.68,z};});points.current=positions;
    for(let i=0;i<n;i++){const target=Math.abs(engine.activity[i]??0);display.current[i]=Math.max(target,display.current[i]*(reduced ? .86 : .92));}
    const activeEdges=graph.edges.map(edge=>({edge,value:display.current[edge[0]]+display.current[edge[1]]})).sort((a,b)=>b.value-a.value).slice(0,42);
    ctx.lineCap='round';
    for(const[a,b,weight]of graph.edges){const p=positions[a],q=positions[b],depth=(p.z+q.z)/2;ctx.strokeStyle=weight>=0?`rgba(126,94,48,${.025+depth*.045})`:`rgba(80,99,111,${.025+depth*.04})`;ctx.lineWidth=.35+depth*.35;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.quadraticCurveTo((p.x+q.x)/2,(p.y+q.y)/2-8*(depth-.5),q.x,q.y);ctx.stroke();}
    activeEdges.forEach(({edge,value})=>{if(value<.035)return;const [a,b,weight]=edge,p=positions[a],q=positions[b],alpha=Math.min(.74,.12+value*.45);ctx.strokeStyle=weight>=0?`rgba(238,180,82,${alpha})`:`rgba(156,187,199,${alpha*.72})`;ctx.lineWidth=Math.min(3,.75+value*2.4);ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.quadraticCurveTo((p.x+q.x)/2,(p.y+q.y)/2-14,q.x,q.y);ctx.stroke();});
    for(let i=0;i<n;i++){const p=positions[i],v=display.current[i],role=graph.roles[i],active=v>.035,size=(role?2.5:1.35)+p.z*1.1+v*5.8;if(active&&!reduced){const glow=ctx.createRadialGradient(p.x,p.y,1,p.x,p.y,10+v*18);glow.addColorStop(0,`rgba(238,180,82,${.18+v*.22})`);glow.addColorStop(1,'rgba(238,180,82,0)');ctx.fillStyle=glow;ctx.beginPath();ctx.arc(p.x,p.y,10+v*18,0,Math.PI*2);ctx.fill();}ctx.globalAlpha=.32+p.z*.24+Math.min(.44,v*3.5);ctx.fillStyle=active?'#eeb452':COLORS[role];ctx.beginPath();ctx.arc(p.x,p.y,size,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;}
    ctx.font='11px Arial';ctx.fillStyle='rgba(125,145,155,.82)';ctx.textAlign='left';ctx.fillText('sensory input',14,h-10);ctx.textAlign='right';ctx.fillStyle='rgba(238,180,82,.9)';ctx.fillText('motor readout',w-14,h-10);
   }else{points.current=[];ctx.fillStyle='#8d918c';ctx.font='12px Arial';ctx.textAlign='center';ctx.fillText(engine.mode==='replay'?'No brain recording in this replay':'No active neural signals',w/2,h/2);}
  };raf=requestAnimationFrame(draw);return()=>cancelAnimationFrame(raf);
 },[engine]);
 const inspect=(clientX:number,clientY:number)=>{
  const el=canvas.current,g=engine.graph;if(!el||!g||!points.current.length){setInfo('');return;}const r=el.getBoundingClientRect(),x=clientX-r.left,y=clientY-r.top;
  let nearest=-1,distance=49;points.current.forEach((p,i)=>{const d=(p.x-x)**2+(p.y-y)**2;if(d<distance){distance=d;nearest=i;}});
  if(nearest>=0){setInfo(`${g.ids[nearest]} · ${['Internal','Stimulated input','Motor readout'][g.roles[nearest]]} · activity ${(engine.activity[nearest]??0).toFixed(6)}`);return;}
  for(const[a,b,weight]of g.edges){const p=points.current[a],q=points.current[b],dx=q.x-p.x,dy=q.y-p.y,t=Math.max(0,Math.min(1,((x-p.x)*dx+(y-p.y)*dy)/(dx*dx+dy*dy||1)));if(Math.hypot(x-p.x-dx*t,y-p.y-dy*t)<2){setInfo(`${g.ids[a]} → ${g.ids[b]} · effective weight ${weight.toFixed(6)} (normalized)`);return;}}
  setInfo('');
 };
 return <div className="brain-canvas-wrap"><canvas className="brain-canvas" ref={canvas} aria-label="Sampled real neural signals. Hover a neuron or connection for its measured value." onPointerMove={e=>inspect(e.clientX,e.clientY)} onClick={e=>inspect(e.clientX,e.clientY)} onPointerLeave={()=>setInfo('')}/>{info&&<div className="neuron-tooltip" role="status">{info}</div>}</div>;
}

