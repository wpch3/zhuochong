/* Real Chromium: local demo, brush, cancellation, undo, zoom, PNG export. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const {chromium} = require('playwright-core');
const mod = require('@sparticuz/chromium'), pkg = mod.default || mod;
const out = path.resolve(process.env.UNDERPAINT_QA || 'build/underpaint-qa');
(async()=>{
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:await pkg.executablePath(),args:pkg.args});
  try {
    const page=await browser.newPage({viewport:{width:1450,height:1000},acceptDownloads:true});
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    await page.goto(process.env.UNDERPAINT_URL || 'http://127.0.0.1:5211/');
    await page.click('#demo');
    await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('已载入'));
    assert.strictEqual(await page.locator('#margin').inputValue(),'6');
    await page.selectOption('#margin','0');
    await page.uncheck('#showArms');
    const canvas=page.locator('#canvas');
    const save=key=>page.evaluate(key=>{window[key]=document.querySelector('#canvas').getContext('2d').getImageData(0,0,480,512).data.slice();},key);
    const different=key=>page.evaluate(key=>{const a=window[key], b=document.querySelector('#canvas').getContext('2d').getImageData(0,0,480,512).data;let n=0;for(let i=0;i<a.length;i+=4)if(Math.max(...[0,1,2,3].map(j=>Math.abs(a[i+j]-b[i+j])))>2)n++;return n;},key);
    // Chromium can differ by one RGB level when switching render backends;
    // count changes over two levels rather than treating that as a brush edit.
    await save('_original');
    await page.check('#showMask'); assert((await different('_original'))>1000);
    await page.uncheck('#showMask'); assert.strictEqual(await different('_original'),0);
    async function stroke(points){
      await page.evaluate(()=>window.scrollTo(0,0));
      await page.locator('#canvasWrap').evaluate(el=>{el.scrollTop=0;el.scrollLeft=0;});
      const box=await canvas.boundingBox();
      const pos=([x,y])=>({x:box.x+box.width*x/480,y:box.y+box.height*y/512});
      let p=pos(points[0]);await page.mouse.move(p.x,p.y);await page.mouse.down();
      for(const pt of points.slice(1)){p=pos(pt);await page.mouse.move(p.x,p.y,{steps:3});}
      await page.mouse.up();
    }
    await page.locator('#color').fill('#f8f5fa');
    await page.locator('#size').fill('12');
    await stroke([[145,50],[152,70],[147,105],[135,145],[128,172],[130,185]]);
    assert((await different('_original'))>20); await save('_painted');
    await page.click('#undo');assert.strictEqual(await different('_original'),0);
    await page.click('#redo');assert.strictEqual(await different('_painted'),0);
    // Cancel a second gesture; it must not be added to the history or image.
    await page.evaluate(()=>window.scrollTo(0,0));
    let box=await canvas.boundingBox();await page.mouse.move(box.x+310*box.width/480,box.y+90*box.height/512);await page.mouse.down();
    await page.mouse.move(box.x+320*box.width/480,box.y+120*box.height/512);
    await canvas.dispatchEvent('pointercancel',{pointerId:1});await page.mouse.up();
    assert.strictEqual(await different('_painted'),0);
    // Test coordinate conversion at a different CSS scale.
    await page.selectOption('#zoom','1.5'); await canvas.scrollIntoViewIfNeeded();
    await stroke([[315,50],[307,70],[313,105],[325,145],[332,172],[330,185]]);
    assert((await different('_painted'))>20);await save('_both');
    page.once('dialog', d=>d.dismiss()); await page.click('#demo');
    assert.strictEqual(await different('_both'),0,'canceling reload must retain edits');
    await page.click('#undo');assert.strictEqual(await different('_painted'),0);
    await page.click('#redo');assert.strictEqual(await different('_both'),0);
    await page.selectOption('#margin','6'); assert((await different('_both'))>20);
    await page.selectOption('#margin','0'); assert.strictEqual(await different('_both'),0,'margin must not erase hidden strokes');
    await page.selectOption('#margin','6'); // export the stricter, independently verified patch
    await page.selectOption('#zoom','1');
    await page.locator('#canvasWrap').evaluate(el=>{el.scrollTop=0;el.scrollLeft=0;});
    await page.screenshot({path:path.join(out,'underpaint.png'),fullPage:true});
    const [download]=await Promise.all([page.waitForEvent('download'),page.click('#download')]);
    await download.saveAs(path.join(out,'underpaint-patch.png'));
    await page.check('#showArms');await page.locator('#leftAngle').fill('2');await page.locator('#rightAngle').fill('-2');
    await page.screenshot({path:path.join(out,'preview-rotated.png'),fullPage:true});
    await save('_beforeInvalid');
    await page.locator('#bodyFile').setInputFiles({name:'fake.png',mimeType:'image/png',buffer:Buffer.from('not a png')});
    await page.locator('#leftFile').setInputFiles('experiments/live2d_chibi_dynamic/sprites/arm_l.png');
    await page.locator('#rightFile').setInputFiles('experiments/live2d_chibi_dynamic/sprites/arm_r.png');
    page.once('dialog', d=>d.accept()); await page.click('#loadFiles');
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('载入失败'));
    assert.strictEqual(await different('_beforeInvalid'),0,'failed import must retain current work');
    assert.deepStrictEqual(errors,[]);
    console.log('Chromium 遮挡工作台：载入、受限补画、取消、撤销/重做、缩放坐标、导出通过');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
