/* Lightweight DOM/canvas integration test, no real browser or GPU. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const ids = ['file','demo','undo','redo','download','status','work','part','x','y','layer','savePart','newId','newLabel','min','max','default','addParam','param','group','channel','scale','offset','addBind','bindings','assetFiles','viewport','canvasStatus','meshId','meshCols','meshRows','mesh','meshValue','meshEdit','meshC','meshR','meshDx','meshDy','addMesh','setMeshPoint','meshDetails','partGroup','savePartGroup','newGroupId','newGroupParent','newGroupX','newGroupY','addGroup','editGroup','editGroupParent','groupX','groupY','saveGroup'];
const ctx2d = {clearRect(){}, save(){}, restore(){}, translate(){}, rotate(){}, drawImage(){}, setLineDash(){}, strokeRect(){}, beginPath(){}, arc(){}, fill(){}, moveTo(){}, lineTo(){}, stroke(){}};
class Element {
  constructor(id) { this.id=id; this.value=''; this.children=[]; this.handlers={}; this.hidden=false; this.disabled=false; this.textContent=''; this.width=0; this.height=0; }
  addEventListener(event, fn) { this.handlers[event]=fn; }
  appendChild(child) { this.children.push(child); if (!this.value && child.value) this.value=child.value; return child; }
  replaceChildren() { this.children=[]; this.value=''; }
  getContext(){return ctx2d}
  getBoundingClientRect(){return {left:0,top:0,width:1024,height:1024}}
  setPointerCapture(){}
  click(){ if (this.handlers.click) return this.handlers.click({target:this}); }
}
const elements = Object.fromEntries(ids.map(id => [id,new Element(id)]));
for (const [id,value] of Object.entries({min:'-1',max:'1',default:'0',scale:'1',offset:'0',channel:'rot_deg'})) elements[id].value=value;
const doc = {getElementById(id){return elements[id]}, createElement(){return new Element('created')}};
class MockImage { constructor(){this.width=480;this.height=512} set src(s){this._src=s; queueMicrotask(() => this.onload())} }
const fixture = JSON.parse(fs.readFileSync('tools/rig_editor/demo.json', 'utf8'));
const context = vm.createContext({document:doc, Image:MockImage, Blob, URL:{createObjectURL(){return 'blob:test'},revokeObjectURL(){}},
  setTimeout, console, fetch:async () => ({ok:true,json:async () => fixture})});
for (const file of ['core.js','viewport.js','app.js']) vm.runInContext(fs.readFileSync('tools/rig_editor/'+file,'utf8'), context, {filename:file});
(async () => {
  await elements.demo.click();
  assert.strictEqual(elements.work.hidden,false);
  assert(elements.status.textContent.includes('黑描边'));
  assert(elements.canvasStatus.textContent.includes('示例贴图已载入'));
  assert.strictEqual(elements.part.value,'body');
  assert.strictEqual(elements.x.value,280);
  elements.x.value='312'; elements.y.value='460'; elements.layer.value='10';
  elements.savePart.click(); assert.strictEqual(elements.x.value,312);
  elements.undo.click(); assert.strictEqual(elements.x.value,280);
  elements.redo.click(); assert.strictEqual(elements.x.value,312);
  elements.newGroupId.value='ui_bone'; elements.newGroupParent.value='head'; elements.newGroupX.value='512'; elements.newGroupY.value='400'; elements.addGroup.click();
  assert(elements.editGroup.children.some(c=>c.value==='ui_bone'));
  elements.part.value='nose'; elements.part.handlers.change(); elements.partGroup.value='ui_bone'; elements.savePartGroup.click();
  assert.strictEqual(elements.partGroup.value,'ui_bone'); elements.undo.click(); assert.strictEqual(elements.partGroup.value,'head'); elements.redo.click();
  elements.newId.value='ParamUIHead'; elements.newLabel.value='测试'; elements.addParam.click();
  assert(elements.param.children.some(c => c.value==='ParamUIHead'));
  elements.param.value='ParamUIHead'; elements.group.value='head'; elements.scale.value='4'; elements.addBind.click();
  assert(elements.bindings.children[0].children[0].textContent.includes('rot_deg'));
  elements.meshId.value='mesh_ui'; elements.meshCols.value='2'; elements.meshRows.value='2'; elements.addMesh.click();
  assert(elements.meshDetails.textContent.includes('mesh_ui'));
  elements.meshValue.value='1'; elements.meshC.value='0'; elements.meshR.value='0'; elements.meshDx.value='12'; elements.meshDy.value='0'; elements.setMeshPoint.click();
  assert(elements.meshDetails.textContent.includes('"dx": 12'));
  elements.undo.click(); assert(!elements.meshDetails.textContent.includes('"dx": 12'));
  console.log('zrig 编辑器 UI：载入图层、位置撤销/重做及参数绑定通过（模拟 DOM）');
})().catch(e => {console.error(e); process.exitCode=1});
