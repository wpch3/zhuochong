/* tests/test_web.js —— 界面内核与组件的单测（node，无需浏览器）
 *
 * 为什么要这个：重构成"组件 + layout.json"之后，界面是**配置拼起来的**，
 * 配置写错、组件忘了注册、某个卡片 mount 抛异常，用肉眼看页面是看不出来的
 * （沙箱里也没有浏览器）。这里拿一个极简 DOM stub 把 app.js 和全部组件真正
 * 跑一遍：挂载、推一次 info、点一下按钮，断言 DOM 和发出去的请求都对。
 *
 * 跑法：node tests/test_web.js   （make web-test）
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const WEB = path.join(__dirname, "..", "web");
let pass = 0, fail = 0, section = "";
function SECTION(s) { section = s; console.log("== " + s + " =="); }
function CHECK(cond, msg) {
  if (cond) { pass++; }
  else { fail++; console.log("  [失败] " + section + ": " + msg); }
}

/* ------------------------------------------------------------ DOM stub */
function makeEl(tag) {
  const e = {
    tagName: String(tag).toUpperCase(),
    children: [], parent: null, _text: "", className: "", id: "",
    dataset: {}, style: { setProperty(k, v) { this[k] = v; } },
    hidden: false, value: "", src: "", href: "", title: "", type: "",
    attributes: {}, _handlers: {},
    appendChild(c) { c.parent = e; e.children.push(c); return c; },
    removeChild(c) { const i = e.children.indexOf(c); if (i >= 0) e.children.splice(i, 1); return c; },
    addEventListener(evt, fn) { (e._handlers[evt] = e._handlers[evt] || []).push(fn); },
    removeEventListener(evt, fn) {
      const a = e._handlers[evt] || []; const i = a.indexOf(fn); if (i >= 0) a.splice(i, 1);
    },
    dispatch(evt, arg) { (e._handlers[evt] || []).forEach((f) => f(arg || { target: e })); },
    getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 300 }; },
    setAttribute(k, v) { e.attributes[k] = v; if (k === "class") e.className = v; },
    getAttribute(k) { return e.attributes[k]; },
    get textContent() { return e._text; },
    set textContent(v) { e._text = String(v); e.children.length = 0; },
    get innerHTML() { return e._html || ""; },
    set innerHTML(v) { e._html = v; if (v === "") e.children.length = 0; },
    get classList() {
      return {
        add(c) { if (!e.className.split(/\s+/).includes(c)) e.className = (e.className + " " + c).trim(); },
        remove(c) { e.className = e.className.split(/\s+/).filter((x) => x && x !== c).join(" "); },
        contains(c) { return e.className.split(/\s+/).includes(c); },
      };
    },
    querySelectorAll(sel) { return walk(e).filter((n) => matches(n, sel)); },
    querySelector(sel) { return e.querySelectorAll(sel)[0] || null; },
  };
  return e;
}
function walk(root, out) {
  out = out || [];
  root.children.forEach((c) => { out.push(c); walk(c, out); });
  return out;
}
function matches(node, sel) {
  return String(sel).split(",").map((s) => s.trim()).some((s) => {
    if (s.startsWith(".")) return node.className.split(/\s+/).includes(s.slice(1));
    if (s.startsWith("#")) return node.id === s.slice(1);
    return node.tagName === s.toUpperCase();
  });
}
function textOf(node) {
  let t = node._text || "";
  node.children.forEach((c) => { t += textOf(c); });
  return t;
}

/* 加载过的脚本：script 元素一进 head 就同步读文件执行，再回调 onload。
   这样内核的"按 layout 动态加载组件"这条路是真的走了一遍。 */
const loadedScripts = [];
const ctx = {};
function makeDocument() {
  const doc = {
    readyState: "complete", hidden: false, title: "",
    documentElement: makeEl("html"),
    body: makeEl("body"),
    head: makeEl("head"),
    _byId: {},
    createElement(tag) {
      const e = makeEl(tag);
      if (tag === "script") {
        /* 关键：模拟浏览器"插进 head 就执行" */
        const origAppend = doc.head.appendChild;
        e._isScript = true;
      }
      return e;
    },
    getElementById(id) { return doc._byId[id] || null; },
    querySelectorAll(sel) { return walk(doc.body).filter((n) => matches(n, sel)); },
    querySelector(sel) { return doc.querySelectorAll(sel)[0] || null; },
    addEventListener() {},
  };
  doc.head.appendChild = function (c) {
    c.parent = doc.head; doc.head.children.push(c);
    if (c._isScript && c.src) {
      const f = path.join(WEB, c.src);
      loadedScripts.push(c.src);
      try {
        vm.runInContext(fs.readFileSync(f, "utf8"), doc._ctx || ctx, { filename: f });
        if (c.onload) c.onload();
      } catch (err) {
        console.log("  [脚本执行异常] " + c.src + " → " + err.message);
        if (c.onerror) c.onerror(err);
      }
    }
    return c;
  };
  return doc;
}

/* ------------------------------------------------------------ fetch stub */
const INFO = {
  action: "idle", mood: "joy", affection: 12, tier_name: "熟识", form: "teen",
  form_name: "少女", forms: ["teen"], form_names: ["少女"],
  outfit: "default", outfits: ["default"], outfit_names: ["常服"],
  scale: 0.75, actions: ["idle", "happy", "wave", "sleep"],
  expressions: [{ id: "smile", name: "微笑" }],
  deformers: { skirt_sway_x: 0.0 },
};
const calls = [];
function makeFetch() {
  return async function (url) {
    calls.push(String(url).split("?")[0]);
    const u = String(url);
    const json = (o) => ({
      ok: true, status: 200,
      headers: { get: () => "application/json" },
      json: async () => o, text: async () => JSON.stringify(o),
      blob: async () => ({ size: 1234 }),
    });
    if (u.startsWith("layout.json")) return json(JSON.parse(fs.readFileSync(path.join(WEB, "layout.json"), "utf8")));
    if (u.startsWith("themes/")) {
      const f = path.join(WEB, u.split("?")[0]);
      if (!fs.existsSync(f)) return { ok: false, status: 404, headers: { get: () => "" } };
      return json(JSON.parse(fs.readFileSync(f, "utf8")));
    }
    if (u.includes("/api/info.json")) return json(INFO);
    if (u.includes("/api/speech.json")) return json({ line: "" });
    if (u.includes("/voice_manifest.json")) {
      return json({ engine: "zh-CN-XiaoyiNeural", lines: [
        { id: "pat_1", text: "摸头好舒服", file: "a.mp3" },
        { id: "mood_1", text: "今天心情不错", file: "b.mp3" },
      ] });
    }
    if (u.includes("frame.png")) {
      return { ok: true, status: 200, headers: { get: () => "image/png" }, blob: async () => ({ size: 50000 }) };
    }
    return json({ ok: true });
  };
}

/* ------------------------------------------------------------ 建环境并启动 */
const timers = [];
const doc = makeDocument();
Object.assign(ctx, {
  console, document: doc, fetch: makeFetch(),
  URLSearchParams, URL: { createObjectURL: () => "blob:x", revokeObjectURL() {} },
  performance: { now: () => Date.now() },
  setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
  clearTimeout: () => {}, setInterval: (fn, ms) => { timers.push({ fn, ms, repeat: true }); return 0; },
  clearInterval: () => {}, alert: () => {},
  Date, Math, JSON, Set, Map, Object, Array, String, Number, Boolean, Error, Promise, isNaN, parseInt, parseFloat,
  ZC_NO_AUTOBOOT: true,
});
ctx.window = ctx;
ctx.globalThis = ctx;
vm.createContext(ctx);

/* 页面上的区域容器（和 index.html 保持一致） */
["topbar", "stage", "side", "footer"].forEach((r) => {
  const d = makeEl("div");
  d.id = "region-" + r;
  doc.body.appendChild(d);
  doc._byId[d.id] = d;
});

vm.runInContext(fs.readFileSync(path.join(WEB, "app.js"), "utf8"), ctx, { filename: "app.js" });
const ZC = ctx.ZC;

/* 取某个组件的插槽；没挂上就判失败并返回一个空壳，别让整个测试崩掉 */
function slotOf(id) {
  const m = ZC.mounted.find((x) => x.def.id === id);
  if (!m) { CHECK(false, "组件 " + id + " 没有挂载，后面针对它的检查无法进行"); return makeEl("div"); }
  return m.el;
}

(async function main() {
  SECTION("内核：注册表与事件总线");
  CHECK(!!ZC && typeof ZC.register === "function", "app.js 应导出 ZC.register");
  CHECK(typeof ZC.boot === "function", "app.js 应导出 ZC.boot");
  {
    let threw = false;
    try { ZC.register({ id: "", mount() {} }); } catch (e) { threw = true; }
    CHECK(threw, "没有 id 的组件必须被拒绝");
    threw = false;
    try { ZC.register({ id: "zz_nomount" }); } catch (e) { threw = true; }
    CHECK(threw, "没有 mount() 的组件必须被拒绝");
    ZC.register({ id: "zz_dup", mount() {} });
    threw = false;
    try { ZC.register({ id: "zz_dup", mount() {} }); } catch (e) { threw = true; }
    CHECK(threw, "重复 id 必须被拒绝（否则后注册的会悄悄顶掉前一个）");
  }
  {
    const bus = ZC.bus;
    let got = 0, other = 0;
    const off = bus.on("t_evt", () => { got++; });
    bus.on("t_evt", () => { throw new Error("故意抛"); });
    bus.on("t_evt", () => { other++; });
    bus.emit("t_evt", {});
    CHECK(got === 1 && other === 1, "一个订阅者抛异常，别的订阅者照样要收到（实际 " + got + "/" + other + "）");
    off();
    bus.emit("t_evt", {});
    CHECK(got === 1, "退订之后不该再收到（实际 " + got + "）");
  }

  SECTION("启动：按 layout.json 组装界面");
  await ZC.boot();
  const layout = JSON.parse(fs.readFileSync(path.join(WEB, "layout.json"), "utf8"));
  const wanted = [];
  Object.keys(layout.regions).forEach((rk) => {
    layout.regions[rk].forEach((it) => wanted.push(typeof it === "string" ? it : it.id));
  });
  CHECK(loadedScripts.length === wanted.length,
        "layout 里每个组件都应被动态加载（要 " + wanted.length + " 个，实际 " + loadedScripts.length + "）");
  CHECK(ZC.mounted.length === wanted.length,
        "每个组件都应挂载成功（要 " + wanted.length + " 个，实际 " + ZC.mounted.length + "）");
  const errs = walk(doc.body).filter((n) => n.className === "err");
  CHECK(errs.length === 0, "不应有组件挂载失败（实际 " + errs.length + " 个 .err：" +
        errs.map((e) => e._text).join(" / ") + "）");

  /* 区域归属：每个组件的 DOM 必须落在 layout 指定的那个区域里 */
  let misplaced = 0;
  Object.keys(layout.regions).forEach((rk) => {
    const region = doc.getElementById("region-" + rk);
    const ids = layout.regions[rk].map((it) => (typeof it === "string" ? it : it.id));
    const inRegion = walk(region).filter((n) => n.dataset && n.dataset.component)
                                 .map((n) => n.dataset.component);
    ids.forEach((id) => { if (!inRegion.includes(id)) misplaced++; });
  });
  CHECK(misplaced === 0, "每个组件都应挂在 layout 指定的区域里（错位 " + misplaced + " 个）");

  /* 顺序：side 区的 DOM 顺序要和配置一致 */
  {
    const side = doc.getElementById("region-side");
    const order = side.children.map((c) => c.dataset.component);
    const want = layout.regions.side.map((it) => (typeof it === "string" ? it : it.id));
    CHECK(JSON.stringify(order) === JSON.stringify(want),
          "side 区顺序应与 layout 一致（配置 " + want.join(",") + " / 实际 " + order.join(",") + "）");
  }

  SECTION("主题：JSON 里的变量要真写到 :root 上");
  {
    const st = doc.documentElement.style;
    CHECK(st["--pink"] === "#ff9ec2", "默认主题 sakura 的 --pink 应写入（实际 " + st["--pink"] + "）");
    await ZC.host.setTheme("dusk");
    CHECK(st["--card"] === "#242734", "切到 dusk 后 --card 应变（实际 " + st["--card"] + "）");
    CHECK(ZC.host.theme().id === "dusk", "host.theme() 应报告当前主题");
    await ZC.host.setTheme("sakura");
    CHECK(st["--card"] === "#fffdfd", "切回 sakura 应恢复（实际 " + st["--card"] + "）");
    const before = ZC.host.theme().id;
    await ZC.host.setTheme("__not_exist__");
    CHECK(doc.documentElement.style["--card"] === "#fffdfd",
          "主题文件不存在时不该把已生效的变量抹掉");
  }

  SECTION("组件：推一次 info 后各自要更新");
  ZC.bus.emit("info", INFO);
  {
    const chips = ZC.host.find("statuschips");
    const box = slotOf("statuschips");
    const texts = walk(box).map((n) => n._text).filter(Boolean);
    CHECK(texts.some((t) => t.includes("idle")), "状态条应显示动作（实际 " + texts.join(" | ") + "）");
    CHECK(texts.some((t) => t.includes("熟识")), "状态条应显示好感档位");
    CHECK(texts.some((t) => t.includes("少女")), "状态条应显示形态名");
  }
  {
    const el = slotOf("actions");
    const btns = walk(el).filter((n) => n.tagName === "BUTTON");
    CHECK(btns.length === INFO.actions.length,
          "动作按钮数应等于引擎给的动作数（要 " + INFO.actions.length + "，实际 " + btns.length + "）");
    CHECK(btns.some((b) => b._text === "挥手"), "已知 id 应显示中文名（wave → 挥手）");
    /* 引擎新增的未知动作也要能出现（名字回落成 id） */
    ZC.bus.emit("info", Object.assign({}, INFO, { actions: INFO.actions.concat(["brand_new"]) }));
    const again = walk(el).filter((n) => n.tagName === "BUTTON");
    CHECK(again.length === INFO.actions.length,
          "动作列表只建一次，不该每次 info 都重建（实际 " + again.length + "）");
  }
  {
    const el = slotOf("appearance");
    const sels = walk(el).filter((n) => n.tagName === "SELECT");
    CHECK(sels.length === 2, "形态卡应有形态/服装两个下拉（实际 " + sels.length + "）");
    CHECK(sels[0].children.length === 1 && sels[0].children[0]._text.includes("少女"),
          "形态下拉应按引擎给的名字填充");
    const mono = walk(el).filter((n) => n.className === "mono")[0];
    CHECK(mono && mono._text === "0.75", "缩放数值应跟随 info（实际 " + (mono && mono._text) + "）");
  }

  SECTION("组件：点按钮要发对请求");
  {
    const el = slotOf("actions");
    const btn = walk(el).filter((n) => n.tagName === "BUTTON").find((b) => b._text === "挥手");
    calls.length = 0;
    btn.dispatch("click");
    await new Promise((r) => setImmediate(r));
    CHECK(calls.includes("/api/action"), "点动作按钮应调 /api/action（实际 " + calls.join(",") + "）");
    CHECK(btn.classList.contains("active"), "点过的按钮应高亮");
  }
  {
    const el = slotOf("moods");
    const btn = walk(el).filter((n) => n.tagName === "BUTTON")[0];
    calls.length = 0;
    btn.dispatch("click");
    await new Promise((r) => setImmediate(r));
    CHECK(calls.includes("/api/express"), "点情绪按钮应调 /api/express（实际 " + calls.join(",") + "）");
  }
  {
    /* 立绘点击：坐标要按显示尺寸换算成帧坐标，不能原样提交 */
    const el = slotOf("stage");
    const img = walk(el).filter((n) => n.tagName === "IMG")[0];
    CHECK(!!img, "舞台应有立绘 img");
    const seen = [];
    const realFetch = ctx.fetch;
    ctx.fetch = async (u) => { seen.push(String(u)); return realFetch(u); };
    img.dispatch("click", { clientX: 50, clientY: 150, target: img });
    await new Promise((r) => setImmediate(r));
    ctx.fetch = realFetch;
    const poke = seen.find((u) => u.includes("/api/poke"));
    CHECK(!!poke, "点立绘应调 /api/poke（实际 " + seen.join(",") + "）");
    if (poke) {
      const q = new URLSearchParams(poke.split("?")[1]);
      /* 显示 100x300，naturalWidth 兜底 445x1292：点 (50,150) → 正中间 */
      CHECK(Math.abs(Number(q.get("x")) - 222) < 3 && Math.abs(Number(q.get("y")) - 646) < 5,
            "点击坐标应按显示比例换算成帧坐标（实际 x=" + q.get("x") + " y=" + q.get("y") + "）");
    }
  }

  SECTION("组件：语音与用量");
  {
    const el = slotOf("voice");
    const items = walk(el).filter((n) => n.className === "voice-item");
    CHECK(items.length === 2, "语音清单应渲染两条（实际 " + items.length + "）");
    const tag = walk(el).filter((n) => n.className === "tag")[0];
    CHECK(tag && tag._text.includes("Xiaoyi"), "应显示引擎名（实际 " + (tag && tag._text) + "）");
    const usageEl = slotOf("usage");
    const before = ZC.host.state.usage.tokens;
    items[0].dispatch("click");
    await new Promise((r) => setImmediate(r));
    CHECK(ZC.host.state.usage.tokens > before,
          "播一条台词应累加 token（" + before + " → " + ZC.host.state.usage.tokens + "）");
    const meter = walk(usageEl).filter((n) => n.className === "meter-fill")[0];
    CHECK(meter && meter.style.width && meter.style.width !== "0.0%",
          "用量条应随之变长（实际 " + (meter && meter.style.width) + "）");
  }

  SECTION("容错：布局写错不该让整个界面白屏");
  {
    /* 另起一套环境，layout 里塞一个不存在的组件 */
    const doc2 = makeDocument();
    const ctx2 = Object.assign({}, ctx, { document: doc2, ZC_NO_AUTOBOOT: true });
    delete ctx2.ZC;                       /* 不继承上一套的注册表，否则组件会报"id 重复" */
    doc2._ctx = ctx2;
    ctx2.window = ctx2; ctx2.globalThis = ctx2;
    ctx2.fetch = async (url) => {
      const u = String(url);
      if (u.startsWith("layout.json")) {
        return { ok: true, status: 200, headers: { get: () => "application/json" },
                 json: async () => ({ theme: "sakura", regions: { side: ["moods", "no_such_card"] } }) };
      }
      return ctx.fetch(url);
    };
    vm.createContext(ctx2);
    ["topbar", "stage", "side", "footer"].forEach((r) => {
      const d = makeEl("div"); d.id = "region-" + r;
      doc2.body.appendChild(d); doc2._byId[d.id] = d;
    });
    vm.runInContext(fs.readFileSync(path.join(WEB, "app.js"), "utf8"), ctx2, { filename: "app.js" });
    await ctx2.ZC.boot();
    const side2 = doc2.getElementById("region-side");
    const mountedOk = walk(side2).filter((n) => n.dataset && n.dataset.component).length;
    const errs2 = walk(side2).filter((n) => n.className === "err");
    CHECK(mountedOk >= 1, "正常的组件仍要挂上（实际 " + mountedOk + "）");
    CHECK(errs2.length === 1, "缺失的组件应就地显示错误而不是整页崩（实际 " + errs2.length + "）");
    CHECK(errs2.length && errs2[0]._text.includes("no_such_card"), "错误里应点名是哪个组件");
  }

  console.log("");
  console.log(fail === 0
    ? "通过 " + pass + " 项，失败 0 项"
    : "通过 " + pass + " 项，失败 " + fail + " 项");
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
