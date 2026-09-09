import {ACTIONS,isAction,type Action,type ClientMessage,type GraphView,type ServerMessage,type Topology} from '../../../packages/protocol';
import {createMatch,step,policy,hashState,parseReplay,type Difficulty,type Match,type Replay,type SceneName} from '../../../packages/sim/core';
export type Mode='human'|'spectate'|'lab'|'replay';
export class Engine {
 state:Match=createMatch(); mode:Mode='spectate'; difficulty:Difficulty='medium';topology:Topology='real';paused=false;
 graph:GraphView|null=null;activity:number[]=[];aggregate=0;brainMs=0;gameMs=0;action:Action=0;
 connected=false;ready=false;lastResponse=0;neuralActions=0;activityUpdates=0;status='Connecting to local service';checkpoint='seed-initialized';
 training:Extract<ServerMessage,{type:'train_progress'}>|null=null;
 checkpoints:Extract<ServerMessage,{type:'checkpoint_list'}>['items']=[];
 keys=new Set<string>();actions:[Action,Action][]=[];replay:Replay|null=null;replayCursor=0;error='';simulationSpeed=1;
 private ws:WebSocket|null=null;private heartbeat:ReturnType<typeof setInterval>|null=null;private retry:ReturnType<typeof setTimeout>|null=null;private stopped=false;
 private awaiting=-1;private sentAt=0;private accumulator=0;
 get online(){return this.connected&&this.ready&&performance.now()-this.lastResponse<2000;}
 get actionName(){return ACTIONS[this.action];}
 connect(){
  this.stopped=false;
  this.ws=new WebSocket('ws://127.0.0.1:8000/ws');
  this.ws.onopen=()=>{this.connected=true;this.status='Neural service connected';this.send({v:1,type:'reset',seed:this.state.seed,topology:this.topology});};
  this.ws.onmessage=(event)=>{
   try{
    if(typeof event.data!=='string'||event.data.length>100_000)throw Error('Oversized service response');
    const m=JSON.parse(event.data) as ServerMessage;if(m.v!==1)throw Error('Protocol version');
    this.lastResponse=performance.now();
    if(m.type==='status'){
     if(!Number.isInteger(m.neurons)||m.neurons<1||m.neurons>5000||!Number.isInteger(m.edge_count)||m.edge_count>500000||!Array.isArray(m.ids)||m.ids.length>256||m.roles.length!==m.ids.length||m.edges.length>600||!m.roles.every(x=>Number.isInteger(x)&&x>=0&&x<=2)||!m.ids.every(x=>typeof x==='string'&&x.length<40)||!m.edges.every(e=>e.length===3&&e.every(Number.isInteger)&&e[0]>=0&&e[1]>=0&&e[0]<m.ids.length&&e[1]<m.ids.length&&Math.abs(e[2])===1))throw Error('Graph schema');
     this.graph=m;this.ready=true;this.awaiting=-1;this.checkpoint=m.checkpoint;this.activity=new Array(m.ids.length).fill(0);
    }else if(m.type==='action'){
     if(!isAction(m.action)||!Number.isFinite(m.tick_ms))throw Error('Action schema');
     if(m.seq===this.awaiting){this.action=m.action;this.brainMs=m.tick_ms;this.awaiting=-1;this.neuralActions++;}
    }else if(m.type==='neural_activity'){
     if(!Array.isArray(m.values)||m.values.length!==this.graph?.ids.length||!m.values.every(v=>Number.isFinite(v)&&v>=0&&v<=1.01)||!Number.isFinite(m.aggregate))throw Error('Activity schema');
     this.activity=m.values;this.aggregate=m.aggregate;this.activityUpdates++;
    }else if(m.type==='train_progress'){this.training=m;if(m.status!=='training')this.send({v:1,type:'checkpoint_list'});}
    else if(m.type==='checkpoint_list')this.checkpoints=m.items;
    else if(m.type==='error'){this.error=m.code;this.status=m.code;}
    else if(m.type==='checkpoint_load'){this.checkpoint=m.id;}
   }catch{this.error='Invalid service response';this.ws?.close(); }
  };
  this.ws.onclose=()=>{
   this.connected=false;this.ready=false;this.awaiting=-1;this.graph=null;this.activity=[];this.aggregate=0;this.brainMs=0;this.status='Local demo · rule-based';
   if(!this.stopped)this.retry=setTimeout(()=>this.connect(),3000);
  };
  this.ws.onerror=()=>{this.status='Local demo · rule-based';};
  if(!this.heartbeat)this.heartbeat=setInterval(()=>this.send({v:1,type:'health'}),5000);
 }
 destroy(){this.stopped=true;if(this.retry)clearTimeout(this.retry);if(this.heartbeat)clearInterval(this.heartbeat);this.ws?.close();}
 send(message:ClientMessage){if(this.ws?.readyState===WebSocket.OPEN&&this.ws.bufferedAmount<8192)this.ws.send(JSON.stringify(message));}
 reset(seed=this.state.seed,scene:SceneName='standard',limit=2700){
  this.state=createMatch(seed,scene,limit);this.actions=[];this.paused=false;this.replayCursor=0;this.action=0;this.awaiting=-1;this.accumulator=0;this.error='';this.ready=false;this.checkpoint='seed-initialized';
  if(this.mode!=='replay')this.replay=null;
  this.send({v:1,type:'reset',seed,topology:this.topology});
 }
 setMode(mode:Mode){this.mode=mode;this.keys.clear();if(mode!=='replay')this.reset();else this.paused=true;}
 humanAction():Action{
  const k=this.keys;if(k.has('l'))return 7;if(k.has('k'))return 6;if(k.has('j'))return 5;if(k.has('w'))return 3;if(k.has('s'))return 4;if(k.has('a')&&!k.has('d'))return 1;if(k.has('d')&&!k.has('a'))return 2;return 0;
 }
 update(delta:number){
  if(this.paused||this.mode==='lab')return;
  this.accumulator+=Math.min(delta,100)*this.simulationSpeed;
  let steps=0;
  while(this.accumulator>=1000/60&&steps++<12){this.advance();this.accumulator-=1000/60;}
 }
 advance(){
  if(this.state.winner!==null)return;
  const start=performance.now();
  let pair:[Action,Action];
  if(this.mode==='replay'){
   if(!this.replay||this.replayCursor>=this.replay.actions.length){this.paused=true;return;}
   pair=this.replay.actions[this.replayCursor++];
  }else{
   if(this.connected&&this.ready&&this.state.frame%6===0&&this.awaiting<0){
    this.awaiting=this.state.frame;this.sentAt=performance.now();
    const f=this.state.fighters[1],o=this.state.fighters[0];
    const values=[(o.x-f.x)/1000,(o.y-f.y)/150,o.vx/10,o.vy/15,f.vx/10,f.vy/15,Math.abs(o.x-f.x)/1000,o.attack?1:0,o.block?1:0,f.hp/100,o.hp/100,(f.x-36)/928,(964-f.x)/928,f.damage,f.action/7,1-this.state.frame/this.state.limit].map(v=>Math.max(-1,Math.min(1,v)));
    this.send({v:1,type:'observation',seq:this.state.frame,values});
   }
   if(this.awaiting>=0&&performance.now()-this.sentAt>1000){this.ws?.close();this.awaiting=-1;}
   const brain=this.online?this.action:policy(this.state,1,'medium');
   pair=[this.mode==='human'?this.humanAction():policy(this.state,0,this.difficulty),brain];
   this.actions.push(pair);
  }
  step(this.state,pair);this.gameMs=performance.now()-start;
 }
 exportReplay():Replay{return {v:1,seed:this.state.seed,scene:this.state.scene,limit:this.state.limit,actions:this.actions.map(a=>[...a]),finalHash:hashState(this.state),controller:this.online?this.topology:'local-demo',datasetHash:this.graph?.dataset_hash??'synthetic-local-demo'};}
 loadReplay(text:string){const replay=parseReplay(text);this.mode='replay';this.replay=replay;this.state=createMatch(replay.seed,replay.scene,replay.limit);this.replayCursor=0;this.actions=[];this.paused=false;this.accumulator=0;}
 seek(frame:number){if(!this.replay)return;const end=Math.max(0,Math.min(Math.floor(frame),this.replay.actions.length));this.state=createMatch(this.replay.seed,this.replay.scene,this.replay.limit);for(let i=0;i<end;i++)step(this.state,this.replay.actions[i]);this.replayCursor=end;this.paused=true;}
 snapshot(){return {state:structuredClone(this.state),online:this.online,neuralActions:this.neuralActions,activityUpdates:this.activityUpdates,aggregate:this.aggregate,activity:[...this.activity],action:this.action,graph:this.graph,mode:this.mode,paused:this.paused,hash:hashState(this.state)};}
}
declare global{interface Window{__FLYWEIGHT__?:{snapshot:()=>ReturnType<Engine['snapshot']>;scene:(name:SceneName,seed?:number,seconds?:number)=>void;pause:(p:boolean)=>void;exportReplay:()=>Replay;loadReplay:(text:string)=>void;step:(frames:number)=>void;engine:Engine};}}

