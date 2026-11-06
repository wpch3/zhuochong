/* Local-only zrig authoring prototype. Never writes back to a server. */
'use strict';
const $ = id => document.getElementById(id);
let session = null;
const status = message => { $('status').textContent = message; };
const viewport = new ZRigViewport.Viewport($('viewport'), (id, pos, layer) => {
  run(() => session.setPart(id, Math.round(pos[0] * 100) / 100, Math.round(pos[1] * 100) / 100, layer), '部件位置已更新，可撤销。');
}, message => { $('canvasStatus').textContent = message; });
function number(id) {
  const text = $(id).value.trim();
  if (!text) throw new Error('数值不能为空');
  const n = Number(text);
  if (!Number.isFinite(n)) throw new Error('数值必须有限');
  return n;
}
function run(fn, message) {
  try { fn(); render(); status(message); } catch (error) { status('操作失败：' + error.message); }
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
  viewport.setSelection(p ? p.id : null);
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
function render() {
  $('work').hidden = !session;
  $('download').disabled = !session;
  $('undo').disabled = !session || !session.history.length;
  $('redo').disabled = !session || !session.future.length;
  if (!session) return;
  viewport.setRig(session.rig, false);
  options($('part'), session.rig.parts.filter(p => p && typeof p.id === 'string').map(p => [p.id, p.id]));
  options($('param'), session.rig.params.filter(p => p && typeof p.id === 'string').map(p => [p.id, (p.label || p.id) + ' · ' + p.id]));
  options($('group'), Object.keys(session.rig.groups).map(id => [id, id]));
  showPart(); showBindings();
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
$('param').addEventListener('change', showBindings);
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
