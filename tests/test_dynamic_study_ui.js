/* Exercise asynchronous input coalescing/reset/error paths without a browser. */
'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
let component;
vm.runInNewContext(fs.readFileSync('web/components/dynamic_study.js','utf8'), {
  ZC: {register(value) { component = value; }},
});
function el(tag, cls, text) {
  return {tag, cls, textContent: text || '', children: [], attributes: {},
    appendChild(child) { this.children.push(child); },
    addEventListener(name, fn) { this[name] = fn; },
    setAttribute(name, value) { this.attributes[name] = value; }};
}
const calls = [];
let resume;
let first = true;
let fail = false;
const host = {
  el,
  card() { const box = el('div'), body = el('div'); box.appendChild(body); return {box, body}; },
  async api(url, params) {
    calls.push({url, params: {...params}});
    if (first) { first = false; await new Promise(resolve => {resume = resolve;}); }
    if (fail) { fail = false; throw new Error('offline'); }
  },
  refresh() {},
};
const root = el('root'); component.mount(host, root);
const body = root.children[0].children[0];
const reset = body.children[1];
const slider = (label) => body.children.flatMap(row => row.children || [])
  .find(child => child.attributes && child.attributes['aria-label'] === label);
const left = slider('左侧袖手'), right = slider('右侧袖手');
const state = body.children[body.children.length-1];
const flush = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  left.value = '0.3'; left.input();
  right.value = '0.4'; right.input();
  right.value = '0.9'; right.input();
  reset.click(); // supersedes unsent right and the old left value
  left.value = '0.8'; left.input();
  resume();
  for (let i=0; i<10; i++) await flush();
  const paramCalls = calls.filter(c => c.url === '/api/param');
  assert.deepStrictEqual(paramCalls.map(c => c.params), [{all:1}, {id:'ParamArmL',v:0.8}]);
  assert.strictEqual(state.textContent, '静止检查模式');
  assert.strictEqual(right.value, '0');
  fail = true;
  left.value = '0.6'; left.input();
  for (let i=0; i<5; i++) await flush();
  assert(state.textContent.includes('offline'), 'errors must be visible');
  left.value = '-0.5'; left.input();
  for (let i=0; i<5; i++) await flush();
  assert.strictEqual(state.textContent, '静止检查模式', 'input should recover after error');
  assert.deepStrictEqual(calls.filter(c => c.url === '/api/param').pop().params, {id:'ParamArmL',v:-0.5});
  console.log('动态控制：在途合并、复位优先、错误提示与恢复通过');
})().catch(e => {console.error(e); process.exitCode=1;});
