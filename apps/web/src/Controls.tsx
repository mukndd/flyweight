import {useEffect,useRef} from 'react';
import type {Engine} from './engine';
const controls=[['A / D','Move left / right'],['W','Jump'],['S','Standing block'],['C','Crouch and guard low'],['J','Light punch'],['K','Heavy punch'],['L','Dodge'],['Forward + J','Advancing punch'],['C + J','Low kick'],['Jump, then J or K','Air strike'],['S + K','Shove at close range'],['Land J, J, then K','Combo finisher'],['Block just before a hit','Counter: opens a punish window'],['Space','Pause / resume (arena focused)']];
export function Controls({engine,onClose}:{engine:Engine;onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{const wasPaused=engine.paused;engine.paused=true;engine.keys.clear();dialog.current?.showModal();return()=>{engine.paused=wasPaused;};},[engine]);
 return <dialog ref={dialog} className="controls-dialog" onCancel={onClose}><div className="dialog-heading"><h2>How to fight</h2><button aria-label="Close controls" onClick={onClose}>×</button></div><p>You are the green fighter. Fly Brain is purple when its engine is online.</p><div className="controls-table">{controls.map(([key,meaning])=><div key={key}><kbd>{key}</kbd><span>{meaning}</span></div>)}</div><p>Attacks have startup and recovery. A finisher needs two connected light hits before the combo window expires. Low kicks beat standing guard; crouch guard blocks lows. A shove beats guard but can be dodged.</p><button className="primary" onClick={onClose}>Got it</button></dialog>;
}

