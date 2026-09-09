export const VERSION = 1 as const;
export const ACTIONS = ['Idle','Move left','Move right','Jump','Block','Light attack','Heavy attack','Dodge'] as const;
export type Action = 0|1|2|3|4|5|6|7;
export type Topology = 'real'|'degree_randomized'|'weight_shuffled'|'ordinary'|'rule'|'random';
export const CHANNELS = ['Relative x','Relative y','Opponent vx','Opponent vy','Own vx','Own vy','Distance','Incoming attack','Opponent block','Own health','Opponent health','Left boundary','Right boundary','Recent damage','Previous action','Round time'] as const;
export type ClientMessage =
 | {v:1;type:'reset';seed:number;topology:Topology}
 | {v:1;type:'observation';seq:number;values:number[]}
 | {v:1;type:'health'|'train_stop'|'checkpoint_list'}
 | {v:1;type:'train_start';seed:number;generations:number;population:number;episode_seconds:number}
 | {v:1;type:'checkpoint_load';id:string};
export interface GraphView {ids:string[];roles:number[];edges:[number,number,number][];neurons:number;edge_count:number;synthetic:boolean;dataset_hash:string;input_count:number;output_count:number;}
export interface Activity {v:1;type:'neural_activity';seq:number;values:number[];aggregate:number;tick_ms:number;}
export type ServerMessage =
 | ({v:1;type:'status';controller:string;topology:Topology;checkpoint:string} & GraphView)
 | {v:1;type:'action';seq:number;action:Action;tick_ms:number}
 | Activity
 | {v:1;type:'health';status:string;training:boolean}
 | {v:1;type:'error';code:string}
 | {v:1;type:'train_progress';generation:number;generations:number;reward:number;win_rate:number;checkpoint:string;seed:number;status:string}
 | {v:1;type:'checkpoint_list';items:{id:string;seed:number;generation:number;reward:number;canonical:boolean}[]}
 | {v:1;type:'checkpoint_load';id:string};
export function isAction(x:unknown):x is Action {return Number.isInteger(x)&&Number(x)>=0&&Number(x)<8;}

