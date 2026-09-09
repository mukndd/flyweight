import {useEffect,useRef} from 'react';
import type {Engine} from './engine';
const COLORS=['#818995','#cde7a3','#bda6e9'];
export function Brain({engine}:{engine:Engine}){
 const canvas=useRef<HTMLCanvasElement>(null);
 useEffect(()=>{
  let raf=0;
  const draw=()=>{
   const el=canvas.current;if(!el)return;const ctx=el.getContext('2d');if(!ctx)return;
   const dpr=Math.min(window.devicePixelRatio,2),w=el.clientWidth,h=el.clientHeight;if(el.width!==w*dpr||el.height!==h*dpr){el.width=w*dpr;el.height=h*dpr;}
   ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
   const graph=engine.graph;
   ctx.strokeStyle='#363b42';ctx.lineWidth=.5;
   for(let x=10;x<w;x+=22)for(let y=10;y<h;y+=22){ctx.beginPath();ctx.moveTo(x-1,y);ctx.lineTo(x+1,y);ctx.stroke();}
   if(graph){
    const n=graph.ids.length;const points=graph.ids.map((_,i)=>{
     const role=graph.roles[i],angle=i*2.3999632297,rad=Math.sqrt((i+.5)/n);
     const x=role===1?w*.14:role===2?w*.86:w*.5+Math.cos(angle)*rad*w*.30;
     const y=role===0?h*.51+Math.sin(angle)*rad*h*.34:h*.22+((i*7)%23)/23*h*.57;
     return{x,y};
    });
    for(const [a,b,sign]of graph.edges){const p=points[a],q=points[b],v=(engine.activity[a]??0)+(engine.activity[b]??0);ctx.strokeStyle=sign>0?`rgba(164,190,148,${.07+v*.2})`:`rgba(182,147,185,${.07+v*.2})`;ctx.lineWidth=.5;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();}
    for(let i=0;i<n;i++){const p=points[i],v=engine.activity[i]??0,role=graph.roles[i];if(v>.04){ctx.fillStyle=COLORS[role]+'18';ctx.beginPath();ctx.arc(p.x,p.y,4+v*14,0,Math.PI*2);ctx.fill();}ctx.globalAlpha=.35+Math.min(.65,v*4);ctx.fillStyle=COLORS[role];ctx.beginPath();ctx.arc(p.x,p.y,role?2.6:1.3+v*3,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;}
   }else{ctx.fillStyle='#9ca1a7';ctx.font='12px monospace';ctx.textAlign='center';ctx.fillText('Waiting for neural service',w/2,h/2);ctx.fillText('Local demo has no neural activity',w/2,h/2+22);}
   ctx.fillStyle='#7e858b';ctx.font='9px monospace';ctx.textAlign='left';ctx.fillText('SENSORY',w*.08,h-18);ctx.textAlign='right';ctx.fillText('MOTOR',w*.92,h-18);
   raf=requestAnimationFrame(draw);
  };raf=requestAnimationFrame(draw);return()=>cancelAnimationFrame(raf);
 },[engine]);
 return <canvas className="brain-canvas" ref={canvas} aria-label="Sampled live neural activity. Schematic layout, not anatomical coordinates."/>;
}

