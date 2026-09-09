import {useEffect,useRef} from 'react';
import Phaser from 'phaser';
import type {Engine} from './engine';
import type {Fighter} from '../../../packages/sim/core';
export function Arena({engine}:{engine:Engine}){
 const host=useRef<HTMLDivElement>(null);
 useEffect(()=>{
  class Ring extends Phaser.Scene{
   ink!:Phaser.GameObjects.Graphics;
   create(){this.ink=this.add.graphics();}
   update(_time:number,delta:number){
    engine.update(delta);const g=this.ink;g.clear();
    const floor=390,frame=engine.state.frame;
    g.fillStyle(0x222429);g.fillRect(0,0,1000,500);
    // Atmospheric architectural geometry, all generated locally.
    g.fillStyle(0x292b33);g.fillCircle(520,230,210);g.lineStyle(1,0x46414d,.35);
    for(let r=110;r<=290;r+=60)g.strokeCircle(500,240,r);
    g.lineStyle(1,0x40434b,.6);
    for(let x=0;x<1050;x+=60){g.lineBetween(x,390,500+(x-500)*1.6,500);}
    for(let y=390;y<500;y+=22)g.lineBetween(0,y,1000,y);
    g.lineStyle(1,0xb0a2c7,.55);g.lineBetween(30,floor,970,floor);
    g.fillStyle(0xb9a4e8,.04);g.fillTriangle(150,30,70,390,350,390);g.fillTriangle(850,30,650,390,930,390);
    for(let x=55;x<960;x+=32){g.fillStyle(0x70737b,.6);g.fillRect(x,390,1,x%3===0?12:5);}
    for(let i=0;i<2;i++)this.drawFighter(g,engine.state.fighters[i],i===0?0xc8df9a:0xb7a0e3,floor,frame,i===1);
    for(const h of engine.state.hits){
     const life=1-(frame-h.frame)/18, x=h.x,y=floor-h.y;
     g.lineStyle(2,h.blocked?0xc8df9a:0xe6d3a1,life);
     for(let i=0;i<8;i++){const a=i*Math.PI/4;g.lineBetween(x+Math.cos(a)*(22-life*14),y+Math.sin(a)*(22-life*14),x+Math.cos(a)*(45-life*20),y+Math.sin(a)*(45-life*20));}
    }
   }
   drawFighter(g:Phaser.GameObjects.Graphics,f:Fighter,color:number,floor:number,frame:number,neural:boolean){
    const x=f.x,y=floor-f.y,dir=f.face,walk=Math.sin(frame*.25)*Math.min(1,Math.abs(f.vx)/4),crouch=f.block?10:0,hit=f.stun?Math.sin(frame*2)*3:0;
    g.fillStyle(0x08090c,.35);g.fillEllipse(x,floor+8,75-f.y*.15,12);
    if(f.invul){g.lineStyle(2,color,.3);g.strokeEllipse(x-dir*20,y-43,60,90);}
    const hip={x:x-dir*4+hit,y:y-38+crouch},chest={x:x+dir*2+hit,y:y-73+crouch};
    g.lineStyle(11,0x16181d,1);g.lineBetween(hip.x,hip.y,x-15-walk*9,y-4);g.lineBetween(hip.x,hip.y,x+18+walk*9,y-4);
    g.lineStyle(5,color,.8);g.lineBetween(hip.x,hip.y,x-15-walk*9,y-4);g.lineBetween(hip.x,hip.y,x+18+walk*9,y-4);
    g.fillStyle(color);g.fillTriangle(chest.x-dir*15,chest.y, chest.x+dir*17,chest.y+4,hip.x,hip.y+6);
    g.fillStyle(0x32313b);g.fillTriangle(chest.x-dir*12,chest.y+6,hip.x,hip.y+6,hip.x-dir*12,hip.y-4);
    const attacking=!!f.attack,extension=attacking?Math.sin(Math.min(1,f.attackFrame/(f.attack===6?17:10))*Math.PI)*63:0;
    const fistX=chest.x+dir*(f.block?18:26+extension),fistY=chest.y+(f.block?-15:6);
    g.lineStyle(7,color);g.lineBetween(chest.x,chest.y+7,chest.x-dir*18,chest.y+24);
    g.lineBetween(chest.x-dir*18,chest.y+24,chest.x+dir*5,chest.y+24);
    g.lineBetween(chest.x+dir*8,chest.y+8,fistX,fistY);
    g.fillStyle(color);g.fillRoundedRect(fistX-7,fistY-7,14,14,4);
    if(attacking&&extension>25){g.lineStyle(f.attack===6?5:2,color,.3);g.strokeEllipse(fistX-dir*5,fistY,42,38);}
    // Faceted mask, split visor, antennae distinguish the neural contender.
    const hx=chest.x+dir*4,hy=chest.y-17;
    g.fillStyle(color);g.fillPoints([{x:hx-13,y:hy-10},{x:hx+9,y:hy-12},{x:hx+dir*17,y:hy},{x:hx+7,y:hy+12},{x:hx-11,y:hy+9}],true);
    g.lineStyle(4,0x24262d);g.lineBetween(hx+dir*2,hy-1,hx+dir*13,hy-3);
    if(neural){g.lineStyle(2,color,.8);g.lineBetween(hx-5,hy-12,hx-12,hy-26);g.lineBetween(hx+5,hy-12,hx+12,hy-26);g.fillStyle(0xd5eeaf);g.fillCircle(hx-12,hy-26,2);g.fillCircle(hx+12,hy-26,2);}
    if(f.block){g.lineStyle(2,color,.6);g.beginPath();g.arc(x+dir*12,y-50,48,dir>0?-1.3:1.8,dir>0?1.3:4.5);g.strokePath();}
   }
  }
  const game=new Phaser.Game({type:Phaser.CANVAS,parent:host.current!,width:1000,height:500,backgroundColor:'#222429',scene:Ring,banner:false,audio:{noAudio:true},render:{antialias:true},scale:{mode:Phaser.Scale.FIT,autoCenter:Phaser.Scale.CENTER_BOTH}});
  const down=(e:KeyboardEvent)=>{if(e.target instanceof HTMLInputElement||e.target instanceof HTMLSelectElement||e.target instanceof HTMLTextAreaElement)return;if(['a','d','w','s','j','k','l',' '].includes(e.key.toLowerCase())){e.preventDefault();engine.keys.add(e.key.toLowerCase());}if(e.code==='Space')engine.paused=!engine.paused;};
  const up=(e:KeyboardEvent)=>engine.keys.delete(e.key.toLowerCase());
  const blur=()=>{engine.keys.clear();engine.paused=true;};
  window.addEventListener('keydown',down);window.addEventListener('keyup',up);window.addEventListener('blur',blur);
  return()=>{game.destroy(true);window.removeEventListener('keydown',down);window.removeEventListener('keyup',up);window.removeEventListener('blur',blur);};
 },[engine]);
 return <div className="phaser-host" ref={host} aria-label="Live fighting arena"/>;
}

