import {useEffect,useRef,useState} from 'react';
import {Arena} from './Arena';
import {Controls} from './Controls';
import {DecisionPanels} from './DecisionPanels';
import {Overview,Leaderboard} from './Overview';
import {Presentation3D} from './Presentation3D';
import {Research,ResearchDashboard} from './Research';
import {Lab} from './Lab';
import {Engine,type Mode} from './engine';
import {ACTIONS} from '../../../packages/protocol';
import type {Difficulty} from '../../../packages/sim/core';

const modes:{id:Mode;label:string;hint:string}[]=[
 {id:'overview',label:'Overview',hint:'Neuroscience Fight Night home'},
 {id:'human',label:'Play',hint:'Fight the Fly Brain yourself'},
 {id:'spectate',label:'Watch',hint:'Watch the Bot fight the Fly Brain'},
 {id:'research',label:'Research',hint:'Review champion lineage and benchmarks'},
 {id:'lab',label:'Lab',hint:'Train artificial adapters'},
 {id:'leaderboard',label:'Leaderboard',hint:'Verified human exhibition results'},
 {id:'replay',label:'Replays',hint:'Review saved matches'},
];

export function App(){
 const [engine]=useState(()=>new Engine());
 const[,refresh]=useState(0);
 const[layout,setLayout]=useState('split');
 const[controls,setControls]=useState(false);
 const file=useRef<HTMLInputElement>(null);
 useEffect(()=>{
  engine.connect();
  const timer=setInterval(()=>refresh(v=>v+1),100);
  if(import.meta.env.DEV)window.__FLYWEIGHT__={snapshot:()=>engine.snapshot(),scene:(name,seed=783,seconds=45)=>{engine.mode='spectate';engine.reset(seed,name,seconds*60);},pause:p=>{engine.paused=p;},exportReplay:()=>engine.exportReplay(),loadReplay:text=>engine.loadReplay(text),step:frames=>{if(Number.isInteger(frames)&&frames>0&&frames<=5400)for(let i=0;i<frames;i++)engine.advance();},engine};
  return()=>{clearInterval(timer);engine.destroy();delete window.__FLYWEIGHT__;};
 },[engine]);
 const s=engine.state,mode=engine.mode,g=engine.graph,online=engine.online,done=s.winner!==null;
 const training=engine.training?.status==='training';
 const brainStatus=training?`Fly Brain training... generation ${engine.training?.generation}/${engine.training?.generations}`
  :online?`Fly Brain engine online - ${g?`${g.neurons.toLocaleString()} neurons · ${g.edge_count.toLocaleString()} connections`:''}`
  :engine.startingUp?'Starting Fly Brain... connecting'
  :'Fly Brain offline · demo bot active';
 const save=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(engine.exportReplay())],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`flyweight-seed-${s.seed}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 const load=async(f?:File)=>{if(!f)return;try{if(f.size>1000000)throw Error('Replay must be under 1 MB');engine.loadReplay(await f.text());}catch(e){engine.error=e instanceof Error?e.message:'Invalid replay';}};
 const restart=()=>{if(mode==='replay'&&engine.replay){engine.seek(0);engine.paused=false;}else engine.reset();};
 const matchTitle=mode==='lab'?'TRAIN THE ADAPTERS':mode==='replay'?'REPLAY VIEWER':mode==='human'?'HUMAN CHALLENGE':'LIVE EXHIBITION';
 return <div className="app-shell"><header className="masthead"><a className="wordmark" href="/"><span className="brand-icon" aria-hidden="true">f<span>•</span></span>flyweight<span className="version">EXPERIMENT 002</span></a><div className="header-right"><span className={`local-dot${online?' online':''}${engine.startingUp&&!online?' starting':''}`}/><span>{brainStatus}</span><a href="#about" className="about-link">About the experiment ↗</a></div></header><main>
 <div className="workspace-nav"><nav aria-label="Game mode">{modes.map(m=><button key={m.id} title={m.hint} aria-pressed={mode===m.id} onClick={()=>engine.setMode(m.id)} className={mode===m.id?'active':''}>{m.label}</button>)}</nav><div className="workspace-tools"><button className="controls-open" onClick={()=>setControls(true)}>⌨ Controls</button><div className="layout-control">{[['arena','Arena only'],['split','Fight and decisions'],['brain','Decision focus']].map(([id,label])=><button key={id} aria-label={label} title={label} aria-pressed={layout===id} className={layout===id?'selected':''} onClick={()=>setLayout(id)}>{id==='arena'?'▰':id==='split'?'◫':'⌘'}</button>)}</div></div></div>
 {!online&&engine.startingUp&&<div className="notice" role="status">Starting Fly Brain - loading the connectome. The demo bot is available meanwhile.</div>}
 {!online&&!engine.startingUp&&<div className="warning" role="status"><strong>Fly Brain offline.</strong> Using the demo bot instead. <details><summary>Technical details</summary><p>The Fly Brain engine is unavailable or reconnecting. No neural signals are fabricated. Reconnection is automatic; changes in controller source are recorded in replays.</p></details></div>}
 {online&&g?.synthetic&&<div className="warning" role="status"><strong>Synthetic wiring.</strong> The engine is online, but this fixture does not use FlyWire data or neuron IDs.</div>}
 {online&&!engine.isNeural&&<div className="comparison-notice">Research control active: a conventional baseline runs the purple fighter. No neurons are active.</div>}
 {online&&engine.isNeural&&engine.topology!=='real'&&<div className="comparison-notice">Research comparison: {engine.topology.replaceAll('_',' ')}. This is not the original biological wiring.</div>}
 <div className="mobile-warning">Play requires a keyboard. You can Watch, use Lab and review Replays on this screen.</div>
 {mode==='overview'?<Overview engine={engine}/>:mode==='research'?<ResearchDashboard engine={engine}/>:mode==='leaderboard'?<Leaderboard engine={engine}/>:<>
  {mode!=='lab'&&mode!=='replay'&&<div className="match-setup"><div className="match-pair"><span className="identity bot">◆ {mode==='human'?'YOU':'BOT'}</span><span>vs</span><span className="identity fly">✳ {engine.rightName}</span></div><label>Bot difficulty<select aria-label="Bot difficulty" value={engine.difficulty} disabled={mode==='human'} onChange={e=>{engine.difficulty=e.target.value as Difficulty;engine.reset();}}>{['easy','medium','hard'].map(d=><option key={d} value={d}>{d[0].toUpperCase()+d.slice(1)}</option>)}</select></label><label>Fly Brain mode<select aria-label="Fly Brain mode" value={engine.requestedCheckpoint} disabled={!online||!engine.isNeural} onFocus={()=>engine.send({v:2,type:'checkpoint_list'})} onChange={e=>engine.selectCheckpoint(e.target.value)}><option value="">Not trained yet</option>{engine.checkpoints.map(c=><option key={c.id} value={c.id}>Trained candidate · {c.id.slice(-6)}</option>)}</select></label><p>Fly wiring: <b>fixed</b><br/>Adapters: <b>{engine.requestedCheckpoint?'trained snapshot':'trainable in Lab'}</b></p></div>}
  <section className={`experiment-grid layout-${layout} mode-${mode}`}><div className="arena-panel"><div className="panel-top"><span className="panel-label">{matchTitle}</span><span className="arena-status"><i className={!engine.paused&&!done?'lit':''}/>{mode==='lab'?'EXPERIMENT':engine.paused?'PAUSED':done?'ROUND COMPLETE':'ROUND 1'}</span></div>
  {mode==='lab'?<Lab engine={engine}/>:<><Presentation3D engine={engine} variant="match"/><div className="match-hud">{[0,1].map(i=><div key={i} className={i?'fighter-hud brain-fighter':'fighter-hud'}><div><strong>{i?'✳ '+engine.rightName:'◆ '+(mode==='human'?'YOU':'BOT')}</strong><small>{i?online&&engine.isNeural?'Connectome controller':'Conventional controller':mode==='human'?'Keyboard input':'Rule-based opponent'}</small></div><div className="health-track"><span style={{width:`${s.fighters[i].hp}%`}}/></div><span className="health-number">{s.fighters[i].hp}<small> / 100</small></span></div>)}<div className="timer"><strong>{String(Math.max(0,Math.ceil((s.limit-s.frame)/60))).padStart(2,'0')}</strong><small>SECONDS</small></div></div>
  <div className="stage"><Arena engine={engine}/><div className="stage-caption"><span>◆ {mode==='human'?'YOU':'BOT'} · LEFT</span><span>✳ {engine.rightName} · RIGHT</span></div>{(engine.paused||done||!engine.matchStarted)&&<div className="pause-card"><span className="eyebrow">{done?'ROUND COMPLETE':engine.matchStarted?'PAUSED':'READY WHEN YOU ARE'}</span>{done&&<h2>{s.winner===2?'Draw.':s.winner===1?`${engine.rightName} wins.`:`${mode==='human'?'You':'Bot'} wins.`}</h2>}{done&&<div className="result-card"><span>Dealt<b>{100-s.fighters[1].hp}</b></span><span>Taken<b>{100-s.fighters[0].hp}</b></span><span>Time<b>{Math.round(s.frame/60)}s</b></span><span>Champion<b>{engine.checkpoint.slice(-6)}</b></span></div>}<button className="primary" onClick={()=>{if(done)restart();else{engine.paused=false;engine.matchStarted=true;}}}>{done?'Play again ↗':engine.matchStarted?'Resume':'Start match'}</button><div className="pause-links"><button onClick={restart}>Restart</button><button onClick={save}>Save replay</button><button onClick={()=>{engine.matchStarted=false;engine.paused=false;engine.keys.clear();}}>Exit match</button></div></div>}</div>
  <div className="action-pair"><span><b>{mode==='human'?'YOU':'BOT'}</b> {ACTIONS[s.fighters[0].action]}</span><span><b>{engine.rightName}</b> {ACTIONS[s.fighters[1].action]}</span></div>
  <div className="arena-bottom"><span className="mono">SEED {s.seed} <span className="divider">/</span> FRAME {s.frame}</span><div><button aria-label={engine.paused?'Resume':'Pause'} onClick={()=>{engine.paused=!engine.paused;}}>{engine.paused?'▶ Resume':'Ⅱ Pause'}</button><button onClick={restart}>↺ Restart</button><button onClick={save}>↓ Save replay</button></div></div>
  {mode==='replay'?<div className="match-settings"><div className="replay-controls"><button onClick={()=>file.current?.click()}>↑ Open replay</button><input ref={file} type="file" accept=".json,application/json" hidden onChange={e=>{void load(e.target.files?.[0]);e.target.value='';}}/><button disabled={!engine.lastReplay} onClick={()=>{if(engine.lastReplay)engine.loadReplay(JSON.stringify(engine.lastReplay));}}>Watch last match</button></div>{engine.replay&&<label className="seek-label">Frame {engine.replayCursor} / {engine.replay.actions.length}<input aria-label="Replay frame" type="range" min="0" max={engine.replay.actions.length} value={engine.replayCursor} onChange={e=>engine.seek(Number(e.target.value))}/></label>}<small>Verified action log · version {engine.replay?.v??'—'} · brain activity was not recorded</small></div>:<div className="match-tip">Try <kbd>C + J</kbd> for a low kick. Two connected light punches open a heavy combo finisher. <button onClick={()=>setControls(true)}>All controls ↗</button></div>}</>}
  </div><DecisionPanels engine={engine}/></section></>}
 {engine.error&&<div className="error" role="alert">{engine.error}<button onClick={()=>{engine.error='';}}>Dismiss</button></div>}
 {mode!=='overview'&&<div className="data-strip"><span className="data-tag">{!online?'DEMO BOT':g?.synthetic?'SYNTHETIC FIXTURE':engine.topology==='real'?'REAL FLYWIRE DATA':'RESEARCH CONTROL'}</span><p>{!online?'Fly Brain is offline. The purple fighter is a conventional demo bot.':engine.topology==='real'&&!g?.synthetic?'The connections come from a real fly. The sensory adapter, motor readout and fighting game are artificial.':'This is a labelled comparison configuration. Inspect its exact structure in Research details.'}</p><span className="no-learning">No learning during matches</span></div>}
 {mode!=='overview'&&<Research engine={engine}/>}
 <footer id="about"><div><a className="wordmark" href="/">flyweight<span className="footer-star">✳</span></a><p>An experiment, not an organism.</p></div><p>Not a conscious fly or a full-brain simulation.<br/>Artificial adapters can train; biological wiring stays fixed.<br/>A round is an observation, not scientific proof.</p><div className="footer-links"><a href="https://www.nature.com/articles/s41586-024-07763-9" target="_blank" rel="noreferrer">Scientific reference ↗</a><a href="https://github.com/philshiu/Drosophila_brain_model" target="_blank" rel="noreferrer">Data & attribution ↗</a><span className="mono">LOCAL-FIRST. EXPLORATORY BY DESIGN.</span></div></footer>
 {controls&&<Controls engine={engine} onClose={()=>setControls(false)}/>}</main></div>;
}
