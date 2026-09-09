import readline from 'node:readline';
import {createMatch,step,observation,policy,hashState,roundReward,type Difficulty} from './core.js';
import {isAction,type Action} from '../protocol/index.js';
let s=createMatch();let difficulty:Difficulty='medium';let rounds=0;
const rl=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
for await(const line of rl){
 if(line.length>4096)process.exit(1);
 try{
  const m=JSON.parse(line);
  if(m.type==='reset'&&Object.keys(m).sort().join(',')==='difficulty,limit,seed,type'&&['easy','medium','hard'].includes(m.difficulty)){
   if(++rounds>1000)throw Error();s=createMatch(m.seed,'standard',m.limit);difficulty=m.difficulty;
  }else if(m.type==='step'&&Object.keys(m).sort().join(',')==='action,type'&&isAction(m.action)){
   for(let k=0;k<6&&s.winner===null;k++)step(s,[policy(s,0,difficulty),m.action as Action]);
  }else throw Error();
  process.stdout.write(JSON.stringify({observation:observation(s,1),state:s,hash:hashState(s),rewards:[roundReward(s,0),roundReward(s,1)]})+'\n');
 }catch{process.stdout.write('{"error":"Invalid bridge request"}\n');process.exit(1);}
}

