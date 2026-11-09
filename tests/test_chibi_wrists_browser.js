/* Optional: real Chromium against isolated wrist preview. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const {chromium} = require('playwright-core');
const mod = require('@sparticuz/chromium');
const pkg = mod.default || mod;
(async () => {
 const browser = await chromium.launch({headless:true, executablePath:await pkg.executablePath(), args:pkg.args});
 try {
  const page=await browser.newPage({viewport:{width:1360,height:900}}), errors=[];
  page.on('pageerror', e => errors.push(String(e)));
  const base=process.env.ZCHIBI_PREVIEW || 'http://127.0.0.1:5220';
  await page.goto(base,{waitUntil:'domcontentloaded'});
  assert((await page.title()).includes('手腕连接试验'));
  const l=page.getByLabel('左手腕（试验）',{exact:true}),r=page.getByLabel('右手腕（试验）',{exact:true});
  await l.waitFor();await r.waitFor();
  await l.evaluate(el => {for(const v of ['0.2','-0.7','0.85']) {el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));}});
  await r.evaluate(el => {el.value='-0.75';el.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForFunction(async()=>{const p=(await (await fetch('/api/params.json')).json()).params;
   return Math.abs(p.find(x=>x.id==='ParamWristL').value-.85)<.001 && Math.abs(p.find(x=>x.id==='ParamWristR').value+.75)<.001;},null,{timeout:10000});
  assert.strictEqual((await page.evaluate(async()=> (await (await fetch('/api/info.json')).json()).action)),'neutral');
  const out=path.resolve(process.env.ZCHIBI_QA || 'build/wrist-browser-qa');fs.mkdirSync(out,{recursive:true});
  await page.screenshot({path:path.join(out,'wrist_browser.png'),fullPage:true});
  await page.getByRole('button',{name:'静止并复位'}).click();
  await page.waitForFunction(async()=>{const p=(await (await fetch('/api/params.json')).json()).params;
   return ['ParamWristL','ParamWristR'].every(id=>Math.abs(p.find(x=>x.id===id).value)<.001);},null,{timeout:10000});
  assert.strictEqual(await l.inputValue(),'0');assert.strictEqual(await r.inputValue(),'0');
  await page.getByRole('button',{name:'手腕小摆（试验）'}).click();
  await page.waitForFunction(async()=> (await (await fetch('/api/info.json')).json()).action === 'wrist_test',null,{timeout:10000});
  assert.deepStrictEqual(errors,[]);
  await page.evaluate(async()=>{await fetch('/api/action?id=idle');await fetch('/api/pause?on=0');});
  console.log('真实 Chromium：左右腕最终值、neutral、复位与手腕动作按钮通过');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
