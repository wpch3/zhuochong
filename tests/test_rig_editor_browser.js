/* Optional real Chromium end-to-end: see rig_editor/README.md for dependencies. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const http = require('http');
const {chromium} = require('playwright-core');
const chromiumModule = require('@sparticuz/chromium');
const chromiumPackage = chromiumModule.default || chromiumModule;
const root = path.resolve('tools/rig_editor');
const out = path.resolve(process.env.ZRIG_BROWSER_QA || 'build/browser-editor-qa');
const server = http.createServer((req,res) => {
  let url;
  try { url = decodeURIComponent(new URL(req.url, 'http://localhost').pathname); } catch { res.writeHead(400).end(); return; }
  const file = path.resolve(root, '.' + (url === '/' ? '/index.html' : url));
  if (!file.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file,(err,data) => {
    if (err) {res.writeHead(404).end(); return;}
    const ext=path.extname(file); res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json','.png':'image/png'})[ext] || 'application/octet-stream');
    res.end(data);
  });
});
(async () => {
  fs.mkdirSync(out,{recursive:true});
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const browser = await chromium.launch({headless:true, executablePath:await chromiumPackage.executablePath(), args:chromiumPackage.args});
  try {
    const page = await browser.newPage({viewport:{width:1280,height:1000},deviceScaleFactor:1});
    const errors = []; page.on('pageerror', e => errors.push(String(e)));
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.click('#demo');
    await page.waitForFunction(() => document.querySelector('#canvasStatus').textContent.includes('示例贴图已载入'));
    await page.fill('#newId','ParamEditorHead'); await page.fill('#newLabel','头部测试'); await page.click('#addParam');
    await page.selectOption('#param','ParamEditorHead'); await page.selectOption('#group','head');
    await page.fill('#scale','4'); await page.click('#addBind');
    await page.fill('#newId','ParamEditorMesh'); await page.fill('#newLabel','网格测试');
    await page.fill('#min','0'); await page.fill('#max','1'); await page.fill('#default','0'); await page.click('#addParam');
    await page.selectOption('#param','ParamEditorMesh'); await page.selectOption('#part','body');
    await page.fill('#meshId','editor_mesh'); await page.click('#addMesh');
    await page.selectOption('#mesh','editor_mesh'); await page.fill('#meshValue','1'); await page.check('#meshEdit');
    const canvas = page.locator('#viewport'); await canvas.scrollIntoViewIfNeeded();
    const box = await canvas.boundingBox(); assert(box);
    // Body origin (280,458), image 480x512: centre grid vertex is (520,714).
    const x = box.x + box.width * 520/1024, y = box.y + box.height * 714/1024;
    await page.mouse.move(x,y); await page.mouse.down(); await page.mouse.move(x+18,y+8,{steps:6}); await page.mouse.up();
    let mesh = JSON.parse(await page.locator('#meshDetails').textContent());
    const point = mesh.keys.find(k => k.v === 1).points.find(p => p.c === 1 && p.r === 1);
    assert(point && point.dx > 30 && point.dy > 10, JSON.stringify(mesh));
    await page.locator('.canvas-wrap').screenshot({path:path.join(out,'editor_canvas.png')});
    await page.click('#undo'); mesh = JSON.parse(await page.locator('#meshDetails').textContent());
    assert.strictEqual(mesh.keys.find(k => k.v === 1).points.length,0,'drag must be a single undo transaction');
    await page.click('#redo'); mesh = JSON.parse(await page.locator('#meshDetails').textContent());
    assert.strictEqual(mesh.keys.find(k => k.v === 1).points.length,1);
    // A canceled gesture must not commit a second edit.
    await canvas.scrollIntoViewIfNeeded();
    const movedBox = await canvas.boundingBox();
    const mx = movedBox.x + movedBox.width * (520+point.dx)/1024;
    const my = movedBox.y + movedBox.height * (714+point.dy)/1024;
    await page.mouse.move(mx,my); await page.mouse.down(); await page.mouse.move(mx+12,my+4);
    await canvas.dispatchEvent('pointercancel',{pointerId:1}); await page.mouse.up();
    mesh = JSON.parse(await page.locator('#meshDetails').textContent());
    assert.deepStrictEqual(mesh.keys.find(k => k.v === 1).points[0],point,'cancel must not commit');
    await page.screenshot({path:path.join(out,'editor_page.png'),fullPage:true});
    const [download] = await Promise.all([page.waitForEvent('download'),page.click('#download')]);
    await download.saveAs(path.join(out,'browser-rig.json'));
    assert.deepStrictEqual(errors,[]);
    console.log('真实 Chromium：载入、参数绑定、网格拖点、撤销/重做和下载通过；输出 '+out);
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode=1}).finally(() => server.close());
