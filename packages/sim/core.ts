import {ACTIONS,type Action,isAction} from '../protocol/index.js';
import * as legacy from './v1.js';
export const FPS=60,MAX_FRAMES=5400;
export type Difficulty='easy'|'medium'|'hard';
export type OpponentProfile='standard'|'aggressive'|'defensive'|'counter-focused'|'mobile'|'mixed';
export type SceneName='standard'|'close-combat'|'boundary'|'airborne';
export interface Fighter{x:number;y:number;vx:number;vy:number;hp:number;face:number;stun:number;cooldown:number;dodgeCooldown:number;invul:number;attack:Action;attackFrame:number;hasHit:boolean;block:boolean;action:Action;damage:number;blocks:number;crouch?:boolean;combo?:number;comboWindow?:number;guardFrames?:number;idleTicks?:number;}
export interface CombatEvent{frame:number;actor:0|1;target:0|1;type:'hit'|'blocked'|'miss'|'counter'|'shove'|'combo';action:Action;damage:number;}
export interface Match{v:1|2;seed:number;rng:number;frame:number;limit:number;scene:SceneName;fighters:[Fighter,Fighter];winner:null|0|1|2;hits:{x:number;y:number;frame:number;blocked:boolean}[];events?:CombatEvent[];}
export interface Replay{v:2;engine:'combat-v2';seed:number;scene:SceneName;limit:number;actions:[Action,Action][];finalHash:string;controller:string;datasetHash:string;difficulty:Difficulty;checkpoint:string;checkpointHash:string;controlMode:string;sourceSegments:{frame:number;controller:string;checkpoint:string}[];profile?:OpponentProfile;}
export type AnyReplay=Replay|legacy.Replay;
export interface Decision{action:Action;rule:string;reason:string;frame:number;}
const fighter=(x:number,face:number):Fighter=>({x,y:0,vx:0,vy:0,hp:100,face,stun:0,cooldown:0,dodgeCooldown:0,invul:0,attack:0,attackFrame:0,hasHit:false,block:false,action:0,damage:0,blocks:0,crouch:false,combo:0,comboWindow:0,guardFrames:0,idleTicks:0});
export function random(s:Match){s.rng=(Math.imul(s.rng,1664525)+1013904223)>>>0;return s.rng/4294967296;}
export function createMatch(seed=783,scene:SceneName='standard',limit=2700):Match{
 if(!Number.isInteger(seed)||seed<0||seed>4294967295||!Number.isInteger(limit)||limit<60||limit>MAX_FRAMES||!['standard','close-combat','boundary','airborne'].includes(scene))throw Error('Invalid match configuration');
 const s:Match={v:2,seed,rng:seed,frame:0,limit,scene,fighters:[fighter(300,1),fighter(700,-1)],winner:null,hits:[],events:[]};
 const offset=Math.floor(random(s)*41)-20;s.fighters[0].x+=offset;s.fighters[1].x-=offset;
 if(scene==='close-combat'){s.fighters[0].x=465;s.fighters[1].x=535;}
 if(scene==='boundary'){s.fighters[0].x=42;s.fighters[1].x=115;}
 if(scene==='airborne'){s.fighters[0].y=100;s.fighters[0].vy=0;}return s;
}
export const MOVES:Partial<Record<Action,{startup:number;recovery:number;cooldown:number;range:number;damage:number;kind:'high'|'low'|'air'|'throw'}>>={
 5:{startup:5,recovery:18,cooldown:23,range:90,damage:8,kind:'high'},
 6:{startup:12,recovery:35,cooldown:45,range:112,damage:17,kind:'high'},
 9:{startup:7,recovery:23,cooldown:30,range:96,damage:7,kind:'low'},
 10:{startup:9,recovery:27,cooldown:34,range:103,damage:10,kind:'high'},
 11:{startup:4,recovery:21,cooldown:29,range:100,damage:11,kind:'air'},
 12:{startup:9,recovery:30,cooldown:52,range:69,damage:3,kind:'throw'},
 13:{startup:9,recovery:37,cooldown:48,range:119,damage:22,kind:'high'}
};
export function step(s:Match,actions:readonly[Action,Action]):Match{
 if(s.v===1)return legacy.step(s as legacy.Match,actions as [legacy.Replay['actions'][number][0],legacy.Replay['actions'][number][1]]);
 if(!actions.every(isAction))throw Error('Invalid action');if(s.winner!==null)return s;
 s.frame++;const events=s.events!;
 for(let i=0;i<2;i++){
  const f=s.fighters[i],o=s.fighters[1-i],a=actions[i];f.action=a;f.damage*=.92;f.face=o.x>=f.x?1:-1;
  f.stun=Math.max(0,f.stun-1);f.cooldown=Math.max(0,f.cooldown-1);f.invul=Math.max(0,f.invul-1);f.dodgeCooldown=Math.max(0,f.dodgeCooldown-1);
  f.comboWindow=Math.max(0,(f.comboWindow??0)-1);if(!f.comboWindow)f.combo=0;
  f.idleTicks=(f.idleTicks??0)+(a===0?1:0);
  const oldBlock=f.block;f.crouch=a===8&&f.y===0&&!f.attack&&!f.stun;f.block=(a===4||a===8)&&f.y===0&&!f.attack&&!f.stun&&!f.invul;
  f.guardFrames=f.block?(oldBlock?(f.guardFrames??0)+1:1):0;
  if(f.attack){f.attackFrame++;const move=MOVES[f.attack]!;if(f.attackFrame>move.recovery){if(!f.hasHit)events.push({frame:s.frame,actor:i as 0|1,target:(1-i) as 0|1,type:'miss',action:f.attack,damage:0});f.attack=0;f.attackFrame=0;}}
  if(!f.stun&&!f.attack){
   if(a===7&&!f.dodgeCooldown&&f.y===0){f.invul=14;f.dodgeCooldown=75;f.vx=f.face*9;f.combo=0;}
   else if(!f.invul)f.vx=a===1?-4:a===2?4:0;
   if(a===3&&f.y===0){f.vy=15;f.block=false;}
   const move=MOVES[a];
   const eligible=(a!==11||f.y>0)&&(a!==13||(f.combo??0)>=2)&&(a!==9&&a!==12||f.y===0);
   if(move&&eligible&&!f.cooldown&&!f.invul){f.attack=a;f.attackFrame=0;f.hasHit=false;f.cooldown=move.cooldown;f.vx=a===10?f.face*4:0;f.block=false;}
  }
  if(f.block)f.vx=0;
  f.x=Math.max(36,Math.min(964,f.x+f.vx));f.y=Math.max(0,f.y+f.vy);if(f.y>0)f.vy-=1;else f.vy=0;if(f.stun)f.vx*=.82;
 }
 const [a,b]=s.fighters;if(Math.abs(a.x-b.x)<44&&Math.abs(a.y-b.y)<65){const dir=a.x<=b.x?1:-1,push=(44-Math.abs(a.x-b.x))/2;a.x=Math.max(36,Math.min(964,a.x-dir*push));b.x=Math.max(36,Math.min(964,b.x+dir*push));}
 const landed:{actor:0|1;action:Action;blocked:boolean;counter:boolean;damage:number}[]=[];
 for(let i=0;i<2;i++){const f=s.fighters[i],o=s.fighters[1-i],m=MOVES[f.attack];if(!m||f.hasHit||f.attackFrame<m.startup||f.attackFrame>m.startup+4||o.invul)continue;
  const reaches=Math.abs(f.x-o.x)<m.range&&Math.abs(f.y-o.y)<(m.kind==='air'?130:75)&&!(m.kind==='low'&&o.y>30);
  if(reaches){f.hasHit=true;const blocked=o.block&&m.kind!=='throw'&&(m.kind==='low'?!!o.crouch:!o.crouch);const counter=blocked&&(o.guardFrames??0)<=4;landed.push({actor:i as 0|1,action:f.attack,blocked,counter,damage:counter?0:blocked?Math.max(1,Math.floor(m.damage/5)):m.damage});}
 }
 for(const h of landed){const f=s.fighters[h.actor],o=s.fighters[1-h.actor],m=MOVES[h.action]!;o.hp=Math.max(0,o.hp-h.damage);o.damage+=h.damage/100;
  if(h.counter){f.stun=16;f.attack=0;f.cooldown=Math.max(f.cooldown,22);o.blocks++;}
  else{o.stun=h.blocked?5:m.kind==='throw'?15:h.action===6||h.action===13?21:10;o.vx=f.face*(m.kind==='throw'?18:h.action===6||h.action===13?10:5);if(!h.blocked){o.attack=0;o.combo=0;if(h.action===5){f.combo=Math.min(2,(f.combo??0)+1);f.comboWindow=55;}else if(h.action===13){f.combo=0;f.comboWindow=0;}}else o.blocks++;}
  events.push({frame:s.frame,actor:h.actor,target:(1-h.actor) as 0|1,type:h.counter?'counter':h.blocked?'blocked':h.action===12?'shove':h.action===13?'combo':'hit',action:h.action,damage:h.damage});
  s.hits.push({x:o.x,y:o.y+(m.kind==='low'?18:45),frame:s.frame,blocked:h.blocked});
 }
 s.events=events.slice(-64);s.hits=s.hits.filter(h=>s.frame-h.frame<18).slice(-12);
 if(a.hp<=0||b.hp<=0||s.frame>=s.limit)s.winner=a.hp===b.hp?2:a.hp>b.hp?0:1;return s;
}
export function decideBot(s:Match,i:0|1,difficulty:Difficulty,profile:OpponentProfile='standard'):Decision{
 const f=s.fighters[i],o=s.fighters[1-i],dx=o.x-f.x,d=Math.abs(dx),toward:Action=dx>0?2:1,away:Action=dx>0?1:2;
 const result=(action:Action,rule:string,reason:string):Decision=>({action,rule,reason,frame:s.frame});
 if(s.v===1)return result(legacy.policy(s as legacy.Match,i,difficulty),'v1-policy','Original v1 rules');
 if(!['standard','aggressive','defensive','counter-focused','mobile','mixed'].includes(profile))throw Error('Invalid opponent profile');
 const activeProfile=profile==='mixed'?(['aggressive','defensive','counter-focused','mobile'] as const)[Math.floor(s.frame/360+s.seed)%4]:profile;
 if(difficulty==='easy'&&(s.frame+(s.seed%11))%28>10&&activeProfile!=='aggressive')return result(0,'reaction-delay','Easy bot is waiting before reacting');
 if(f.stun)return result(4,'hit-recovery','Recovering from a hit');
 if(activeProfile==='mobile'&&f.y===0&&d<150&&!f.cooldown&&s.frame%150<26)return result(3,'profile-mobile-jump','Mobile profile changes lanes before committing');
 if(f.y>20&&!f.cooldown&&d<100)return result(11,'air-window','Airborne and close enough for an air strike');
 if(o.attack&&d<125){
  if((activeProfile==='counter-focused'||difficulty==='hard')&&!f.dodgeCooldown&&(MOVES[o.attack]?.damage??0)>14)return result(7,'dodge-heavy','A heavy attack is winding up nearby');
  return result(o.attack===9?8:4,'incoming-attack',o.attack===9?'A low attack is incoming: crouch guard':'An attack is incoming: block');
 }
 if(activeProfile==='defensive'&&d<116&&!f.cooldown&&s.frame%96<36)return result(o.attack===9?8:4,'profile-defensive-guard','Defensive profile probes by guarding in range');
 if(difficulty!=='easy'&&(f.combo??0)>=2&&!f.cooldown&&d<112)return result(13,'finish-combo','Two light hits connected: finish the chain');
 if(!f.cooldown&&o.block&&(difficulty==='hard'&&d<69||activeProfile==='aggressive'&&d<76))return result(12,'break-guard','Opponent holds guard within shove range');
 if(activeProfile==='aggressive'&&!f.cooldown&&d<112)return result(difficulty==='easy'?5:10,'profile-aggressive-attack','Aggressive profile attacks earlier in range');
 if(activeProfile==='counter-focused'&&o.cooldown>8&&!f.cooldown&&d<120)return result(10,'profile-counter-punish','Counter profile punishes recovery windows');
 if(!f.cooldown&&d<90){if(o.block&&!o.crouch&&difficulty!=='easy')return result(9,'attack-low','Standing guard leaves a low opening');return result(difficulty==='easy'&&s.frame%120<30?6:5,'attack-window','Opponent is in reach and recovery has finished');}
 const predicted=difficulty==='hard'?Math.abs(dx+o.vx*6):d;
 if(difficulty==='hard'&&predicted<135&&d>90&&!f.cooldown&&o.cooldown>15)return result(10,'punish-recovery','Opponent is recovering: advance into a punch');
 if((d<58&&f.cooldown>12)||activeProfile==='defensive'&&d<70)return result(away,'make-space','Attack is recovering: create room');
 if(o.y>45&&difficulty==='hard'&&f.y===0&&d<130)return result(3,'follow-air','Nearby opponent is airborne');
 return d>78?result(toward,'close-distance','Opponent is beyond attack reach'):result(0,'wait-opening','Hold position until an attack is ready');
}
export function policy(s:Match,i:0|1,d:Difficulty,p:OpponentProfile='standard'):Action{return decideBot(s,i,d,p).action;}
export function observation(s:Match,i:0|1):number[]{const f=s.fighters[i],o=s.fighters[1-i];return [(o.x-f.x)/1000,(o.y-f.y)/150,o.vx/10,o.vy/15,f.vx/10,f.vy/15,Math.abs(o.x-f.x)/1000,o.attack?1:0,o.block?1:0,f.hp/100,o.hp/100,(f.x-36)/928,(964-f.x)/928,f.damage,f.action/13,1-s.frame/s.limit,f.y===0?1:0,f.cooldown===0&&!f.stun&&!f.attack?1:0,(f.combo??0)/2,o.cooldown>10&&!o.attack?1:0].map(v=>Math.max(-1,Math.min(1,v)));}
export function roundReward(s:Match,i:0|1){const f=s.fighters[i],o=s.fighters[1-i],dealt=100-o.hp,received=100-f.hp;return dealt-1.1*received+(s.winner===i?40:0)-(s.winner===1-i?40:0)+1.5*f.blocks-.08*(f.idleTicks??0)/6+(1-Math.abs(f.x-500)/500)*Math.min(dealt/20,1);}
export function describeEvent(event:CombatEvent,viewer:0|1=1){const own=event.actor===viewer,move=ACTIONS[event.action].toLowerCase();if(event.type==='counter')return own?'Attack countered by a well-timed block':'Timed block succeeded';if(event.type==='miss')return `${own?'Own':'Opponent'} ${move} missed`;if(event.type==='blocked')return `${own?'Opponent blocked':'Blocked'} ${move} · ${event.damage} chip damage`;return `${own?'Landed':'Received'} ${move} · ${event.damage} damage`;}
export function hashState(s:Match):string{const str=JSON.stringify(s);let h=2166136261;for(let i=0;i<str.length;i++)h=Math.imul(h^str.charCodeAt(i),16777619);return(h>>>0).toString(16).padStart(8,'0');}
export function parseReplay(text:string):AnyReplay{
 if(new TextEncoder().encode(text).length>1_000_000)throw Error('Replay exceeds 1 MB');const r=JSON.parse(text);
 if(r?.v===1)return legacy.parseReplay(text);
 const keys=Object.keys(r??{}).sort().join(',');
 const expected=['v','engine','seed','scene','limit','actions','finalHash','controller','datasetHash','difficulty','checkpoint','checkpointHash','controlMode','sourceSegments'].sort().join(',');
 const expectedWithProfile=['v','engine','seed','scene','limit','actions','finalHash','controller','datasetHash','difficulty','checkpoint','checkpointHash','controlMode','sourceSegments','profile'].sort().join(',');
 if(!r||r.v!==2||r.engine!=='combat-v2'||(keys!==expected&&keys!==expectedWithProfile)||!Array.isArray(r.actions)||r.actions.length>MAX_FRAMES||r.actions.length>r.limit||!['easy','medium','hard'].includes(r.difficulty)||('profile'in r&&!['standard','aggressive','defensive','counter-focused','mobile','mixed'].includes(r.profile)))throw Error('Invalid replay schema/version');
 createMatch(r.seed,r.scene,r.limit);
 for(const key of ['controller','datasetHash','checkpoint','checkpointHash','controlMode'])if(typeof r[key]!=='string'||r[key].length>80)throw Error('Invalid replay metadata');
 if(typeof r.finalHash!=='string'||!/^[a-f0-9]{8}$/.test(r.finalHash)||!r.actions.every((a:unknown)=>Array.isArray(a)&&a.length===2&&a.every(isAction)))throw Error('Invalid replay actions/hash');
 if(!Array.isArray(r.sourceSegments)||r.sourceSegments.length>100||!r.sourceSegments.every((x:{frame:number;controller:string;checkpoint:string},i:number)=>x&&Object.keys(x).sort().join(',')==='checkpoint,controller,frame'&&Number.isInteger(x.frame)&&x.frame>=0&&x.frame<=r.actions.length&&(i===0||x.frame>=r.sourceSegments[i-1].frame)&&typeof x.controller==='string'&&x.controller.length<=80&&typeof x.checkpoint==='string'&&x.checkpoint.length<=80))throw Error('Invalid replay source segments');
 if(hashState(playReplay(r))!==r.finalHash)throw Error('Replay integrity mismatch');return r as Replay;
}
export function replayStart(r:AnyReplay):Match{return r.v===1?legacy.createMatch(r.seed,r.scene,r.limit):createMatch(r.seed,r.scene,r.limit);}
export function playReplay(r:AnyReplay):Match{if(r.v===1)return legacy.playReplay(r);const s=createMatch(r.seed,r.scene,r.limit);for(const a of r.actions){if(s.winner!==null)throw Error('Frames after end');step(s,a);}return s;}
