import {expect,test} from '@playwright/test';

test('public Watch is the default exhibit with reduced navigation',async({page})=>{
 const errors:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('ERR_CONNECTION_REFUSED')&&!m.text().includes('WebSocket connection'))errors.push(m.text());});
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'FLYWEIGHT'})).toBeVisible();
 await expect(page.getByRole('navigation',{name:'Public navigation'})).toContainText('WATCH');
 await expect(page.getByRole('navigation',{name:'Public navigation'})).toContainText('FIGHT');
 await expect(page.getByRole('navigation',{name:'Public navigation'})).toContainText('SCIENCE');
 await expect(page.getByRole('button',{name:'Lab'})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Replays'})).toHaveCount(0);
 await expect(page.locator('.experiment-scene')).toBeVisible();
 await expect(page.locator('.fly-station .presentation3d')).toBeVisible();
 await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().state.frame>90);
 await expect(page.locator('.event-stream')).toContainText(/Selected|landed|blocked|whiffed|countered/i);
 await page.getByRole('button',{name:'8',exact:true}).click();
 expect(await page.evaluate(()=>window.__FLYWEIGHT__!.engine.publicLevel)).toBe(8);
 expect(await page.evaluate(()=>window.__FLYWEIGHT__!.engine.difficulty)).toBe('hard');
 await page.screenshot({path:'docs/screenshots/v10-watch.png',fullPage:true});
 expect(errors).toEqual([]);
});

test('Fight setup starts a human challenge and shows a compact result',async({page})=>{
 await page.goto('/');
 await page.getByRole('button',{name:'FIGHT',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Fight the Fly'})).toBeVisible();
 await page.getByLabel('Name').fill('Ada');
 await page.getByRole('button',{name:'START FIGHT'}).click();
 await expect(page.getByRole('heading',{name:/Ada vs FW-/})).toBeVisible();
 await expect(page.locator('.experiment-scene')).toBeVisible();
 await page.waitForFunction(()=>window.__FLYWEIGHT__!.snapshot().state.frame>90);
 await page.screenshot({path:'docs/screenshots/v10-human-fight.png',fullPage:true});
 await page.evaluate(()=>{
  const engine=window.__FLYWEIGHT__!.engine;
  engine.state.winner=1;
  engine.state.fighters[0].hp=18;
  engine.state.fighters[1].hp=54;
 });
 await expect(page.getByRole('heading',{name:'LOSS'})).toBeVisible();
 await expect(page.locator('.result-metrics')).toContainText('Ada');
 await page.screenshot({path:'docs/screenshots/v10-human-result.png',fullPage:true});
});

test('Science keeps raw machinery out of Watch but available in depth',async({page})=>{
 await page.goto('/');
 await page.getByRole('button',{name:'SCIENCE'}).click();
 await expect(page.getByRole('heading',{name:'What is actually running?'})).toBeVisible();
 await expect(page.locator('.science-page')).toContainText('Raw checkpoint');
 await expect(page.locator('.science-page')).toContainText('Controller Boundary');
 await expect(page.locator('.science-page')).toContainText('deterministic graph layout');
 await page.screenshot({path:'docs/screenshots/v10-science.png',fullPage:true});
});

test('mobile public view does not expose dashboard controls or overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'FLYWEIGHT'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Lab'})).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'docs/screenshots/v10-mobile.png',fullPage:true});
});
