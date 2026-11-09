/* Optional real Chromium against isolated joint and eye trials. */
'use strict';
const assert=require('assert'), fs=require('fs'), path=require('path');
const {chromium}=require('playwright-core');
const mod=require('@sparticuz/chromium'),pkg=mod.default||mod;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:await pkg.executablePath(),args:pkg.args});
 try{
  const page=await browser.newPage({viewport:{width:1360,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  for(const [url,isEye] of [[process.env.ZJOINT_PREVIEW||'http://127.0.0.1:5227',false],[process.env.ZEYE_PREVIEW||'http://127.0.0.1:5228',true]]){
   await page.goto(url,{waitUntil:'domcontentloaded'});
   await page.waitForFunction(text=>document.title.includes(text),isEye?'眼球重绘试验':'肘腕连接试验',{timeout:10000});
   const specs=[['左肘（试验）','ParamElbowL',.8],['右肘（试验）','ParamElbowR',-.7],['左手腕（试验）','ParamWristL',.6]];
   if(isEye) specs.push(['眼球横向（试验）','ParamGazeX',.9]);
   else assert.strictEqual(await page.getByLabel('眼球横向（试验）',{exact:true}).count(),0);
   for(const [label,id,v] of specs){
    const s=page.getByLabel(label,{exact:true});await s.waitFor();
    await s.evaluate((e,v)=>{e.value=String(v);e.dispatchEvent(new Event('input',{bubbles:true}));},v);
    await page.waitForFunction(async([id,v])=>{const p=(await (await fetch('/api/params.json')).json()).params;return Math.abs(p.find(x=>x.id===id).value-v)<.001;},[id,v],{timeout:10000});
   }
   const dir=path.resolve(process.env.ZJOINT_QA||'build/joint-browser-qa');fs.mkdirSync(dir,{recursive:true});
   await page.screenshot({path:path.join(dir,isEye?'eye_browser.png':'joint_browser.png'),fullPage:true});
   await page.getByRole('button',{name:'静止并复位'}).click();
   await page.waitForFunction(async(ids)=>{const p=(await (await fetch('/api/params.json')).json()).params;return ids.every(id=>Math.abs(p.find(x=>x.id===id).value)<.001);},specs.map(x=>x[1]),{timeout:10000});
   await page.getByRole('button',{name:'肘腕联动（试验）'}).click();
   await page.waitForFunction(async()=> (await (await fetch('/api/info.json')).json()).action==='elbow_test',null,{timeout:10000});
   assert.deepStrictEqual(errors,[]);
   await page.evaluate(async()=>{await fetch('/api/param?all=1');await fetch('/api/action?id=idle');await fetch('/api/blink?v=auto');await fetch('/api/pause?on=0');});
  }
  console.log('真实 Chromium：肘/腕/眼控、动作与复位通过');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
