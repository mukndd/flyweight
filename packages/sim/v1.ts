type Action=0|1|2|3|4|5|6|7;
function isAction(x:unknown):x is Action{return Number.isInteger(x)&&Number(x)>=0&&Number(x)<8;}
export const FPS=60, MAX_FRAMES=5400;
export type Difficulty='easy'|'medium'|'hard';
export type SceneName='standard'|'close-combat'|'boundary'|'airborne';
export interface Fighter {x:number;y:number;vx:number;vy:number;hp:number;face:number;stun:number;cooldown:number;dodgeCooldown:number;invul:number;attack:0|5|6;attackFrame:number;hasHit:boolean;block:boolean;action:Action;damage:number;blocks:number;}
export interface Match {v:1;seed:number;rng:number;frame:number;limit:number;scene:SceneName;fighters:[Fighter,Fighter];winner:null|0|1|2;hits:{x:number;y:number;frame:number;blocked:boolean}[];}
export interface Replay {v:1;seed:number;scene:SceneName;limit:number;actions:[Action,Action][];finalHash:string;controller:string;datasetHash:string;}
export function random(s:Match) {s.rng=(Math.imul(s.rng,1664525)+1013904223)>>>0;return s.rng/4294967296;}
const fighter=(x:number,face:number):Fighter=>({x,y:0,vx:0,vy:0,hp:100,face,stun:0,cooldown:0,dodgeCooldown:0,invul:0,attack:0,attackFrame:0,hasHit:false,block:false,action:0,damage:0,blocks:0});
export function createMatch(seed=783,scene:SceneName='standard',limit=2700):Match {
 if(!Number.isInteger(seed)||seed<0||seed>4294967295||!Number.isInteger(limit)||limit<60||limit>MAX_FRAMES||!['standard','close-combat','boundary','airborne'].includes(scene)) throw Error('Invalid match configuration');
 const s:Match={v:1,seed,rng:seed,frame:0,limit,scene,fighters:[fighter(300,1),fighter(700,-1)],winner:null,hits:[]};
 const offset=Math.floor(random(s)*41)-20;s.fighters[0].x+=offset;s.fighters[1].x-=offset;
 if(scene==='close-combat'){s.fighters[0].x=465;s.fighters[1].x=535;}
 if(scene==='boundary'){s.fighters[0].x=42;s.fighters[1].x=115;}
 if(scene==='airborne'){s.fighters[0].y=100;s.fighters[0].vy=0;}
 return s;
}
export function step(s:Match,actions:readonly [Action,Action]):Match {
 if(!actions.every(isAction))throw Error('Invalid action');
 if(s.winner!==null)return s;
 s.frame++;
 for(let i=0;i<2;i++){
  const f=s.fighters[i],o=s.fighters[1-i],a=actions[i];f.action=a;f.damage*=0.92;
  f.face=o.x>=f.x?1:-1;f.stun=Math.max(0,f.stun-1);f.cooldown=Math.max(0,f.cooldown-1);f.invul=Math.max(0,f.invul-1);f.dodgeCooldown=Math.max(0,f.dodgeCooldown-1);
  f.block=a===4&&f.y===0&&!f.attack&&!f.stun&&!f.invul;
  if(f.attack){f.attackFrame++;if(f.attackFrame>(f.attack===5?20:36)){f.attack=0;f.attackFrame=0;}}
  if(!f.stun&&!f.attack){
   if(a===7&&!f.dodgeCooldown&&f.y===0){f.invul=14;f.dodgeCooldown=75;f.vx=f.face*9;}
   else if(!f.invul)f.vx=a===1?-4:a===2?4:0;
   if(a===3&&f.y===0){f.vy=15;f.block=false;}
   if((a===5||a===6)&&!f.cooldown&&!f.invul){f.attack=a;f.attackFrame=0;f.hasHit=false;f.cooldown=a===5?26:48;f.vx=0;}
  }
  if(f.block)f.vx=0;
  f.x=Math.max(36,Math.min(964,f.x+f.vx));
  f.y=Math.max(0,f.y+f.vy);if(f.y>0)f.vy-=1;else f.vy=0;
  if(f.stun)f.vx*=0.82;
 }
 const [a,b]=s.fighters;
 if(Math.abs(a.x-b.x)<44&&Math.abs(a.y-b.y)<65){const dir=a.x<=b.x?1:-1;const push=(44-Math.abs(a.x-b.x))/2;a.x=Math.max(36,Math.min(964,a.x-dir*push));b.x=Math.max(36,Math.min(964,b.x+dir*push));}
 // Collect hits first: simultaneous active attacks can trade.
 const hits:{attacker:number;damage:number;blocked:boolean;heavy:boolean}[]=[];
 for(let i=0;i<2;i++){
  const f=s.fighters[i],o=s.fighters[1-i];const heavy=f.attack===6,active=heavy?11:5;
  if(f.attack&&!f.hasHit&&f.attackFrame>=active&&f.attackFrame<=active+4&&Math.abs(f.x-o.x)<(heavy?116:90)&&Math.abs(f.y-o.y)<75&&!o.invul){
   f.hasHit=true;const blocked=o.block;hits.push({attacker:i,damage:blocked?(heavy?4:1):(heavy?18:9),blocked,heavy});
  }
 }
 for(const h of hits){const f=s.fighters[h.attacker],o=s.fighters[1-h.attacker];o.hp=Math.max(0,o.hp-h.damage);o.damage+=h.damage/100;o.stun=h.blocked?4:h.heavy?20:11;o.vx=f.face*(h.heavy?9:5);if(!h.blocked)o.attack=0;else o.blocks++;s.hits.push({x:o.x,y:o.y+45,frame:s.frame,blocked:h.blocked});}
 s.hits=s.hits.filter(h=>s.frame-h.frame<18).slice(-12);
 if(a.hp<=0||b.hp<=0||s.frame>=s.limit)s.winner=a.hp===b.hp?2:a.hp>b.hp?0:1;
 return s;
}
export function policy(s:Match,i:0|1,difficulty:Difficulty):Action{
 const f=s.fighters[i],o=s.fighters[1-i],dx=o.x-f.x,d=Math.abs(dx),toward:Action=dx>0?2:1,away:Action=dx>0?1:2;
 if(difficulty==='easy'&&s.frame%24>8)return 0;
 if(o.attack&&d<125){if(difficulty==='hard'&&!f.dodgeCooldown&&s.frame%3===0)return 7;return 4;}
 const projected=difficulty==='hard'?Math.abs(dx+o.vx*6):d;
 if(projected<86&&!f.cooldown)return o.block||s.frame%90<25?6:5;
 if(d<55&&f.cooldown>12)return away;
 if(o.y>45&&difficulty==='hard'&&f.y===0)return 3;
 return d>78?toward:0;
}
export function observation(s:Match,i:0|1):number[]{
 const f=s.fighters[i],o=s.fighters[1-i];
 return [(o.x-f.x)/1000,(o.y-f.y)/150,o.vx/10,o.vy/15,f.vx/10,f.vy/15,Math.abs(o.x-f.x)/1000,o.attack?1:0,o.block?1:0,f.hp/100,o.hp/100,(f.x-36)/928,(964-f.x)/928,f.damage,f.action/7,1-s.frame/s.limit].map(v=>Math.max(-1,Math.min(1,v)));
}
export function hashState(s:Match):string {const str=JSON.stringify(s);let h=2166136261;for(let i=0;i<str.length;i++)h=Math.imul(h^str.charCodeAt(i),16777619);return (h>>>0).toString(16).padStart(8,'0');}
function keys(obj:object,expected:string[]){return Object.keys(obj).sort().join(',')===expected.sort().join(',');}
export function parseReplay(text:string):Replay{
 if(new TextEncoder().encode(text).length>1_000_000)throw Error('Replay exceeds 1 MB');
 const r=JSON.parse(text) as Replay;
 if(!r||typeof r!=='object'||!keys(r,['v','seed','scene','limit','actions','finalHash','controller','datasetHash'])||r.v!==1||!Array.isArray(r.actions)||r.actions.length>MAX_FRAMES||r.actions.length>r.limit||typeof r.finalHash!=='string'||!/^[a-f0-9]{8}$/.test(r.finalHash)||typeof r.controller!=='string'||r.controller.length>80||typeof r.datasetHash!=='string'||r.datasetHash.length>64)throw Error('Invalid replay schema');
 createMatch(r.seed,r.scene,r.limit);
 if(!r.actions.every(a=>Array.isArray(a)&&a.length===2&&a.every(isAction)))throw Error('Invalid replay actions');
 const s=playReplay(r);if(hashState(s)!==r.finalHash)throw Error('Replay integrity mismatch');
 return r;
}
export function playReplay(r:Replay){const s=createMatch(r.seed,r.scene,r.limit);for(const a of r.actions){if(s.winner!==null)throw Error('Frames after end');step(s,a);}return s;}

