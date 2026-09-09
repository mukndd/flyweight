import {test,expect} from '@playwright/test';
test('real neural interface completes a full round, records and replays it deterministically',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.goto('/');await page.waitForFunction(()=>window.__FLYWEIGHT__?.snapshot().online);
 await page.evaluate(()=>window.__FLYWEIGHT__!.scene('close-combat',783,45));
 await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().neuralActions>12);
 const first=await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().activity);
 await page.waitForTimeout(1500);
 const second=await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().activity);
 expect(first).not.toEqual(second);
 await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().state.winner!==null,{timeout:55000});
 const result=await page.evaluate(()=>({snapshot:window.__FLYWEIGHT__!.snapshot(),replay:window.__FLYWEIGHT__!.exportReplay()}));
 expect(result.snapshot.neuralActions).toBeGreaterThan(50);expect(result.snapshot.graph!.neurons).toBe(1536);
 expect(result.snapshot.state.fighters.some(f=>f.hp<100)).toBe(true);
 await page.screenshot({path:'docs/screenshots/round-complete.png',fullPage:true});
 await page.evaluate(text=>{window.__FLYWEIGHT__!.loadReplay(text);window.__FLYWEIGHT__!.step(5400);},JSON.stringify(result.replay));
 expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().hash)).toBe(result.snapshot.hash);
 expect(errors).toEqual([]);
});
test('keyboard, pause, layout, topology controls and mobile warning',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Play',exact:true}).click();
 const before=await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().state.fighters[0].x);
 await page.keyboard.down('d');await page.waitForTimeout(300);await page.keyboard.up('d');
 expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().state.fighters[0].x)).toBeGreaterThan(before);
 await page.getByRole('button',{name:'Pause',exact:true}).click();const frame=await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().state.frame);await page.waitForTimeout(250);expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().state.frame)).toBe(frame);
 await page.getByRole('button',{name:'Arena only',exact:true}).click();await expect(page.locator('.brain-panel')).toBeHidden();
 await page.getByRole('button',{name:'Split view',exact:true}).click();await expect(page.locator('.brain-panel')).toBeVisible();
 await page.getByLabel('Controller topology').selectOption('weight_shuffled');await page.waitForFunction(()=>window.__FLYWEIGHT__!.engine.topology==='weight_shuffled'&&window.__FLYWEIGHT__!.snapshot().online);
 await page.getByRole('button',{name:'Inspect the interface +'}).click();await expect(page.getByText('What enters the network')).toBeVisible();
 await page.setViewportSize({width:390,height:844});await expect(page.locator('.mobile-warning')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'docs/screenshots/mobile.png',fullPage:true});
});
test('training cancellation, candidates and replay rejects unknown version',async({page})=>{
 await page.goto('/');await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().online);
 await page.getByRole('button',{name:'Training lab'}).click();await page.getByRole('spinbutton',{name:'Generations'}).fill('20');
 await page.getByRole('button',{name:'Start candidate run ↗'}).click();await page.waitForTimeout(500);await page.getByRole('button',{name:'Stop training'}).click();
 await expect(page.locator('.lab-status')).toContainText('cancelled');
 await page.getByRole('button',{name:'Refresh ↻'}).click();await expect(page.locator('.checkpoint-list')).toContainText('candidate_');
 await page.screenshot({path:'docs/screenshots/training-lab.png',fullPage:true});
 const rejected=await page.evaluate(()=>{try{window.__FLYWEIGHT__!.loadReplay('{"v":99}');return false;}catch{return true;}});expect(rejected).toBe(true);
});
test('offline local controller stays playable with persistent disclosure',async({page})=>{
 await page.routeWebSocket('ws://127.0.0.1:8000/ws',ws=>ws.close());
 await page.goto('/');await expect(page.locator('.warning')).toContainText('LOCAL DEMO');
 await page.evaluate(()=>window.__FLYWEIGHT__!.scene('close-combat',2,6));await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().state.winner!==null,{timeout:10000});
 expect(await page.evaluate(()=>window.__FLYWEIGHT__!.snapshot().neuralActions)).toBe(0);
 await page.screenshot({path:'docs/screenshots/offline-fallback.png',fullPage:true});
});

