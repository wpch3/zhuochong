/* Optional real Chromium against tools/preview_live2d_chibi.py --dynamic. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const {chromium} = require('playwright-core');
const mod = require('@sparticuz/chromium');
const pkg = mod.default || mod;
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: await pkg.executablePath(), args: pkg.args});
  try {
    const page = await browser.newPage({viewport:{width:1360,height:900}});
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    const base = process.env.ZCHIBI_PREVIEW || 'http://127.0.0.1:5209';
    await page.goto(base, {waitUntil:'domcontentloaded'});
    await page.getByText('动态试装控制', {exact:false}).first().waitFor();
    const slider = page.getByLabel('左侧袖手', {exact:true});
    await slider.waitFor();
    // Rapid changes during an in-flight request must retain the final value.
    await slider.evaluate(el => {
      for (const v of ['0.1','0.3','-0.7','0.85']) {
        el.value = v; el.dispatchEvent(new Event('input', {bubbles:true}));
      }
    });
    await page.waitForFunction(async () => {
      const p = await (await fetch('/api/params.json')).json();
      return Math.abs(p.params.find(x => x.id === 'ParamArmL').value - 0.85) < 0.001;
    }, null, {timeout:10000});
    const info = await page.evaluate(async () => (await fetch('/api/info.json')).json());
    assert.strictEqual(info.action, 'neutral');
    await page.getByRole('button',{name:'静止并复位'}).click();
    await page.waitForFunction(async () => {
      const p = await (await fetch('/api/params.json')).json();
      return Math.abs(p.params.find(x => x.id === 'ParamArmL').value) < 0.001;
    }, null, {timeout:10000});
    assert.strictEqual(await slider.inputValue(), '0');
    const out = path.resolve(process.env.ZCHIBI_QA || 'experiments/live2d_chibi_dynamic/qa');
    fs.mkdirSync(out,{recursive:true});
    await page.screenshot({path:path.join(out,'browser_preview.png'), fullPage:true});
    assert.deepStrictEqual(errors, []);
    await page.evaluate(() => fetch('/api/action?id=idle'));
    console.log('真实 Chromium：动态试装组件加载、快速滑动保留最终值、切入静止并复位通过');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode=1});
