import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1100}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
await page.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});
await page.waitForFunction(()=>window.__FLYWEIGHT__?.snapshot().neuralActions>8,{timeout:20000});
await page.screenshot({path:'docs/screenshots/desktop.png',fullPage:true});
const snapshot=await page.evaluate(()=>({title:document.title,text:document.body.innerText,debug:window.__FLYWEIGHT__.snapshot(),overflow:document.documentElement.scrollWidth>innerWidth}));
await fs.writeFile('logs/browser-initial.json',JSON.stringify({errors,...snapshot},null,2));
console.log(JSON.stringify({errors,online:snapshot.debug.online,neuralActions:snapshot.debug.neuralActions,activityUpdates:snapshot.debug.activityUpdates,aggregate:snapshot.debug.aggregate,overflow:snapshot.overflow}));
await browser.close();

