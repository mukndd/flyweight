import {describe,expect,test} from 'vitest';
import {createMatch,step} from '../../packages/sim/core';
import {actionButton,actionMood,presentationState} from '../../apps/web/src/presentation';

describe('presentation state mapping',()=>{
 test('maps actions to deterministic fly and controller moods',()=>{
  expect(actionMood(0)).toBe('idle');
  expect(actionMood(2)).toBe('move');
  expect(actionMood(4)).toBe('guard');
  expect(actionMood(6)).toBe('attack');
  expect(actionButton(13)).toBe(5);
 });

 test('derives presentation from match state without mutating simulation',()=>{
  const match=createMatch(12,'close-combat',180);
  const before=JSON.stringify(match);
  step(match,[0,5]);
  const state=presentationState(match,true,'candidate_demo',5);
  expect(JSON.stringify(match)).not.toBe(before);
  expect(state.mood).toBe('attack');
  expect(state.champion).toBe('candidate_demo');
  expect(state.tagline).toContain('connectome');
 });

 test('labels offline state without fake neural activity',()=>{
  const match=createMatch(12);
  const state=presentationState(match,false,'',0);
  expect(state.mood).toBe('offline');
  expect(state.tagline).toContain('no neural activity is fabricated');
 });
});
