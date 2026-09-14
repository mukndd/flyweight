import {test,expect} from '@playwright/test';
test('full live round, measured signals, expanded replay and deterministic playback',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.goto('/');await expect(page.getByRole('heading',{name:/fruit-fly connectome/i})).toBeVisible();await expect(page.locator('.presentation3d.hero')).toBeVisible();await page.getByRole('button',{name:'Watch',exact:true}).click();await page.waitForFunction(()=>window.__FLYWEIGHT__?.snapshot().online);
 await expect(page.locator('.match-pair')).toContainText('BOT');await expect(page.locator('.match-pair')).toContainText('FLY BRAIN');
 await page.evaluate(()=>window.__FLYWEIGHT__!.scene('close-combat',783,45));
 await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().neuralActions>12);
 const first=await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().activity);
 await page.waitForTimeout(1500);expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().activity)).not.toEqual(first);
 expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().scores.length)).toBe(14);
 await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().state.winner!==null,null,{timeout:55000});
 const result=await page.evaluate(()=>({snapshot:window.__FLYWEIGHT__!.snapshot(),replay:window.__FLYWEIGHT__!.exportReplay()}));
 expect(result.snapshot.neuralActions).toBeGreaterThan(50);expect(result.snapshot.graph!.neurons).toBe(1536);
 expect(result.snapshot.state.fighters.some(f=>f.hp<100)).toBe(true);
 await page.screenshot({path:'docs/screenshots/round-complete.png',fullPage:true});
 await page.evaluate(text=>{window.__FLYWEIGHT__!.loadReplay(text);window.__FLYWEIGHT__!.step(5400);},JSON.stringify(result.replay));
 expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().hash)).toBe(result.snapshot.hash);
 expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().activity)).toEqual([]);
 expect(errors).toEqual([]);
});
test('play, every keyboard action, controls focus and compact pause',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Play',exact:true}).click();
 await expect(page.locator('.match-pair')).toContainText('YOU');await expect(page.getByLabel('Bot difficulty')).toBeDisabled();
 await page.locator('.phaser-host').focus();
 const before=await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().state.fighters[0].x);
 await page.keyboard.down('d');await page.waitForTimeout(250);await page.keyboard.up('d');
 expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().state.fighters[0].x)).toBeGreaterThan(before);
 await page.keyboard.press('Space');const frame=await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().state.frame);
 await page.waitForTimeout(250);expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().state.frame)).toBe(frame);
 await expect(page.locator('.pause-card')).toBeVisible();
 await page.getByRole('button',{name:'Controls',exact:false}).first().click();
 await expect(page.getByRole('dialog')).toBeVisible();await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toBeHidden();
 await page.locator('.phaser-host').focus();
 const patterns:[string[],number,number,number][]=[[[],0,0,0],[['a'],1,0,0],[['d'],2,0,0],[['w'],3,0,0],[['s'],4,0,0],[['j'],5,0,0],[['k'],6,0,0],[['l'],7,0,0],[['c'],8,0,0],[['c','j'],9,0,0],[['d','j'],10,0,0],[['j'],11,50,0],[['s','k'],12,0,0],[['k'],13,0,2]];
 for(const [keys,action,y,combo] of patterns){
  await page.evaluate(({y,combo})=>{const e=window.__FLYWEIGHT__!.engine;e.paused=true;e.state.fighters[0].face=1;e.state.fighters[0].y=y;e.state.fighters[0].combo=combo;},{y,combo});
  for(const key of keys)await page.keyboard.down(key);
  expect(await page.evaluate(()=>window.__FLYWEIGHT__!.engine.humanAction())).toBe(action);
  for(const key of keys)await page.keyboard.up(key);
 }
 await page.locator('.pause-card').getByRole('button',{name:'Resume',exact:true}).click();
 await expect(page.locator('.pause-card')).toBeHidden();
});
test('difficulty, research controls, reconnect, responsive and reduced motion',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Watch',exact:true}).click();await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().online);
 for(const value of ['easy','medium','hard']){await page.getByLabel('Bot difficulty').selectOption(value);expect(await page.evaluate(()=>window.__FLYWEIGHT__!.engine.difficulty)).toBe(value);}
 await page.getByRole('button',{name:'Arena only',exact:true}).click();await expect(page.locator('.decision-panels')).toBeHidden();
 await page.getByRole('button',{name:'Fight and decisions',exact:true}).click();
 await page.locator('.research-details > summary').click();
 for(const topology of ['weight_shuffled','degree_randomized','ordinary','rule','random','real']){
  await page.getByLabel('Research controller').selectOption(topology);
  await page.waitForFunction(t=>window.__FLYWEIGHT__!.snapshot().online&&window.__FLYWEIGHT__!.engine.graph!==null&&window.__FLYWEIGHT__!.engine.topology===t,topology);
  if(topology==='rule'||topology==='random'){await page.waitForTimeout(250);expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().graph!.neurons)).toBe(0);expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().activity)).toEqual([]);}
 }
 await page.evaluate(()=>window.__FLYWEIGHT__!.engine.destroy());await expect(page.locator('.warning')).toContainText('Fly Brain offline');
 expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().activity)).toEqual([]);
 await page.evaluate(()=>window.__FLYWEIGHT__!.engine.connect());await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().online&&window.__FLYWEIGHT__!.snapshot().activity.some(x=>x!==0));
 await page.emulateMedia({reducedMotion:'reduce'});await page.setViewportSize({width:390,height:844});
 await expect(page.locator('.mobile-warning')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'docs/screenshots/mobile.png',fullPage:true});
});
test('training cancellation and safe replay rejection',async({page})=>{
 await page.goto('/');await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().online);
 await page.getByRole('button',{name:'Lab',exact:true}).click();await page.getByRole('spinbutton',{name:'Generations'}).fill('20');
 await page.getByRole('button',{name:'Start candidate run ↗'}).click();await page.waitForTimeout(500);await page.getByRole('button',{name:'Stop training'}).click();
 await expect(page.locator('.lab-status')).toContainText('cancelled');
 await page.screenshot({path:'docs/screenshots/training-lab.png',fullPage:true});
 expect(await page.evaluate(()=>{try{window.__FLYWEIGHT__!.loadReplay('{"v":99}');return false;}catch{return true;}})).toBe(true);
});
test('offline demo remains playable without fabricated neural activity',async({page})=>{
 await page.routeWebSocket('ws://127.0.0.1:8000/ws',ws=>ws.close());
 await page.goto('/');await expect(page.locator('.warning')).toContainText('Using the demo bot');await page.getByRole('button',{name:'Watch',exact:true}).click();
 await expect(page.locator('.match-pair')).toContainText('DEMO BOT');
 await page.evaluate(()=>window.__FLYWEIGHT__!.scene('close-combat',2,6));
 await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().state.winner!==null,null,{timeout:10000});
 const s=await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot());expect(s.neuralActions).toBe(0);expect(s.activity).toEqual([]);expect(s.scores).toEqual([]);
 await page.screenshot({path:'docs/screenshots/offline-fallback.png',fullPage:true});
});
