import {ACTIONS,isAction,type Action,type ClientMessage,type GraphView,type ServerMessage,type Topology} from '../../../packages/protocol';
import {createMatch,step,decideBot,policy,hashState,parseReplay,replayStart,observation,type Difficulty,type Match,type Replay,type AnyReplay,type SceneName,type Decision} from '../../../packages/sim/core';
import {brainSocketUrl} from './config';
export type Mode='human'|'spectate'|'lab'|'replay';
export class Engine{
 state:Match=createMatch();mode:Mode='spectate';difficulty:Difficulty='medium';topology:Topology='real';paused=false;matchStarted=true;
 graph:GraphView|null=null;activity:number[]=[];aggregate=0;brainMs=0;gameMs=0;action:Action=0;scores:number[]=[];available:boolean[]=[];inputs:number[]=[];neuralRule:string|null=null;
 connected=false;ready=false;lastResponse=0;neuralActions=0;activityUpdates=0;checkpoint='seed-initialized';checkpointHash='';datasetHash='unavailable';trainingEnabled=true;requestedCheckpoint='';loadingCheckpoint=false;
 training:Extract<ServerMessage,{type:'train_progress'}>|null=null;checkpoints:Extract<ServerMessage,{type:'checkpoint_list'}>['items']=[];
 keys=new Set<string>();actions:[Action,Action][]=[];replay:AnyReplay|null=null;lastReplay:AnyReplay|null=null;replayCursor=0;error='';simulationSpeed=1;
 botDecision:Decision={action:0,rule:'waiting',reason:'Waiting for the match to begin',frame:0};humanDecision='No key pressed';history:{frame:number;action:Action}[]=[];sourceSegments:Replay['sourceSegments']=[];
 private ws:WebSocket|null=null;private heartbeat:ReturnType<typeof setInterval>|null=null;private retry:ReturnType<typeof setTimeout>|null=null;private stopped=false;private awaiting=-1;private sentAt=0;private accumulator=0;
 get online(){return this.connected&&this.ready&&performance.now()-this.lastResponse<6500;}
 get actionName(){return ACTIONS[this.action];}
 get isNeural(){return !['rule','random'].includes(this.topology);}
 get rightName(){return this.mode==='replay'?'RECORDED FIGHTER':!this.online?'DEMO BOT':!this.isNeural?'CONTROL BOT':'FLY BRAIN';}
 private clearSignals(){this.activity=[];this.aggregate=0;this.scores=[];this.inputs=[];this.available=[];this.neuralRule=null;}
 connect(){
  this.stopped=false;
  try{this.ws=new WebSocket(brainSocketUrl(import.meta.env.VITE_BRAIN_URL,location.origin,import.meta.env.DEV));}catch{this.error='Fly Brain address is invalid';return;}
  this.ws.onopen=()=>{this.connected=true;this.send({v:2,type:'reset',seed:this.state.seed,topology:this.topology});};
  this.ws.onmessage=event=>{
   try{
    if(typeof event.data!=='string'||event.data.length>100000)throw Error('Response too large');
    const m=JSON.parse(event.data) as ServerMessage;if(m.v!==2)throw Error('Protocol version mismatch');
    this.lastResponse=performance.now();
    if(m.type==='status'){
     if(!Number.isInteger(m.neurons)||m.neurons<0||m.neurons>5000||!Number.isInteger(m.edge_count)||m.edge_count<0||m.edge_count>500000||!Array.isArray(m.ids)||m.ids.length>256||m.roles.length!==m.ids.length||m.edges.length>600||!m.roles.every(x=>Number.isInteger(x)&&x>=0&&x<=2)||!m.ids.every(x=>typeof x==='string'&&x.length<40)||!m.edges.every(e=>e.length===3&&Number.isInteger(e[0])&&Number.isInteger(e[1])&&Number.isFinite(e[2])&&Math.abs(e[2])<=1&&e[0]>=0&&e[1]>=0&&e[0]<m.ids.length&&e[1]<m.ids.length))throw Error('Graph schema');
     if(typeof m.checkpoint_hash!=='string'||m.checkpoint_hash!==''&&!/^[a-f0-9]{64}$/.test(m.checkpoint_hash))throw Error('Checkpoint hash');this.graph=m;this.datasetHash=m.dataset_hash;this.checkpointHash=m.checkpoint_hash;this.checkpoint=m.checkpoint;this.trainingEnabled=m.training_enabled;this.awaiting=-1;this.clearSignals();this.activity=new Array(m.ids.length).fill(0);
     if(this.requestedCheckpoint&&m.checkpoint!==this.requestedCheckpoint){this.ready=false;if(!this.loadingCheckpoint){this.loadingCheckpoint=true;this.send({v:2,type:'checkpoint_load',id:this.requestedCheckpoint});}}
     else{this.ready=true;this.loadingCheckpoint=false;}
    }else if(m.type==='action'){
     if(!isAction(m.action)||!Number.isFinite(m.tick_ms)||m.scores.length!==0&&m.scores.length!==14||!m.scores.every(v=>Number.isFinite(v)&&Math.abs(v)<1e6)||m.available.length!==14||!m.available.every(v=>typeof v==='boolean')||m.inputs.length!==20||!m.inputs.every(v=>Number.isFinite(v)&&Math.abs(v)<=1)||m.rule!==null&&(typeof m.rule!=='string'||m.rule.length>200))throw Error('Decision schema');
     if(m.seq===this.awaiting){this.action=m.action;this.brainMs=m.tick_ms;this.scores=m.scores;this.available=m.available;this.inputs=m.inputs;this.neuralRule=m.rule;this.awaiting=-1;this.neuralActions++;this.history=[...this.history,{frame:m.seq,action:m.action}].slice(-12);}
    }else if(m.type==='neural_activity'){
     if(!Array.isArray(m.values)||m.values.length!==this.graph?.ids.length||!m.values.every(v=>Number.isFinite(v)&&Math.abs(v)<=1.01)||!Number.isFinite(m.aggregate))throw Error('Activity schema');
     if(this.mode!=='replay'){this.activity=m.values;this.aggregate=m.aggregate;this.activityUpdates++;}
    }else if(m.type==='train_progress'){this.training=m;if(m.status!=='training')this.send({v:2,type:'checkpoint_list'});}
    else if(m.type==='checkpoint_list'){if(!Array.isArray(m.items)||m.items.length>80)throw Error('Snapshot limit');this.checkpoints=m.items;}
    else if(m.type==='error'){this.error=m.code;if(m.code==='checkpoint_incompatible'){this.requestedCheckpoint='';this.loadingCheckpoint=false;}if(m.code.startsWith('training_')&&this.training)this.training={...this.training,status:'stopped'};}
    else if(m.type==='checkpoint_load')this.checkpoint=m.id;
    else if(m.type==='health'&&m.status==='training_cancelled'&&this.training)this.training={...this.training,status:'cancelled'};
   }catch{this.error='Fly Brain response could not be verified';this.ws?.close();}
  };
  this.ws.onclose=()=>{this.connected=false;this.ready=false;this.loadingCheckpoint=false;this.awaiting=-1;this.graph=null;this.clearSignals();this.brainMs=0;if(!this.stopped)this.retry=setTimeout(()=>this.connect(),3000);};
  this.ws.onerror=()=>{};
  if(!this.heartbeat)this.heartbeat=setInterval(()=>this.send({v:2,type:'health'}),2000);
 }
 destroy(){this.stopped=true;if(this.retry)clearTimeout(this.retry);if(this.heartbeat)clearInterval(this.heartbeat);this.heartbeat=null;this.retry=null;this.ws?.close();}
 send(message:ClientMessage){if(this.ws?.readyState===WebSocket.OPEN&&this.ws.bufferedAmount<8192)this.ws.send(JSON.stringify(message));}
 reset(seed=this.state.seed,scene:SceneName='standard',limit=2700){
  if(this.actions.length&&this.mode!=='replay')this.lastReplay=this.exportReplay();
  this.state=createMatch(seed,scene,limit);this.actions=[];this.sourceSegments=[];this.paused=false;this.matchStarted=true;this.replayCursor=0;this.action=0;this.awaiting=-1;this.accumulator=0;this.error='';this.ready=false;this.loadingCheckpoint=false;this.history=[];this.clearSignals();this.checkpoint='seed-initialized';this.checkpointHash='';
  if(this.mode!=='replay')this.replay=null;this.send({v:2,type:'reset',seed,topology:this.topology});
 }
 setMode(mode:Mode){
  if(this.actions.length&&this.mode!=='replay')this.lastReplay=this.exportReplay();
  this.mode=mode;this.keys.clear();if(mode==='lab'){this.paused=true;this.send({v:2,type:'checkpoint_list'});}
  else if(mode==='replay'){this.paused=true;this.clearSignals();}else this.reset();
 }
 selectCheckpoint(id:string){this.requestedCheckpoint=id;this.mode='spectate';this.reset();}
 humanAction():Action{
  const k=this.keys,f=this.state.fighters[0],forward=f.face>0?'d':'a';let action:Action=0;
  if(k.has('l'))action=7;
  else if(k.has('k'))action=k.has('s')?12:f.y>0?11:(f.combo??0)>=2?13:6;
  else if(k.has('j'))action=f.y>0?11:k.has('c')?9:k.has(forward)?10:5;
  else if(k.has('w'))action=3;else if(k.has('c'))action=8;else if(k.has('s'))action=4;else if(k.has('a')&&!k.has('d'))action=1;else if(k.has('d')&&!k.has('a'))action=2;
  this.humanDecision=k.size?[...k].map(v=>v.toUpperCase()).join(' + ')+' → '+ACTIONS[action]:'No key pressed → wait';return action;
 }
 update(delta:number){if(this.paused||this.mode==='lab'||!this.matchStarted)return;this.accumulator+=Math.min(delta,100)*this.simulationSpeed;let count=0;while(this.accumulator>=1000/60&&count++<12){this.advance();this.accumulator-=1000/60;}}
 advance(){
  if(this.state.winner!==null)return;const started=performance.now();let pair:[Action,Action];
  if(this.mode==='replay'){if(!this.replay||this.replayCursor>=this.replay.actions.length){this.paused=true;return;}pair=this.replay.actions[this.replayCursor++];}
  else{
   if(this.connected&&this.ready&&this.state.frame%6===0&&this.awaiting<0){this.awaiting=this.state.frame;this.sentAt=performance.now();this.send({v:2,type:'observation',seq:this.state.frame,values:observation(this.state,1)});}
   if(this.awaiting>=0&&performance.now()-this.sentAt>1500){this.ws?.close();this.awaiting=-1;}
   this.botDecision=decideBot(this.state,0,this.difficulty);
   pair=[this.mode==='human'?this.humanAction():this.botDecision.action,this.online?this.action:policy(this.state,1,'medium')];
   if(!this.online)this.action=pair[1];
   const source=this.online?this.topology:'demo-bot',last=this.sourceSegments.at(-1);
   if(!last||last.controller!==source||last.checkpoint!==this.checkpoint){if(this.sourceSegments.length<100)this.sourceSegments.push({frame:this.state.frame,controller:source,checkpoint:this.checkpoint});else{this.paused=true;this.error='Too many reconnects to preserve replay provenance';return;}}
   this.actions.push(pair);
  }
  step(this.state,pair);this.gameMs=performance.now()-started;
 }
 exportReplay():AnyReplay{
  if(this.mode==='replay'&&this.replay)return this.replay;
  return {v:2,engine:'combat-v2',seed:this.state.seed,scene:this.state.scene,limit:this.state.limit,actions:this.actions.map(a=>[...a]),finalHash:hashState(this.state),controller:this.topology,datasetHash:this.datasetHash,difficulty:this.difficulty,checkpoint:this.checkpoint,checkpointHash:this.checkpointHash,controlMode:this.mode,sourceSegments:this.sourceSegments.map(s=>({...s}))};
 }
 loadReplay(text:string){const replay=parseReplay(text);this.mode='replay';this.replay=replay;this.state=replayStart(replay);this.replayCursor=0;this.actions=[];this.paused=false;this.matchStarted=true;this.accumulator=0;this.clearSignals();}
 seek(frame:number){if(!this.replay)return;const end=Math.max(0,Math.min(Math.floor(frame),this.replay.actions.length));this.state=replayStart(this.replay);for(let i=0;i<end;i++)step(this.state,this.replay.actions[i]);this.replayCursor=end;this.paused=true;}
 snapshot(){return {state:structuredClone(this.state),online:this.online,neuralActions:this.neuralActions,activityUpdates:this.activityUpdates,aggregate:this.aggregate,activity:[...this.activity],action:this.action,scores:[...this.scores],graph:this.graph,mode:this.mode,paused:this.paused,hash:hashState(this.state),botDecision:this.botDecision};}
}
declare global{interface Window{__FLYWEIGHT__?:{snapshot:()=>ReturnType<Engine['snapshot']>;scene:(name:SceneName,seed?:number,seconds?:number)=>void;pause:(p:boolean)=>void;exportReplay:()=>AnyReplay;loadReplay:(text:string)=>void;step:(frames:number)=>void;engine:Engine};}}
