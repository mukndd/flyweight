import readline from 'node:readline';
import {createMatch,step,observation,policy,hashState,roundReward,type Difficulty,type OpponentProfile} from './core.js';
import {isAction,type Action} from '../protocol/index.js';
let s=createMatch();let difficulty:Difficulty='medium';let profile:OpponentProfile='standard';let rounds=0;
const num=(v:unknown,min:number,max:number)=>typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max;
const maybeNum=(v:unknown,min:number,max:number)=>v===undefined||num(v,min,max);
const maybeBool=(v:unknown)=>v===undefined||typeof v==='boolean';
function applyFighter(target:0|1,value:unknown){
 if(value===undefined)return;
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error();
 const f=s.fighters[target],v=value as Record<string,unknown>;
 const allowed='attack,attackFrame,block,cooldown,face,hp,vx,vy,x,y'.split(',');
 if(!Object.keys(v).every(k=>allowed.includes(k)))throw Error();
 if(!maybeNum(v.x,36,964)||!maybeNum(v.y,0,160)||!maybeNum(v.vx,-12,12)||!maybeNum(v.vy,-20,20)||!maybeNum(v.hp,1,100)||!maybeNum(v.face,-1,1)||!maybeNum(v.cooldown,0,90)||!maybeNum(v.attack,0,13)||!maybeNum(v.attackFrame,0,60)||!maybeBool(v.block))throw Error();
 if(v.x!==undefined)f.x=v.x as number;if(v.y!==undefined)f.y=v.y as number;if(v.vx!==undefined)f.vx=v.vx as number;if(v.vy!==undefined)f.vy=v.vy as number;
 if(v.hp!==undefined)f.hp=v.hp as number;if(v.face!==undefined)f.face=v.face as number;if(v.cooldown!==undefined)f.cooldown=v.cooldown as number;
 if(v.attack!==undefined){if(!isAction(v.attack))throw Error();f.attack=v.attack;f.hasHit=false;}
 if(v.attackFrame!==undefined)f.attackFrame=v.attackFrame as number;if(v.block!==undefined)f.block=v.block as boolean;
}
function applyScenario(value:unknown){
 if(value===undefined)return;
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error();
 const v=value as Record<string,unknown>;
 if(Object.keys(v).sort().join(',')!=='id,opponent,player')throw Error();
 if(typeof v.id!=='string'||!/^[a-z0-9_]{1,40}$/.test(v.id))throw Error();
 applyFighter(0,v.opponent);applyFighter(1,v.player);
}
const rl=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
for await(const line of rl){
 if(line.length>8192)process.exit(1);
 try{
  const m=JSON.parse(line);
  const keys=Object.keys(m).sort().join(',');
  if(m.type==='reset'&&(keys==='difficulty,limit,seed,type'||keys==='difficulty,limit,profile,seed,type'||keys==='difficulty,limit,profile,scenario,seed,type')&&['easy','medium','hard'].includes(m.difficulty)&&(!('profile'in m)||['standard','aggressive','defensive','counter-focused','mobile','mixed'].includes(m.profile))){
   if(++rounds>1000)throw Error();s=createMatch(m.seed,'standard',m.limit);difficulty=m.difficulty;profile=m.profile??'standard';
   applyScenario(m.scenario);
  }else if(m.type==='step'&&Object.keys(m).sort().join(',')==='action,type'&&isAction(m.action)){
   for(let k=0;k<6&&s.winner===null;k++)step(s,[policy(s,0,difficulty,profile),m.action as Action]);
  }else throw Error();
  process.stdout.write(JSON.stringify({observation:observation(s,1),state:s,hash:hashState(s),rewards:[roundReward(s,0),roundReward(s,1)],difficulty,profile})+'\n');
 }catch{process.stdout.write('{"error":"Invalid bridge request"}\n');process.exit(1);}
}

