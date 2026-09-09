import {describe,it,expect} from 'vitest';
import {createMatch,step,policy,hashState,parseReplay,playReplay,observation,type Replay,type SceneName} from '../../packages/sim/core';
import type {Action} from '../../packages/protocol';
describe('shared deterministic combat',()=>{
 it('moves, jumps, lands, blocks and enforces walls',()=>{
  const s=createMatch(783,'boundary');step(s,[1,0]);expect(s.fighters[0].x).toBeGreaterThanOrEqual(36);step(s,[3,0]);expect(s.fighters[0].y).toBeGreaterThan(0);
  for(let i=0;i<45;i++)step(s,[0,0]);expect(s.fighters[0].y).toBe(0);
  step(s,[4,0]);expect(s.fighters[0].block).toBe(true);
 });
 it('resolves a light attack once and applies hit stun/cooldown',()=>{
  const s=createMatch(783,'close-combat');for(let i=0;i<8;i++)step(s,[5,0]);
  expect(s.fighters[1].hp).toBe(91);expect(s.fighters[1].stun).toBeGreaterThan(0);expect(s.fighters[0].cooldown).toBeGreaterThan(0);
  for(let i=0;i<10;i++)step(s,[5,0]);expect(s.fighters[1].hp).toBe(91);
 });
 it('blocking reduces damage; dodge gives invulnerability',()=>{
  const blocked=createMatch(1,'close-combat');for(let i=0;i<10;i++)step(blocked,[5,4]);expect(blocked.fighters[1].hp).toBe(99);expect(blocked.fighters[1].blocks).toBe(1);
  const dodged=createMatch(1,'close-combat');step(dodged,[5,7]);expect(dodged.fighters[1].invul).toBe(14);for(let i=0;i<10;i++)step(dodged,[0,0]);expect(dodged.fighters[1].hp).toBe(100);
 });
 it('trades simultaneous attacks and freezes a completed match',()=>{
  const s=createMatch(0,'close-combat',60);for(let i=0;i<8;i++)step(s,[5,5]);expect(s.fighters.map(f=>f.hp)).toEqual([91,91]);while(s.winner===null)step(s,[0,0]);const before=hashState(s);step(s,[6,6]);expect(hashState(s)).toBe(before);
 });
 it('replays concrete action logs exactly',()=>{
  const s=createMatch(783);const actions:[Action,Action][]=[];while(s.winner===null){const a:[Action,Action]=[policy(s,0,'hard'),policy(s,1,'medium')];actions.push(a);step(s,a);}
  const r:Replay={v:1,seed:783,scene:'standard',limit:2700,actions,finalHash:hashState(s),controller:'test',datasetHash:'fixture'};
  expect(hashState(playReplay(parseReplay(JSON.stringify(r))))).toBe(hashState(s));
  expect(()=>parseReplay(JSON.stringify({...r,v:2}))).toThrow();expect(()=>parseReplay(JSON.stringify({...r,finalHash:'00000000'}))).toThrow();expect(()=>parseReplay(JSON.stringify({...r,actions:[[99,0]]}))).toThrow();expect(()=>parseReplay(JSON.stringify({...r,path:'../x'}))).toThrow();
 });
 it('fuzzes bounded combat transitions and replay parsing (32 seeds × 600 frames)',()=>{
  for(let seed=0;seed<32;seed++){const s=createMatch(seed,['standard','close-combat','boundary','airborne'][seed%4] as SceneName);let rng=seed+1;const actions:[Action,Action][]=[];
   for(let i=0;i<600&&s.winner===null;i++){rng=(Math.imul(rng,1664525)+1013904223)>>>0;const a:[Action,Action]=[(rng%8) as Action,((rng>>>8)%8) as Action];actions.push(a);step(s,a);
    for(const f of s.fighters){expect(Number.isFinite(f.x+f.y+f.hp)).toBe(true);expect(f.hp).toBeGreaterThanOrEqual(0);expect(f.x).toBeGreaterThanOrEqual(36);expect(f.x).toBeLessThanOrEqual(964);}
    expect(observation(s,1).every(v=>Number.isFinite(v)&&v>=-1&&v<=1)).toBe(true);
   }
   const r:Replay={v:1,seed,scene:s.scene,limit:s.limit,actions,finalHash:hashState(s),controller:'fuzz',datasetHash:'fixture'};expect(hashState(playReplay(parseReplay(JSON.stringify(r))))).toBe(hashState(s));
  }
 });
 it('rejects pathological configurations, actions and replay bytes',()=>{
  for(const value of [NaN,Infinity,-1,4294967296,1.5])expect(()=>createMatch(value)).toThrow();
  expect(()=>step(createMatch(),[8 as Action,0])).toThrow();expect(()=>parseReplay('x'.repeat(1000001))).toThrow();
 });
});

