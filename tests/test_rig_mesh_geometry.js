/* Compare the static editor grid against real C vertex coordinates for
   isolated, unweighted meshes with no active group transforms. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {execFileSync} = require('child_process');
const view = require('../tools/rig_editor/viewport.js');
const rig = JSON.parse(fs.readFileSync('tools/rig_editor/qa/browser_rig.json','utf8'));
const mesh = rig.deformers.find(d => d.id === 'editor_mesh');
const body = rig.parts.find(p => p.id === 'body');
const image = {width:480,height:512};
const temp = fs.mkdtempSync(path.join(os.tmpdir(),'zrig-geometry-'));
try {
  for (const transform of [
    {pos:[280,458],anchor:[0,0],scale:1,rot_deg:0},
    {pos:[300,350],anchor:[.5,.5],scale:[1.3,.7],rot_deg:37}
  ]) {
    Object.assign(body, transform);
    const rigPath = path.join(temp,'rig.json'); fs.writeFileSync(rigPath,JSON.stringify(rig));
    const rows = execFileSync('./build/rig_mesh_probe',[rigPath,path.resolve('tools/rig_editor/demo')],{encoding:'utf8'}).trim().split('\n').map(line => line.split(' ').map(Number));
    const a = view.meshPoints(body,image,rig,mesh,0)[4];
    const b = view.meshPoints(body,image,rig,mesh,1)[4];
    assert.strictEqual(rows.length,3);
    for (const [value,x,y] of rows) {
      const wantX = a.x + (b.x-a.x)*value, wantY = a.y + (b.y-a.y)*value;
      assert(Math.abs(x-wantX)<1e-7 && Math.abs(y-wantY)<1e-7, `C ${value} (${x},${y}) vs editor (${wantX},${wantY})`);
    }
  }
  console.log('网格坐标：浏览器导出关键点与 C 引擎在平移/分轴缩放/旋转及中间态一致（无组变换）');
} finally { fs.rmSync(temp,{recursive:true,force:true}); }
