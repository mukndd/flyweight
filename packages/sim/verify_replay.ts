import readline from 'node:readline';
import {parseReplay,playReplay,hashState} from './core.js';

const rl=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
let bytes=0;
for await(const line of rl){
 bytes+=Buffer.byteLength(line,'utf8');
 if(bytes>1_000_000)process.exit(1);
 try{
  const replay=parseReplay(line);
  const final=playReplay(replay);
  process.stdout.write(JSON.stringify({
   ok:true,
   finalHash:hashState(final),
   winner:final.winner,
   duration:final.frame/60,
   damage:[100-final.fighters[1].hp,100-final.fighters[0].hp],
   seed:replay.seed,
   checkpointHash:replay.v===2?replay.checkpointHash:'',
  })+'\n');
 }catch{
  process.stdout.write('{"ok":false}\n');
  process.exit(1);
 }
}
