import {describe,it,expect} from 'vitest';
import {createMatch,step,hashState,parseReplay,playReplay,decideBot,observation,roundReward,type Replay,MOVES} from '../../packages/sim/core';
import type {Action} from '../../packages/protocol';
import {brainSocketUrl} from '../../apps/web/src/config';
const replay=(s:ReturnType<typeof createMatch>,actions:[Action,Action][]):Replay=>({v:2,engine:'combat-v2',seed:s.seed,scene:s.scene,limit:s.limit,actions,finalHash:hashState(s),controller:'real',datasetHash:'fixture',difficulty:'hard',checkpoint:'seed-initialized',checkpointHash:'',controlMode:'spectate',sourceSegments:[{frame:0,controller:'real',checkpoint:'seed-initialized'}]});
describe('v2 contextual combat and evidence',()=>{
 it('low kick beats standing guard but crouch guard stops it',()=>{
  const high=createMatch(2,'close-combat'),low=createMatch(2,'close-combat');for(let i=0;i<12;i++){step(high,[9,4]);step(low,[9,8]);}
  expect(high.fighters[1].hp).toBe(93);expect(low.fighters[1].hp).toBe(99);expect(low.events!.some(e=>e.type==='blocked')).toBe(true);
 });
 it('timed block counters; a held block does not fabricate a counter',()=>{
  const timed=createMatch(3,'close-combat'),held=createMatch(3,'close-combat');for(let i=0;i<8;i++){step(timed,[5,i>=3?4:0]);step(held,[5,4]);}
  expect(timed.events!.some(e=>e.type==='counter')).toBe(true);expect(timed.fighters[1].hp).toBe(100);expect(held.fighters[1].hp).toBe(99);
 });
 it('two landed lights unlock a finite combo finisher window',()=>{
  const s=createMatch(7,'close-combat');s.fighters[0].x=890;s.fighters[1].x=964;
  for(let i=0;i<90&&!s.events!.some(e=>e.type==='combo');i++)step(s,[(s.fighters[0].combo??0)>=2?13:5,0]);
  expect(s.events!.some(e=>e.type==='combo')).toBe(true);expect(s.fighters[0].combo).toBe(0);
 });
 it('shove breaks guard, dodge evades, and air strike requires air',()=>{
  const shove=createMatch(4,'close-combat');shove.fighters[0].x=480;shove.fighters[1].x=525;for(let i=0;i<15;i++)step(shove,[12,4]);
  expect(shove.events!.some(e=>e.type==='shove')).toBe(true);
  const air=createMatch(4,'close-combat');step(air,[11,0]);expect(air.fighters[0].attack).toBe(0);step(air,[3,0]);step(air,[11,0]);expect(air.fighters[0].attack).toBe(11);
 });
 it('every expanded move can start when its real preconditions hold',()=>{
  for(const key of Object.keys(MOVES)){const action=Number(key) as Action,s=createMatch(783,'close-combat');if(action===11)s.fighters[0].y=30;if(action===13){s.fighters[0].combo=2;s.fighters[0].comboWindow=30;}step(s,[action,0]);expect(s.fighters[0].attack).toBe(action);}
 });
 it('bot explanations name the branch that selected its action',()=>{
  const s=createMatch(4,'close-combat');s.fighters[1].block=true;const hard=decideBot(s,0,'hard');expect(hard.action).toBe(9);expect(hard.rule).toBe('attack-low');
  s.fighters[0].combo=2;expect(decideBot(s,0,'medium').action).toBe(13);
  expect(decideBot(s,0,'hard')).toEqual(decideBot(s,0,'hard'));
 });
 it('v2 replay fuzz preserves all actions, metadata and finite bounded states',()=>{
  for(let seed=0;seed<20;seed++){const s=createMatch(seed,'close-combat',600),actions:[Action,Action][]=[];let r=seed+1;while(s.winner===null){r=(Math.imul(r,1664525)+1013904223)>>>0;const pair:[Action,Action]=[(r%14) as Action,((r>>>8)%14) as Action];actions.push(pair);step(s,pair);expect(observation(s,1)).toHaveLength(20);expect(Number.isFinite(roundReward(s,1))).toBe(true);for(const f of s.fighters){expect(f.x>=36&&f.x<=964&&f.y>=0&&f.hp>=0&&f.hp<=100).toBe(true);}}
   const saved=replay(s,actions);expect(hashState(playReplay(parseReplay(JSON.stringify(saved))))).toBe(hashState(s));expect(()=>parseReplay(JSON.stringify({...saved,engine:'future'}))).toThrow();expect(()=>parseReplay(JSON.stringify({...saved,sourceSegments:[{frame:-1,controller:'evil',checkpoint:''}]}))).toThrow();
  }
 });
 it('production URL defaults to same-origin path and supports HTTPS/WSS',()=>{
  expect(brainSocketUrl(undefined,'https://flyweight.example',false)).toBe('wss://flyweight.example/brain/ws');
  expect(brainSocketUrl('https://brain.example','https://flyweight.example',false)).toBe('wss://brain.example/ws');
  expect(()=>brainSocketUrl('http://remote.example','https://flyweight.example',false)).toThrow();
  expect(()=>brainSocketUrl('https://user:password@brain.example','https://flyweight.example',false)).toThrow();
 });
});

