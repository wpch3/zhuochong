/* Regression test for isolated face-study controls; no browser required. */
"use strict";
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");
let component;
vm.runInNewContext(fs.readFileSync("web/components/face_study.js", "utf8"), {
  ZC: { register(value) { component = value; } },
});
function el(tag, cls, text) {
  return { tag, cls, textContent: text || "", children: [],
    appendChild(child) { this.children.push(child); },
    addEventListener(name, cb) { this[name] = cb; } };
}
const calls = [];
let fail = false;
const host = { el, card() { return { body: el("div"), box: el("div") }; },
  async api(url) { calls.push(url); if (fail) throw new Error("offline"); },
  refresh() {} };
const root = el("root");
/* Preserve card body for this small stub, as a real card does. */
host.card = () => { const body = el("div"), box = el("div"); box.appendChild(body); return {body, box}; };
component.mount(host, root);
const customizedRoot = el("root");
component.mount(host, customizedRoot, {title: "表情控制", description: "Chibi 独立试装"});
assert.strictEqual(customizedRoot.children[0].children[0].children[0].textContent, "Chibi 独立试装");
const body = root.children[0].children[0];
const buttons = body.children[1].children;
(async () => {
  assert.strictEqual(buttons.length, 5);
  for (const button of buttons) await button.click();
  assert.deepStrictEqual(calls, ["/api/blink?v=0", "/api/blink?v=1", "/api/blink?v=auto",
                                "/api/param?id=ParamMouthOpenY&v=1", "/api/param?id=ParamMouthOpenY&v=0"]);
  fail = true;
  await buttons[0].click();
  assert(body.children[2].textContent.includes("offline"), "errors must be visible");
  console.log("面部试作控制：5 个按钮及错误提示通过");
})().catch(err => { console.error(err); process.exitCode = 1; });
