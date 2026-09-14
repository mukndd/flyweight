import {ACTIONS,type Action} from '../../../packages/protocol';
import type {Match} from '../../../packages/sim/core';

export type ActionMood='idle'|'move'|'jump'|'guard'|'attack'|'dodge'|'ko'|'victory'|'offline';

export interface PresentationState{
 mood:ActionMood;
 action:Action;
 actionLabel:string;
 intensity:number;
 button:number;
 flyHp:number;
 opponentHp:number;
 frame:number;
 online:boolean;
 champion:string;
 tagline:string;
}

export function actionMood(action:Action):ActionMood{
 if(action===1||action===2)return 'move';
 if(action===3||action===11)return 'jump';
 if(action===4||action===8)return 'guard';
 if(action===7)return 'dodge';
 if(action===5||action===6||action===9||action===10||action===12||action===13)return 'attack';
 return 'idle';
}

export function actionButton(action:Action){
 if(action===1||action===2)return 0;
 if(action===3||action===11)return 1;
 if(action===4||action===8)return 2;
 if(action===7)return 3;
 if(action===13)return 5;
 if(action===5||action===6||action===9||action===10||action===12)return 4;
 return -1;
}

export function presentationState(match:Match, online:boolean, champion:string, action:Action):PresentationState{
 const fly=match.fighters[1],opponent=match.fighters[0];
 const winner=match.winner;
 const mood:ActionMood=winner===1?'victory':winner===0?'ko':!online?'offline':actionMood(action);
 const recentHit=match.hits.some(hit=>match.frame-hit.frame<10);
 const intensity=Math.max(
  recentHit ? .8 : 0,
  mood==='attack' ? .72 : 0,
  mood==='dodge'||mood==='jump' ? .58 : 0,
  mood==='guard' ? .42 : 0,
  mood==='victory'||mood==='ko' ? .95 : 0,
  mood==='offline' ? .2 : .28,
 );
 return {
  mood,
  action,
  actionLabel:ACTIONS[action],
  intensity,
  button:actionButton(action),
  flyHp:fly.hp,
  opponentHp:opponent.hp,
  frame:match.frame,
  online,
  champion:champion||'seed-initialized',
  tagline:online?'A fly connectome is steering the purple fighter.':'Offline fallback: no neural activity is fabricated.',
 };
}
