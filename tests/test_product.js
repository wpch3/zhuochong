/* T62.1 产品视图交互测试：用小型 DOM/fetch 替身实际执行 product.js。 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");
const WEB = path.join(__dirname, "..", "web");

class El {
  constructor(tag, id) {
    this.tagName = tag.toUpperCase(); this.id = id || ""; this.children = [];
    this.attrs = {}; this.dataset = {}; this.style = {}; this.handlers = {};
    this.hidden = false; this.value = ""; this.checked = false; this.disabled = false;
    this.open = false; this.className = ""; this.parent = null; this._text = "";
    this.classList = {
      add: (c) => { if (!this.className.split(/\s+/).includes(c)) this.className = (this.className + " " + c).trim(); },
      remove: (c) => { this.className = this.className.split(/\s+/).filter((x) => x && x !== c).join(" "); },
    };
  }
  append(...nodes) { nodes.forEach((n) => this.appendChild(n)); }
  appendChild(n) { n.parent = this; this.children.push(n); return n; }
  replaceChildren(...nodes) { this.children = []; nodes.forEach((n) => this.appendChild(n)); }
  addEventListener(name, fn) { (this.handlers[name] ||= []).push(fn); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  get textContent() { return this._text + this.children.map((n) => n.textContent).join(""); }
  set textContent(v) { this._text = String(v); this.children = []; }
  focus() { this.focused = true; }
  async fire(name, event = {}) {
    let result;
    for (const fn of this.handlers[name] || []) result = fn({ target: this, ...event });
    return result;
  }
}

async function main() {
  const ids = ["desktop-pet", "character", "conversation", "dock", "talk-toggle", "message", "send", "more", "options", "persona", "sensitive", "reset", "dry", "dry-output", "toast"];
  const elements = Object.fromEntries(ids.map((id) => [id, new El(id === "message" ? "textarea" : "div", id)]));
  elements.persona.checked = true;
  elements.options.hidden = true;
  elements["dry-output"].hidden = true;
  const copyNodes = ["persona", "sensitive", "reset", "dry"].map((key) => {
    const e = new El("span"); e.dataset.copy = key; return e;
  });
  const document = {
    title: "",
    createElement(tag) { return new El(tag); },
    getElementById(id) { return elements[id] || null; },
    querySelectorAll(sel) { return sel === "[data-copy]" ? copyNodes : []; },
    hidden: false,
  };
  const calls = [];
  const chats = [];
  let chatFailure = false;
  const copy = JSON.parse(fs.readFileSync(path.join(WEB, "product_copy.json"), "utf8"));
  const jsonResponse = (data, ok = true) => ({ ok, status: ok ? 200 : 502, json: async () => data });
  const fetch = async (url) => {
    calls.push(String(url));
    if (url === "product_copy.json") return jsonResponse(copy);
    if (String(url).startsWith("/api/chat?")) {
      const q = new URLSearchParams(String(url).split("?")[1]);
      chats.push(q);
      if (chatFailure) return jsonResponse({ ok: false, error: "本地模型不可用", reason: "sensitive_blocked", turns_held: 1 }, false);
      if (q.get("dry") === "1") return jsonResponse({
        ok: true, url: "http://127.0.0.1:11434/v1/chat/completions",
        request_body: "{\"model\":\"local-test\"}", reason: "default_local",
        local: true, history_sent: 2, turns_held: 1, persona_bytes: 128,
      });
      return jsonResponse({
        ok: true, text: "我在听。", provider: "ollama", model: "local-test",
        local: true, reason: "default_local", tokens_in: 12, tokens_out: 5,
        history_sent: 2, turns_held: 1, persona_bytes: 128,
      });
    }
    if (String(url).startsWith("/api/context.json?reset=1")) return jsonResponse({ ok: true });
    if (String(url).startsWith("/api/frame.png")) return { ok: true, blob: async () => ({ size: 4 }) };
    return jsonResponse({ ok: true });
  };
  /* 受控假定时器（与 test_web.js 同一思路）：零延时定时器在下个 tick 排空，
     正延时定时器（气泡寿命、33ms 帧轮询、12s 主动说话轮询）挂起不跑——
     单测只推进逻辑，不等真实时间，也不让递归帧循环拖住进程退出。
     T69.2 起 send() 要 await sleep(0) 等节奏，没有零延时通路它会永挂，
     Node 事件循环清空后进程静默 0 退出，20 条断言一条都不会执行。 */
  const timers = new Map();
  let timerSeq = 0;
  const context = {
    document, fetch, console,
    URLSearchParams,
    URL: { createObjectURL: () => "blob:test", revokeObjectURL: () => {} },
    setTimeout: (fn, ms) => { const id = ++timerSeq; timers.set(id, { fn, ms: Number(ms) || 0 }); return id; },
    clearTimeout: (id) => { timers.delete(id); },
    setInterval: (fn) => { const id = ++timerSeq; timers.set(id, { fn, repeat: true }); return id; },
    clearInterval: (id) => { timers.delete(id); },
  };
  vm.runInNewContext(fs.readFileSync(path.join(WEB, "product.js"), "utf8"), context, { filename: "product.js" });
  const tick = async () => {
    for (let round = 0; round < 8; round++) {
      await new Promise((r) => setImmediate(r));
      const due = [...timers.entries()].filter(([, t]) => !t.repeat && t.ms === 0);
      if (!due.length) break;
      for (const [id, t] of due) { if (timers.has(id)) { timers.delete(id); t.fn(); } }
    }
  };
  await tick();

  assert.strictEqual(document.title, copy.title, "文案加载后设置产品窗口标题");
  assert.strictEqual(elements.message.placeholder, copy.placeholder, "输入提示从文案数据加载");
  assert.strictEqual(elements.conversation.children[0].children[0].textContent, copy.welcome, "初始角色气泡显示欢迎语");

  elements.message.value = "嗨，小寻";
  /* send() 会等零延时节奏器，不能直接 await（永挂）；交给 tick 排空后再断言 */
  elements.send.fire("click").catch(() => {});
  await tick();
  assert.strictEqual(chats.length, 1, "发送操作向 /api/chat 发出一条请求");
  assert.strictEqual(chats[0].get("text"), "嗨，小寻", "发送原文不丢失");
  assert.strictEqual(chats[0].get("persona"), "1", "默认携带角色人设");
  assert.strictEqual(elements.message.value, "", "发送后清空输入框");
  const reply = elements.conversation.children[0];
  assert.strictEqual(reply.children[0].textContent, "我在听。", "回复作为角色气泡显示");
  const meta = reply.children[1].children[1].textContent;
  assert(meta.includes("没有需要上云的理由") && meta.includes("带入历史条数：2") && meta.includes("1 条隐私内容未带入云端"),
    "折叠详情用人话说明路由、多轮上下文与隐私保留");
  assert(calls.includes("/api/action?id=think") && calls.includes("/api/action?id=talk"), "发送和回复分别触发 think/talk 动作");

  elements.message.value = "预览请求";
  await elements.more.fire("click");
  assert.strictEqual(elements.options.hidden, false, "更多选项可展开");
  elements.dry.open = true;
  await elements.dry.fire("toggle");
  await tick();
  assert.strictEqual(chats.length, 2, "展开 dry-run 行会真的请求后端预演");
  assert.strictEqual(chats[1].get("dry"), "1", "预演请求带 dry=1，不会误发真聊天");
  assert(elements.conversation.children[0].textContent.includes(copy.dry_header), "预演结果在角色气泡中明确说明没有发送");
  assert(elements.conversation.children[0].textContent.includes("local-test"), "预演结果展示真实候选请求体");
  assert.strictEqual(elements["dry-output"].hidden, false, "展开选项后也能查看详细请求体");

  elements.sensitive.checked = true;
  elements.message.value = "只在本机处理";
  elements.send.fire("click").catch(() => {});
  await tick();
  assert.strictEqual(chats[2].get("sensitive"), "1", "隐私开关确实随聊天请求发送");

  chatFailure = true;
  elements.message.value = "隐私请求";
  elements.send.fire("click").catch(() => {});
  await tick();
  assert(elements.conversation.children[0].textContent.includes("本地模型不可用"), "上游拒绝要显示真实错误而不伪装成回复");
  assert(elements.conversation.children[0].textContent.includes("本机没有可用模型"), "隐私拦截原因必须用人话解释");

  await elements.reset.fire("click");
  await tick();
  assert(calls.some((u) => u === "/api/context.json?reset=1"), "重开对话清除服务端上下文");
  assert.strictEqual(elements.conversation.children[0].children[0].textContent, copy.reset_done, "清空后给出确认气泡");

  console.log("产品视图交互：通过 20 项，失败 0 项");
}

main().catch((err) => { console.error(err); process.exit(1); });
