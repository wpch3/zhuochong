/* Local-only zrig authoring prototype. Never writes back to a server. */
'use strict';
const $ = id => document.getElementById(id);
let session = null;
const status = message => { $('status').textContent = message; };
const viewport = new ZRigViewport.Viewport($('viewport'), (id, pos, layer) => {
  run(() => session.setPart(id, Math.round(pos[0] * 100) / 100, Math.round(pos[1] * 100) / 100, layer), '部件位置已更新，可撤销。');
}, message => { $('canvasStatus').textContent = message; }, (id, value, col, row, dx, dy) => {
  const round = n => Math.round(n * 100) / 100;
  if (run(() => session.setKeyformPoint(id, value, col, row, round(dx), round(dy)), '控制点已更新（一次可撤销事务）；贴图仍是静态近似。')) {
    $('meshC').value = col; $('meshR').value = row; $('meshDx').value = round(dx); $('meshDy').value = round(dy);
  }
}, (id, pos) => {
  const g = session.rig.groups[id];
  run(() => session.setGroup(id, g.parent || 'root', Math.round(pos[0] * 100) / 100, Math.round(pos[1] * 100) / 100), '枢轴已更新（一次可撤销）；静态连接不代表实际变形。');
});
function number(id) {
  const text = $(id).value.trim();
  if (!text) throw new Error('数值不能为空');
  const n = Number(text);
  if (!Number.isFinite(n)) throw new Error('数值必须有限');
  return n;
}
function run(fn, message) {
  try { fn(); render(); status(message); return true; } catch (error) { status('操作失败：' + error.message); return false; }
}
function load(rig) {
  const next = new ZRigEditor.Session(rig);
  viewport.setRig(next.rig, true); session = next;
  $('canvasStatus').textContent = '未加载贴图。';
  render(); status('已载入：' + (session.rig.name || session.rig.id || '未命名'));
}
function options(select, values, preferred) {
  const previous = preferred === undefined ? select.value : preferred;
  select.replaceChildren();
  values.forEach(([value, label]) => {
    const option = document.createElement('option'); option.value = value; option.textContent = label; select.appendChild(option);
  });
  if (values.some(([value]) => value === previous)) select.value = previous;
}
function showPart() {
  const p = session.rig.parts.find(p => p.id === $('part').value);
  $('x').value = p && Array.isArray(p.pos) ? p.pos[0] : 0;
  $('y').value = p && Array.isArray(p.pos) ? p.pos[1] : 0;
  $('layer').value = p && Number.isInteger(p.layer) ? p.layer : 0;
  $('savePart').disabled = !p || !!p.socket;
  $('savePartGroup').disabled = !p || !!p.socket;
  if (p) $('partGroup').value = p.group || 'root';
  viewport.setSelection(p ? p.id : null);
}
function showGroup() {
  const id = $('editGroup').value, g = session.rig.groups[id];
  $('groupX').value = g && Array.isArray(g.pivot) ? g.pivot[0] : 0;
  $('groupY').value = g && Array.isArray(g.pivot) ? g.pivot[1] : 0;
  $('editGroupParent').value = g && g.parent ? g.parent : 'root';
  $('saveGroup').disabled = !g || id === 'root';
  viewport.setGroup(id, $('groupEdit').checked);
}
function showBindings() {
  const list = $('bindings'); list.replaceChildren();
  const p = session.rig.params.find(item => item.id === $('param').value);
  const binds = p && Array.isArray(p.binds) ? p.binds : [];
  binds.forEach((bind, index) => {
    const li = document.createElement('li');
    const text = document.createElement('span'); text.textContent = JSON.stringify(bind); li.appendChild(text);
    const remove = document.createElement('button'); remove.textContent = '删除';
    remove.addEventListener('click', () => run(() => session.removeBind(p.id, index), '已删除绑定。'));
    li.appendChild(remove); list.appendChild(li);
  });
  if (!binds.length) { const li = document.createElement('li'); li.textContent = '该参数暂无绑定。'; list.appendChild(li); }
  $('addBind').disabled = !p || !$('group').value;
}
function showMesh() {
  const mesh = (session.rig.deformers || []).find(item => item.id === $('mesh').value && Array.isArray(item.keys));
  $('meshDetails').textContent = mesh ? JSON.stringify(mesh, null, 2) : '暂无单参数关键形态网格。';
  $('setMeshPoint').disabled = !mesh;
  const text = $('meshValue').value.trim();
  viewport.setMesh(mesh ? mesh.id : '', text ? Number(text) : NaN, $('meshEdit').checked);
}
function render() {
  $('work').hidden = !session;
  $('download').disabled = !session;
  $('undo').disabled = !session || !session.history.length;
  $('redo').disabled = !session || !session.future.length;
  if (!session) return;
  viewport.setRig(session.rig, false);
  options($('part'), session.rig.parts.filter(p => p && typeof p.id === 'string').map(p => [p.id, p.id]));
  options($('param'), session.rig.params.filter(p => p && typeof p.id === 'string').map(p => [p.id, (p.label || p.id) + ' · ' + p.id]));
  const groups = Object.keys(session.rig.groups);
  const choices = [...new Set(['root', ...groups])].map(id => [id, id]);
  options($('group'), groups.map(id => [id, id]));
  options($('partGroup'), choices); options($('newGroupParent'), choices);
  options($('editGroup'), groups.map(id => [id, id])); options($('editGroupParent'), choices);
  options($('mesh'), (Array.isArray(session.rig.deformers) ? session.rig.deformers : []).filter(d => d && typeof d.id === 'string' && Array.isArray(d.keys)).map(d => [d.id, d.id]));
  showPart(); showGroup(); showBindings(); showMesh();
}
$('file').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  try { load(JSON.parse(await file.text())); } catch (error) { status('读取失败：' + error.message); }
  event.target.value = '';
});
$('demo').addEventListener('click', async () => {
  try {
    const response = await fetch('demo.json'); if (!response.ok) throw new Error('示例不可用');
    load(await response.json()); await viewport.loadDemo();
  } catch (error) { status('读取失败：' + error.message); }
});
$('assetFiles').addEventListener('change', async event => {
  try { await viewport.loadFiles(event.target.files); }
  catch (error) { $('canvasStatus').textContent = '素材加载失败：' + error.message; }
  event.target.value = '';
});
$('part').addEventListener('change', showPart);
$('editGroup').addEventListener('change', showGroup);
$('groupEdit').addEventListener('change', () => { if ($('groupEdit').checked) $('meshEdit').checked = false; showGroup(); showMesh(); });
$('addGroup').addEventListener('click', () => run(() => session.addGroup($('newGroupId').value.trim(), $('newGroupParent').value, number('newGroupX'), number('newGroupY')), '骨骼组已添加；请用 C 引擎验证。'));
$('saveGroup').addEventListener('click', () => run(() => session.setGroup($('editGroup').value, $('editGroupParent').value, number('groupX'), number('groupY')), '组连接已更新；请用 C 引擎验证。'));
$('savePartGroup').addEventListener('click', () => run(() => session.setPartGroup($('part').value, $('partGroup').value), '部件已连接；请用 C 引擎验证。'));
$('param').addEventListener('change', showBindings);
$('mesh').addEventListener('change', showMesh);
$('meshValue').addEventListener('input', showMesh);
$('meshEdit').addEventListener('change', () => { if ($('meshEdit').checked) $('groupEdit').checked = false; showGroup(); showMesh(); });
$('addMesh').addEventListener('click', () => run(() => session.addKeyform($('meshId').value.trim(), $('part').value, $('param').value, number('meshCols'), number('meshRows')), '网格已新建；请填写关键形态控制点。'));
$('setMeshPoint').addEventListener('click', () => run(() => session.setKeyformPoint($('mesh').value, number('meshValue'), number('meshC'), number('meshR'), number('meshDx'), number('meshDy')), '关键形态控制点已更新；请导出并用 C 引擎验证。'));
$('savePart').addEventListener('click', () => run(() => session.setPart($('part').value, number('x'), number('y'), number('layer')), '部件位置已更新。'));
$('addParam').addEventListener('click', () => run(() => session.addParameter($('newId').value.trim(), $('newLabel').value, number('min'), number('max'), number('default')), '参数已添加。'));
$('addBind').addEventListener('click', () => run(() => session.addGroupBind($('param').value, $('group').value, $('channel').value, number('scale'), number('offset')), '绑定已添加。'));
$('undo').addEventListener('click', () => run(() => session.undo(), '已撤销。'));
$('redo').addEventListener('click', () => run(() => session.redo(), '已重做。'));
$('download').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([session.serialize()], {type: 'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = 'rig-edited.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000); status('已下载副本；不会自动覆盖模型。');
});
