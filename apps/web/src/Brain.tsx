import {useEffect,useRef,useState} from 'react';
import type {Engine} from './engine';
const COLORS=['#929ca8','#cee8a3','#c3acec'];
export function Brain({engine}:{engine:Engine}){
 const canvas=useRef<HTMLCanvasElement>(null),points=useRef<{x:number;y:number}[]>([]);const[info,setInfo]=useState('');
 useEffect(()=>{
  let raf=0,last=0;const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const draw=(time:number)=>{
   raf=requestAnimationFrame(draw);if(time-last<(reduced?200:50))return;last=time;
   const el=canvas.current;if(!el)return;const ctx=el.getContext('2d');if(!ctx)return;const dpr=Math.min(devicePixelRatio,2),w=el.clientWidth,h=el.clientHeight;if(!w||!h)return;
   if(el.width!==w*dpr||el.height!==h*dpr){el.width=w*dpr;el.height=h*dpr;}ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
   const graph=engine.graph,live=engine.online&&engine.isNeural&&engine.mode!=='replay';
   ctx.strokeStyle='#41484d';ctx.lineWidth=.5;for(let x=10;x<w;x+=24)for(let y=10;y<h;y+=24){ctx.beginPath();ctx.moveTo(x-1,y);ctx.lineTo(x+1,y);ctx.stroke();}
   if(live&&graph&&graph.ids.length){
    const n=graph.ids.length;const positions=graph.ids.map((_,i)=>{const role=graph.roles[i],angle=i*2.3999632297,rad=Math.sqrt((i+.5)/n);return{x:role===1?w*.12:role===2?w*.88:w*.5+Math.cos(angle)*rad*w*.30,y:role===0?h*.48+Math.sin(angle)*rad*h*.37:h*.12+((i*7)%23)/23*h*.72};});points.current=positions;
    for(const[a,b,weight]of graph.edges){const p=positions[a],q=positions[b],value=Math.abs(engine.activity[a]??0)+Math.abs(engine.activity[b]??0);ctx.strokeStyle=weight>=0?`rgba(164,190,148,${.09+value*.23})`:`rgba(191,155,196,${.09+value*.23})`;ctx.lineWidth=.6;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();}
    for(let i=0;i<n;i++){const p=positions[i],v=Math.abs(engine.activity[i]??0),role=graph.roles[i];if(v>.04&&!reduced){ctx.fillStyle=COLORS[role]+'15';ctx.beginPath();ctx.arc(p.x,p.y,3+v*8,0,Math.PI*2);ctx.fill();}ctx.globalAlpha=.4+Math.min(.6,v*4);ctx.fillStyle=COLORS[role];ctx.beginPath();ctx.arc(p.x,p.y,role?2.4:1.2+v*3,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;}
    ctx.font='10px monospace';ctx.fillStyle='#a1b094';ctx.textAlign='left';ctx.fillText('Input',12,h-7);ctx.textAlign='right';ctx.fillStyle='#baa5d7';ctx.fillText('Output',w-12,h-7);
   }else{points.current=[];ctx.fillStyle='#a0aaa1';ctx.font='12px Arial';ctx.textAlign='center';ctx.fillText(engine.mode==='replay'?'No brain recording in this replay':'No active neural signals',w/2,h/2);}
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

