import {useState} from 'react';
import type {Engine} from './engine';

const pct=(value?:number)=>value===undefined?'--':`${Math.round(value*100)}%`;
const fixed=(value?:number|null)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(1):'--';

export function Lab({engine}:{engine:Engine}){
 const [seed,setSeed]=useState(783),[generations,setGenerations]=useState(2),[population,setPopulation]=useState(6);
 const t=engine.training,last=t&&t.status!=='training'?t:null,active=t?.status==='training';
 const valid=Number.isInteger(seed)&&seed>=0&&seed<=999999&&Number.isInteger(generations)&&generations>=1&&generations<=20;
 const start=()=>{
  engine.training={v:2,type:'train_progress',generation:0,generations,reward:0,win_rate:0,checkpoint:'',seed,status:'training',population,trainer:'CEMTrainer'};
  engine.send({v:2,type:'train_start',seed,generations,population,episode_seconds:12});
 };
 return <><div className="lab-content">{!engine.trainingEnabled&&<p className="training-disabled">Training is disabled in this public demo. Run local experiments to create candidate snapshots.</p>}
  <div className="eyebrow">LEARNING WITHOUT REWIRING</div><h2>Better adapters.<br/><span>The same connections.</span></h2>
  <p>Evolve the sensory adapter and motor readout with Cross-Entropy Method. Every run creates a candidate fork; browser training never promotes a champion.</p>
  <div className="lab-flow"><span>20 game signals</span><b>→</b><span>Frozen connectome</span><b>→</b><span>14 actions</span></div>
  <section className="lab-card next-run" aria-label="Next run configuration"><div className="lab-section-title"><span>NEXT RUN CONFIGURATION</span><small>Editable before start</small></div>
   <div className="lab-fields"><label>Random seed<input type="number" min="0" max="999999" value={seed} onChange={e=>setSeed(Number(e.target.value))}/></label><label>Generations<input type="number" min="1" max="20" value={generations} onChange={e=>setGenerations(Number(e.target.value))}/></label><label>Population<select value={population} onChange={e=>setPopulation(Number(e.target.value))}>{[4,6,8,10,12].map(v=><option key={v}>{v}</option>)}</select></label></div>
   <div className="lab-actions"><button className="primary" disabled={!engine.online||!engine.trainingEnabled||active||!valid} onClick={start}>Start candidate run ↗</button><button className="subtle" disabled={!engine.online} onClick={()=>engine.send({v:2,type:'train_stop'})}>Stop training</button></div>
  </section>
  <section className="lab-card completed-run" aria-label="Current or last completed run"><div className="lab-section-title"><span>CURRENT / LAST COMPLETED RUN</span><small>{active?'Live process state':'Last persisted progress event'}</small></div>
   <div className="progress-track"><span style={{width:`${t?t.generation/t.generations*100:0}%`}}/></div>
   <dl className="run-meta"><div><dt>Run ID</dt><dd>{t?.run??'none yet'}</dd></div><div><dt>Seed</dt><dd>{t?.seed??'--'}</dd></div><div><dt>Generations</dt><dd>{t?`${t.generation}/${t.generations}`:'--'}</dd></div><div><dt>Population</dt><dd>{t?.population??population}</dd></div><div><dt>Trainer</dt><dd>{t?.trainer??'CEMTrainer'}</dd></div><div><dt>Scenario set</dt><dd>{t?.scenario_set??'evaluation-v2 / browser run'}</dd></div><div><dt>Reward version</dt><dd>{t?.reward_version??'combat-v2-reward-1'}</dd></div><div><dt>Status</dt><dd>{t?.status??'ready'}</dd></div></dl>
   <div className="training-stats scoped"><div title="Best training fitness seen in any generation of this run"><small>BEST TRAINING FITNESS</small><strong>{fixed(t?.best_training_fitness??(active?t?.reward:null))}</strong></div><div title="Checkpoint for the highest-fitness candidate seen so far"><small>BEST-EVER CANDIDATE</small><strong>{t?.best_checkpoint?t.best_checkpoint.slice(-6):t?.checkpoint?t.checkpoint.slice(-6):'--'}</strong></div><div title="Best member from the newest completed generation only"><small>FINAL-GENERATION BEST</small><strong>{fixed(t?.final_generation_best??(active?t?.reward:null))}</strong></div><div title="Held-out win rate from the evaluation suite after training completes"><small>HELD-OUT WIN RATE</small><strong>{pct(t?.held_out_win_rate??(last?t?.win_rate:undefined))}</strong></div><div title="Number of held-out episodes used for the displayed win rate"><small>HELD-OUT EPISODES</small><strong>{t?.held_out_episodes??'--'}</strong></div><div title="Evaluation suite used for final candidate evaluation"><small>EVALUATION SUITE</small><strong>{t?.evaluation_suite??'--'}</strong></div><div title="Mean reward from candidate evaluation, not the training fitness"><small>CANDIDATE EVALUATION REWARD</small><strong>{fixed(t?.candidate_evaluation_reward)}</strong></div></div>
   <p className="lab-fixed-note">Fly wiring: <b>fixed</b> · Adapters (encoder / readout / bias): <b>training only</b></p><p className="lab-status" aria-live="polite">{t?.status??'Ready · one local worker · 12-second episodes'}{t?.checkpoint&&` · ${t.checkpoint}`}</p>
  </section>
 </div><div className="match-settings candidate-panel"><div className="checkpoint-title"><strong>Candidate checkpoints</strong><button onClick={()=>engine.send({v:2,type:'checkpoint_list'})}>Refresh ↻</button></div><div className="checkpoint-list">{engine.checkpoints.length?engine.checkpoints.slice(0,8).map(c=><div key={c.id}><span><b>{c.id}</b><small>Generation {c.generation} · seed {c.seed} · training fitness {c.reward.toFixed(1)}</small><small>{c.canonical?'promoted champion':c.promotion_status??'candidate fork'}{c.held_out_win_rate!==undefined?` · held-out ${pct(c.held_out_win_rate)}`:''}</small></span><button onClick={()=>{engine.selectCheckpoint(c.id);}}>Try candidate ↗</button></div>):<p>Refresh to see local candidate forks. Promotion requires CLI evaluation.</p>}</div></div></>;
}
