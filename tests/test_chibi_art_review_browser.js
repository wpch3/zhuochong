/* Optional live Chromium check for the isolated natural eye candidate. */
'use strict';
const assert=require('assert');
const {chromium}=require('playwright-core');
const mod=require('@sparticuz/chromium'),pkg=mod.default||mod;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:await pkg.executablePath(),args:pkg.args});
 try{
  const page=await browser.newPage({viewport:{width:1360,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(process.env.ZCHIBI_ART_PREVIEW||'http://127.0.0.1:5258',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.title.includes('眼手关节美术试验'),null,{timeout:10000});
  const specs=[['左小指（试验）','ParamFingerLLittle',.7,0],['右拇指（试验）','ParamFingerRThumb',-.8,0],['左肘（试验）','ParamElbowL',.6,0],['眼球横向（试验）','ParamGazeX',.8,0],['左眼开度（试验）','ParamEyeLOpen',.15,1],['右笑眼（试验）','ParamEyeRSmile',.85,0]];
  for(const [label,id,v] of specs){
   const el=page.getByLabel(label,{exact:true});await el.waitFor();
   await el.evaluate((e,v)=>{e.value=String(v);e.dispatchEvent(new Event('input',{bubbles:true}));},v);
   await page.waitForFunction(async([id,v])=>{const p=(await (await fetch('/api/params.json')).json()).params;return Math.abs(p.find(x=>x.id===id).value-v)<.001},[id,v],{timeout:10000});
  }
  await page.getByRole('button',{name:'静止并复位'}).click();
  await page.waitForFunction(async(expected)=>{const p=(await (await fetch('/api/params.json')).json()).params;return expected.every(([id,v])=>Math.abs(p.find(x=>x.id===id).value-v)<.001)},specs.map(x=>[x[1],x[3]]),{timeout:10000});
  await page.getByRole('button',{name:'手指小摆（试验）'}).click();
  await page.waitForFunction(async()=> (await (await fetch('/api/info.json')).json()).action==='finger_test',null,{timeout:10000});
  assert.deepStrictEqual(errors,[]);
  await page.evaluate(async()=>{await fetch('/api/param?all=1');await fetch('/api/action?id=idle');await fetch('/api/blink?v=auto');await fetch('/api/pause?on=0')});
  console.log('真实 Chromium：眼开度、笑眼、眼球与手指控件、复位及试验动作通过');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
