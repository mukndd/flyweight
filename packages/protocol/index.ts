export const VERSION=2 as const;
export const ACTIONS=['Wait','Move left','Move right','Jump','Block','Light punch','Heavy punch','Dodge','Crouch guard','Low kick','Advancing punch','Air strike','Shove','Combo finisher'] as const;
export type Action=0|1|2|3|4|5|6|7|8|9|10|11|12|13;
export const ACTION_COUNT=ACTIONS.length;
export type Topology='real'|'degree_randomized'|'weight_shuffled'|'ordinary'|'rule'|'random';
export const CHANNELS=['Opponent direction','Opponent height','Opponent sideways speed','Opponent vertical speed','Own sideways speed','Own vertical speed','Distance','Opponent attacking','Opponent blocking','Own health','Opponent health','Room on left','Room on right','Recent damage','Previous action','Time remaining','On the ground','Ready to attack','Combo progress','Opponent recovering'] as const;
export type ClientMessage=
 |{v:2;type:'reset';seed:number;topology:Topology}
 |{v:2;type:'observation';seq:number;values:number[]}
 |{v:2;type:'health'|'train_stop'|'checkpoint_list'}
 |{v:2;type:'train_start';seed:number;generations:number;population:number;episode_seconds:number}
 |{v:2;type:'checkpoint_load';id:string};
export interface GraphView{ids:string[];roles:number[];edges:[number,number,number][];neurons:number;edge_count:number;synthetic:boolean;dataset_hash:string;input_count:number;output_count:number;}
export interface Activity{v:2;type:'neural_activity';seq:number;values:number[];aggregate:number;tick_ms:number;}
export type ServerMessage=
 |({v:2;type:'status';controller:string;topology:Topology;checkpoint:string;checkpoint_hash:string;training_enabled:boolean}&GraphView)
 |{v:2;type:'action';seq:number;action:Action;tick_ms:number;scores:number[];available:boolean[];inputs:number[];rule:string|null}
 |Activity
 |{v:2;type:'health';status:string;training:boolean}
 |{v:2;type:'error';code:string}
 |{v:2;type:'train_progress';generation:number;generations:number;reward:number;win_rate:number;training_win_rate?:number;checkpoint:string;seed:number;status:string;run?:string;trainer?:string;population?:number;scenario_set?:string;reward_version?:string;evaluation_suite?:string;candidate_evaluation_reward?:number;held_out_win_rate?:number;held_out_episodes?:number;best_training_fitness?:number|null;best_generation?:number;best_checkpoint?:string;best_training_win_rate?:number;final_generation_best?:number;final_generation_win_rate?:number}
 |{v:2;type:'checkpoint_list';items:{id:string;seed:number;generation:number;reward:number;canonical:boolean;status?:string;validation_win_rate?:number;held_out_win_rate?:number;promotion_status?:string}[]}
 |{v:2;type:'checkpoint_load';id:string};
export function isAction(x:unknown):x is Action{return Number.isInteger(x)&&Number(x)>=0&&Number(x)<ACTION_COUNT;}

