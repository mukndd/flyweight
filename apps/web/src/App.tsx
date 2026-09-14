import {useEffect,useState} from 'react';
import {ACTIONS} from '../../../packages/protocol';
import {describeEvent,observation,roundReward,type CombatEvent} from '../../../packages/sim/core';
import {Arena} from './Arena';
import {Brain} from './Brain';
import {Controls} from './Controls';
import {Engine,type Mode} from './engine';
import {Lab} from './Lab';
import {Presentation3D} from './Presentation3D';

type PublicRoute='spectate'|'human'|'research';

const routeLabels:Record<PublicRoute,string>={spectate:'WATCH',human:'FIGHT',research:'SCIENCE'};
const palette=['ember','graphite','oxide','steel'];

function publicFlyId(engine:Engine){
 const day=engine.research?.today?.day;
 const count=engine.research?.counts?.candidates;
 const n=typeof day==='number'&&day>0?day:typeof count==='number'&&count>0?count:0;
 return `FW-${String(n).padStart(3,'0')}`;
}

function pct(value?:number){
 return value===undefined?'--':`${Math.round(value*100)}%`;
}

function clock(frame:number){
 const seconds=Math.max(0,Math.floor(frame/60));
 return `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
}

function publicAchievement(engine:Engine){
 const cert=engine.research?.certified_level;
 const today=engine.research?.today;
 if(cert)return `Level ${cert.level} certified at ${pct(cert.win_rate)} over ${cert.matches} matches`;
 if(today&&today.promotions>0)return `${today.promotions} promotion${today.promotions===1?'':'s'} recorded today`;
 if(today&&today.candidates_evaluated>0)return `${today.candidates_evaluated} candidates evaluated today`;
 return 'No certified ladder level yet';
}

function eventLabel(event:CombatEvent){
 const actor=event.actor===1?'Fly':'Opponent';
 if(event.type==='blocked')return `${actor} blocked ${ACTIONS[event.action].toLowerCase()}`;
 if(event.type==='miss')return `${actor} whiffed ${ACTIONS[event.action].toLowerCase()}`;
 if(event.type==='counter')return `${actor} countered`;
 if(event.type==='combo')return `${actor} landed combo`;
 if(event.type==='shove')return `${actor} broke guard`;
 return `${actor} landed ${event.damage} damage`;
}

function latestResult(engine:Engine){
 const event=(engine.state.events??[]).filter(e=>e.actor===1||e.target===1).at(-1);
 return event?describeEvent(event,1):'No exchange yet';
}

export function App(){
 const [engine]=useState(()=>new Engine());
 const [,refresh]=useState(0);
 const [controls,setControls]=useState(false);
 const [challengeState,setChallengeState]=useState<'setup'|'fight'|'result'>('setup');
 const [challenger,setChallenger]=useState('');
 const [appearance,setAppearance]=useState(palette[0]);
 const internal=new URLSearchParams(location.search).get('internal')==='1'&&import.meta.env.DEV;

 useEffect(()=>{
  engine.connect();
  const timer=setInterval(()=>refresh(v=>v+1),100);
  if(import.meta.env.DEV)window.__FLYWEIGHT__={snapshot:()=>engine.snapshot(),scene:(name,seed=783,seconds=45)=>{engine.mode='spectate';engine.reset(seed,name,seconds*60);},pause:p=>{engine.paused=p;},exportReplay:()=>engine.exportReplay(),loadReplay:text=>engine.loadReplay(text),step:frames=>{if(Number.isInteger(frames)&&frames>0&&frames<=5400)for(let i=0;i<frames;i++)engine.advance();},engine};
  return()=>{clearInterval(timer);engine.destroy();delete window.__FLYWEIGHT__;};
 },[engine]);

 useEffect(()=>{
  if(engine.mode==='human'&&engine.state.winner!==null)setChallengeState('result');
 },[engine.mode,engine.state.winner,engine.state.frame]);

 const route=(engine.mode==='human'||engine.mode==='research'||engine.mode==='spectate'?engine.mode:'spectate') as PublicRoute;
 const flyId=publicFlyId(engine);
 const certified=engine.research?.certified_level?.level??0;
 const status=engine.online?'Online':engine.startingUp?'Starting':'Offline';
 const researchState=engine.research?.worker_status?.state??engine.research?.training_status??'idle';

 const go=(next:PublicRoute)=>{
  engine.setMode(next as Mode);
  if(next==='human'){setChallengeState('setup');engine.paused=true;engine.matchStarted=false;}
 };

 const startChallenge=()=>{
  engine.setMode('human');
  engine.reset(902+engine.publicLevel*31,'standard',2700);
  setChallengeState('fight');
 };

 return <div className="public-shell"><header className="public-header"><button className="brand-lockup" onClick={()=>go('spectate')}><span>flyweight</span></button><nav aria-label="Public navigation">{(Object.keys(routeLabels) as PublicRoute[]).map(id=><button key={id} aria-pressed={route===id} onClick={()=>go(id)}>{routeLabels[id]}</button>)}</nav><div className="header-status"><i className={engine.online?'online':engine.startingUp?'starting':''}/><span>{status}</span></div></header>
  <main>
   {!engine.online&&!engine.startingUp&&<div className="public-warning" role="status"><b>Fly Brain offline.</b> Demo control is active; no neural activity is fabricated.</div>}
   {engine.online&&engine.graph?.synthetic&&<div className="public-warning" role="status"><b>Synthetic fixture.</b> This service is not using FlyWire data.</div>}
   {internal&&engine.mode==='lab'?<InternalLab engine={engine}/>:route==='research'?<SciencePage engine={engine} flyId={flyId}/>:route==='human'?<HumanChallenge engine={engine} flyId={flyId} certified={certified} challenger={challenger} setChallenger={setChallenger} appearance={appearance} setAppearance={setAppearance} state={challengeState} setState={setChallengeState} startChallenge={startChallenge} openControls={()=>setControls(true)}/>:<WatchExperience engine={engine} flyId={flyId} certified={certified} researchState={researchState} openFight={()=>go('human')}/>}
  </main>
  <footer className="public-footer"><span>Real FlyWire connectivity; artificial game inputs and outputs.</span><button onClick={()=>go('research')}>How it works</button>{internal&&<button onClick={()=>engine.setMode('lab')}>Internal Lab</button>}</footer>
  {controls&&<Controls engine={engine} onClose={()=>setControls(false)}/>}
 </div>;
}

function WatchExperience({engine,flyId,certified,researchState,openFight}:{engine:Engine;flyId:string;certified:number;researchState:string;openFight:()=>void}){
 return <section className="watch-page" aria-label="Live experiment watch view"><div className="watch-copy"><div><p className="kicker">CURRENT EXHIBITION</p><h1>FLYWEIGHT</h1><p>A fruit-fly connectome controlling a fighter.</p></div><button className="primary-action" onClick={openFight}>FIGHT THE FLY</button></div>
  <ExperimentScene engine={engine} flyId={flyId} certified={certified} context="watch"/>
  <div className="watch-bottom"><LevelPicker engine={engine} certified={certified}/><div className="progress-line"><span>{flyId}</span><span>Certified Level {certified||'--'}</span><span>{publicAchievement(engine)}</span><span>Research {researchState}</span></div></div>
 </section>;
}

function ExperimentScene({engine,flyId,certified,context}:{engine:Engine;flyId:string;certified:number;context:'watch'|'fight'}){
 const done=engine.state.winner!==null;
 return <section className="experiment-scene"><div className="scene-stage"><div className="scene-topline"><span>{flyId} vs Level {engine.publicLevel}</span><span>{engine.paused?'Paused':done?'Round complete':'Live simulation'}</span></div><Arena engine={engine}/><div className="minimal-hud"><Health label={context==='fight'?'You':'Opponent'} value={engine.state.fighters[0].hp} side="opponent"/><div className="round-clock">{String(Math.max(0,Math.ceil((engine.state.limit-engine.state.frame)/60))).padStart(2,'0')}</div><Health label={flyId} value={engine.state.fighters[1].hp} side="fly"/></div><div className="fly-station"><Presentation3D engine={engine} variant="match"/></div><div className="stage-actions"><button onClick={()=>{engine.paused=!engine.paused;engine.matchStarted=true;}}>{engine.paused?'Resume':'Pause'}</button><button onClick={()=>engine.reset()}>Restart</button></div></div>
  <aside className="scene-instrument"><div className="instrument-head"><div><span>CONNECTOME ACTIVITY MAP</span><b>{engine.online&&engine.isNeural?'Runtime values':'Inactive'}</b></div><small>{engine.graph?.ids.length??0} displayed nodes</small></div><Brain engine={engine}/><Inspector engine={engine}/><EventStream engine={engine}/><div className="cert-line"><span>Certified</span><b>{certified?`Level ${certified}`:'Not yet'}</b></div></aside></section>;
}

function Health({label,value,side}:{label:string;value:number;side:'fly'|'opponent'}){
 return <div className={`health ${side}`}><span>{label}</span><i><b style={{width:`${value}%`}}/></i></div>;
}

function LevelPicker({engine,certified}:{engine:Engine;certified:number}){
 return <div className="level-picker" aria-label="Opponent level"><span>Opponent</span>{Array.from({length:10},(_,i)=>i+1).map(level=><button key={level} aria-pressed={engine.publicLevel===level} className={level<=certified?'certified':''} onClick={()=>engine.setPublicLevel(level)} title={level<=certified?'Certified level':'Uncertified or current target'}>{level}</button>)}</div>;
}

function EventStream({engine}:{engine:Engine}){
 const events=(engine.state.events??[]).slice(-7);
 const rows=events.length?events.map(e=>({time:clock(e.frame),label:eventLabel(e)})):[{time:clock(engine.state.frame),label:`Selected ${ACTIONS[engine.state.fighters[1].action].toLowerCase()}`}];
 return <section className="event-stream"><div className="small-heading">Match events</div>{rows.map((row,index)=><p key={`${row.time}-${index}`}><time>{row.time}</time><span>{row.label}</span></p>)}</section>;
}

function Inspector({engine}:{engine:Engine}){
 const obs=engine.inputs.length?engine.inputs:observation(engine.state,1);
 const sees=[obs[6]<.13?'opponent close':'opponent at range',obs[7]?'opponent attacking':obs[8]?'opponent blocking':'opponent open',obs[12]<.16?'near right boundary':obs[11]<.16?'near left boundary':'room to move'];
 return <section className="sees-panel"><div><span>SEES</span><b>{sees.join(' / ')}</b></div><div><span>ACTION</span><b>{ACTIONS[engine.state.fighters[1].action]}</b></div><div><span>RESULT</span><b>{latestResult(engine)}</b></div></section>;
}

function HumanChallenge({engine,flyId,certified,challenger,setChallenger,appearance,setAppearance,state,setState,startChallenge,openControls}:{engine:Engine;flyId:string;certified:number;challenger:string;setChallenger:(value:string)=>void;appearance:string;setAppearance:(value:string)=>void;state:'setup'|'fight'|'result';setState:(value:'setup'|'fight'|'result')=>void;startChallenge:()=>void;openControls:()=>void}){
 if(state==='setup')return <section className="challenge-setup"><div className="challenge-copy"><p className="kicker">HUMAN CHALLENGE</p><h1>Fight the Fly</h1><p>Current Fly {flyId}. Certified Level {certified||'--'}. No account required.</p></div><div className="setup-form"><label>Name<input value={challenger} maxLength={24} onChange={e=>setChallenger(e.target.value)} placeholder="Optional"/></label><div><span>Appearance</span><div className="swatches">{palette.map(color=><button key={color} className={color} aria-pressed={appearance===color} onClick={()=>setAppearance(color)}>{color}</button>)}</div></div><button className="primary-action" onClick={startChallenge}>START FIGHT</button></div></section>;
 if(state==='result')return <ResultView engine={engine} flyId={flyId} challenger={challenger} startAgain={()=>{setState('fight');startChallenge();}}/>;
 return <section className={`fight-page fighter-${appearance}`}><div className="fight-head"><div><p className="kicker">HUMAN VS FLY</p><h1>{challenger.trim()||'You'} vs {flyId}</h1></div><button onClick={openControls}>Controls</button></div><ExperimentScene engine={engine} flyId={flyId} certified={certified} context="fight"/></section>;
}

function ResultView({engine,flyId,challenger,startAgain}:{engine:Engine;flyId:string;challenger:string;startAgain:()=>void}){
 const winner=engine.state.winner;
 const humanWon=winner===0;
 const dealt=100-engine.state.fighters[1].hp;
 const taken=100-engine.state.fighters[0].hp;
 return <section className="result-view"><p className="kicker">MATCH RESULT</p><h1>{humanWon?'WIN':'LOSS'}</h1><div className="result-metrics"><span>{challenger.trim()||'Human'}</span><span>{flyId}</span><span>{Math.round(engine.state.frame/60)}s</span><span>{Math.round(dealt)} dealt / {Math.round(taken)} taken</span><span>Round score {roundReward(engine.state,0).toFixed(1)}</span></div><button className="primary-action" onClick={startAgain}>FIGHT AGAIN</button><button className="secondary-action" onClick={()=>navigator.clipboard?.writeText(`Flyweight result: ${humanWon?'win':'loss'} vs ${flyId}, ${Math.round(dealt)} damage dealt.`)}>SHARE RESULT</button></section>;
}

function SciencePage({engine,flyId}:{engine:Engine;flyId:string}){
 const overview=engine.research,cert=overview?.certified_level,ladder=engine.ladder?.levels??[],comparison=engine.topologyStatus?.comparisons??[];
 return <section className="science-page"><div className="science-hero"><p className="kicker">SCIENCE</p><h1>What is actually running?</h1><p>The biological topology is fixed. Game sensors and motor readouts are artificial. Normal matches do not update weights.</p><button onClick={()=>void engine.fetchResearch()}>Refresh</button></div><div className="science-grid"><section><h2>{flyId}</h2><p>Public champion alias. Raw checkpoint identifiers stay here, not in the broadcast HUD.</p><dl><dt>Raw checkpoint</dt><dd>{engine.research?.current_champion?.checkpoint_id??engine.checkpoint}</dd><dt>Checkpoint hash</dt><dd>{engine.checkpointHash||'unavailable'}</dd><dt>Dataset hash</dt><dd>{engine.datasetHash}</dd></dl></section><section><h2>Ladder</h2><p>{cert?`Certified through Level ${cert.level}.`:'No level certification recorded yet.'}</p><div className="science-ladder">{Array.from({length:10},(_,i)=>i+1).map(level=><span key={level} className={cert&&level<=cert.level?'cleared':''}>{level}</span>)}</div><details><summary>Level manifest</summary>{ladder.map(level=><p key={level.version}>Level {level.index}: {level.difficulty}, {level.profile}, {level.min_matches} matches</p>)}</details></section><section><h2>Controller Boundary</h2><p>FlyWire connectivity and initial strengths stay fixed. CEM trains only artificial sensory/readout adapters in isolated candidates.</p><p>Current browser matches are observations of a checkpoint, not online learning.</p></section><section><h2>Activity View</h2><p>No reliable anatomical coordinates are exposed to the web client. The public brain panel is a deterministic graph layout, driven by live controller activations.</p><p>Node intensity maps to absolute activation; edge brightness is capped for display performance.</p></section></div><details className="deep-methods"><summary>Research history and controls</summary><div className="method-grid"><section><h3>Today</h3><p>{overview?.today?`${overview.today.matches_simulated} matches, ${overview.today.candidates_evaluated} candidates, ${overview.today.promotions} promotions.`:'Research registry unavailable.'}</p></section><section><h3>Topology Comparisons</h3>{comparison.length?comparison.slice(0,8).map(row=><p key={row.id}>{row.metrics.condition??row.suite}: {pct(row.metrics.win_rate)} win rate</p>):<p>First comparison batch running or unavailable.</p>}</section><section><h3>Human Results</h3>{engine.humanMatches?.matches?.length?engine.humanMatches.matches.slice(0,5).map(match=><p key={match.id}>{match.result.result.replace('_',' ')}: {Math.round(match.result.damage_dealt)} dealt</p>):<p>No challengers yet. Be the first.</p>}</section></div></details></section>;
}

function InternalLab({engine}:{engine:Engine}){
 return <section className="internal-lab"><h1>Internal Lab</h1><p>Development-only adapter training controls. This is hidden from public navigation.</p><Lab engine={engine}/></section>;
}
