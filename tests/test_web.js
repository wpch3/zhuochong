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
    /* 故意和 info.frame_w/h (466x748) 不一样：坐标换算用错 naturalWidth 立刻看得出来。
       真实情况也是这样 —— 图片尺寸 = 画布 × 画质档 s%，帧缓冲 = 画布 × pet scale。 */
    naturalWidth: 848, naturalHeight: 1360,
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
        /* 真浏览器有 toggle，stub 漏了它就会出现"组件在页面上好好的、测试里一跑就崩"
           （反过来更糟：组件为了迁就 stub 写得别扭）。补齐，口径同 DOM 规范。 */
        toggle(c, force) {
          const has = this.contains(c);
          const on = force === undefined ? !has : !!force;
          if (on) this.add(c); else this.remove(c);
          return on;
        },
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
/* 网关三种状态各给一个样本：能用 / 全关着 / 没接入。
   三条话术要分得开——统一说"不可用"的话用户不知道该做什么。 */
const GATEWAY = {
  loaded: true, strategy: "prefer_local", fallback: true, routes: 16,
  ledger: { spent: 1.2345, held: 0.5, tokens_in: 1200, tokens_out: 800, calls: 3, failed: 1 },
  caps: [
    { cap: "chat.completion", state: "ready", provider: "ollama", model: "qwen2.5:7b",
      local: true, free: true, candidates: 2 },
    { cap: "image.generate", state: "disabled", provider: "", model: "",
      local: false, free: false, candidates: 0 },
    { cap: "video.generate", state: "missing", provider: "", model: "",
      local: false, free: false, candidates: 0 },
  ],
};

const INFO = {
  action: "idle", mood: "joy", affection: 12, tier_name: "熟识", form: "teen",
  form_name: "少女", forms: ["teen"], form_names: ["少女"],
  outfit: "default", outfits: ["default"], outfit_names: ["常服"],
  scale: 0.75, actions: ["idle", "happy", "wave", "sleep"],
  expressions: [{ id: "smile", name: "微笑" }],
  deformers: { skirt_sway_x: 0.0 },
  /* 下面这些字段真服务都有。stub 漏字段的后果是组件在测试里跑得好好的、
     一上真服务就空白 —— api_smoke 有一条闸专门比对这两边的字段集。 */
  expression: "",
  viseme: "", viseme_weight: 0.0, visemes: ["SIL", "A", "I", "U", "E", "O", "N"],
  poses: [{ id: "eye_hl_style", current: "round", entries: ["round", "star"] }],
  /* 区域表 + 画布尺寸：UI 要靠它发现区域、做画布↔帧坐标换算，不能硬编码 */
  canvas_w: 848, canvas_h: 1360, frame_w: 466, frame_h: 748,
  /* 形态路线图：ready 的能切，planned 的只在界面上灰显 */
  form_roadmap: [
    { id: "teen", name: "少女", status: "ready", note: "主形态" },
    { id: "loli", name: "萝莉", status: "planned", note: "音色已选" },
    { id: "chibi", name: "Q 版", status: "planned", note: "头身比 1:2.5" },
  ],
  regions: [
    { id: "head", action: "head_pat", cursor: "hand", rect: [244, 0, 357, 391] },
    { id: "body", action: "stroke", cursor: "hand", rect: [253, 391, 339, 694] },
    { id: "feet", action: "surprised", cursor: "hand", rect: [253, 1085, 339, 207] },
  ],
};

/* 参数表：真服务 46 个，这里放几个有代表性的（内建 binds=0 的、普通的、负区间的） */
const PARAMS = {
  params: [
    { id: "ParamAngleX", label: "头 左右", min: -30, max: 30, default: 0,
      value: 0, expr: 0, effective: 0, builtin: true, binds: 0 },
    { id: "ParamEyeLOpen", label: "左眼 睁开", min: 0, max: 1, default: 1,
      value: 1, expr: 1, effective: 1, builtin: true, binds: 0 },
    { id: "ParamBrowLY", label: "左眉 上下", min: -1, max: 1, default: 0,
      value: 0, expr: 0, effective: 0, builtin: false, binds: 2 },
    { id: "ParamHairFront", label: "前发 摆动", min: -1, max: 1, default: 0,
      value: 0, expr: 0, effective: 0, builtin: false, binds: 3 },
    { id: "ParamMouthOpenY", label: "嘴 张开", min: 0, max: 1, default: 0,
      value: 0, expr: 0, effective: 0, builtin: false, binds: 1 },
  ],
};
const calls = [];
const callsFull = [];      /* calls 把 query 切掉了，查参数名/数值要用这个 */
function makeFetch() {
  return async function (url) {
    calls.push(String(url).split("?")[0]);
    callsFull.push(String(url));
    const u = String(url);
    const json = (o) => ({
      ok: true, status: 200,
      headers: { get: () => "application/json" },
      json: async () => o, text: async () => JSON.stringify(o),
      blob: async () => ({ size: 1234 }),
    });
    if (u.startsWith("layout.json")) return json(JSON.parse(fs.readFileSync(path.join(WEB, "layout.json"), "utf8")));
    if (u.includes("platform.json")) {
      const f = path.join(WEB, "platform.json");
      if (!fs.existsSync(f)) return { ok: false, status: 404, headers: { get: () => "" } };
      return json(JSON.parse(fs.readFileSync(f, "utf8")));
    }
    if (u.startsWith("themes/")) {
      const f = path.join(WEB, u.split("?")[0]);
      if (!fs.existsSync(f)) return { ok: false, status: 404, headers: { get: () => "" } };
      return json(JSON.parse(fs.readFileSync(f, "utf8")));
    }
    if (u.includes("/api/route")) {
      /* 这个假端点必须和 C 侧 zgw_route_for 的口径一致，否则面板测绿了、
         真服务上却是另一回事（吃过这个亏：stub 漏字段 → 测试绿、真界面空白）。 */
      const q = Object.fromEntries(new URLSearchParams((u.split("?")[1] || "")));
      const sens = q.sensitive === "1";
      /* 跟 C 侧 zgw_classify 同口径的迷你版：关键词 + 长度 */
      const qt = q.q || "";
      const KW = ["代码", "函数", "报错", "为什么", "分析", "查一下", "```"];
      const kw = KW.find((k) => qt.includes(k));
      const heavy = q.heavy === "1" || !!kw || qt.length >= 200;
      const tok = parseInt(q.tokens || "0", 10), load = parseInt(q.load || "-1", 10);
      const down = q.cloud_down === "1";
      let local = true, reason = "default_local", ok = true;
      if (sens) { reason = "sensitive_local"; }
      else if (tok > 512) { local = false; reason = "long_cloud"; }
      else if (heavy) { local = false; reason = "heavy_cloud"; }
      else if (load >= 85) { local = false; reason = "local_busy"; }
      if (!local && down) { local = true; reason = "cloud_down"; }
      return json({ cap: "chat.completion", ok: ok, provider: local ? "ollama" : "deepseek",
                    model: local ? "qwen2.5:7b" : "deepseek-chat", local: local,
                    reason: reason, blocked_sensitive: false,
                    task: heavy ? "heavy" : "simple", task_hit: kw || (qt.length >= 200 ? "长文" : ""),
                    rules: { tokens_cloud: 512, local_busy_pct: 85, sensitive_local_only: true },
                    stats: { local: 3, cloud: 1, local_share: 0.75,
                             logged: 4, log_failed: 0 } });
    }
    if (u.includes("/api/params.json")) return json(PARAMS);
    if (u.includes("voicebank.json")) {
      const f = path.join(WEB, "voicebank.json");
      if (!fs.existsSync(f)) return { ok: false, status: 404, headers: { get: () => "" } };
      return json(JSON.parse(fs.readFileSync(f, "utf8")));
    }
    if (u.includes("emotion_map.json")) {
      const f = path.join(__dirname, "..", "config", "emotion_map.json");
      if (!fs.existsSync(f)) return { ok: false, status: 404, headers: { get: () => "" } };
      return json(JSON.parse(fs.readFileSync(f, "utf8")));
    }
    if (u.includes("/api/gateway.json")) return json(GATEWAY);
    if (u.includes("/api/info.json")) return json(INFO);
    if (u.includes("/api/speech.json"))
      return json({ line: "", lipsync: { active: false, id: "", level: 0, remain: 0 } });
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
      /* 显示 100x300，点正中间 (50,150) → 应按 info.frame_w/h (466x748) 换算成 (233,374)。
         这里**不能**用 img.naturalWidth：图片尺寸是画布 × 画质档 s%，
         而 /api/poke 吃的是引擎帧缓冲坐标（画布 × pet scale），两者是两回事。
         stub 故意把 naturalWidth 设成 848x1360，走错分支就会得到 (424,680)。 */
      const px = Number(q.get("x")), py = Number(q.get("y"));
      CHECK(Math.abs(px - 233) < 3 && Math.abs(py - 374) < 5,
            "点击坐标应按 info.frame_w/h 换算（期望 233,374；实际 "
            + px + "," + py + (Math.abs(px - 424) < 3 ? " ← 用成 naturalWidth 了" : "") + "）");
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

  SECTION("立绘调试台（G65）：底层能力要在界面上点得到");
  {
    const el = slotOf("rig");
    /* mount 里串了两个 await（info + params），要多放几个 tick 才渲染完 */
    for (let i = 0; i < 6; i++) await new Promise((r) => setImmediate(r));
    const txt = walk(el).map((n) => n._text).join(" ");
    const btns = walk(el).filter((n) => n.tagName === "BUTTON");
    const btxt = btns.map((b) => b._text);

    /* 动作：引擎给的都要有按钮，而且 idle/sleep 这两个没出现在 info.actions 里的
       也要补上 —— 它们是默认动作和睡眠态动作，调试时必须能手动触发 */
    INFO.actions.forEach((a) => {
      CHECK(btxt.indexOf(a) >= 0, "动作 " + a + " 要有按钮");
    });
    ["idle", "sleep"].forEach((a) => {
      CHECK(btxt.indexOf(a) >= 0, "隐藏动作 " + a + " 也要能手动触发");
    });

    /* 表情层和情绪是两个不同的端点，之前界面上只有情绪 */
    INFO.expressions.forEach((e) => {
      CHECK(btxt.indexOf(e.name) >= 0, "表情 " + e.name + " 要有按钮");
    });
    CHECK(btxt.indexOf("取消") >= 0, "表情要能取消（/api/expression?off=1）");

    /* 口型：7 个音素，列表从 info 来而不是前端硬编码 */
    INFO.visemes.forEach((v) => {
      CHECK(btxt.indexOf(v) >= 0, "口型 " + v + " 要有按钮");
    });

    /* 互斥差分 */
    INFO.poses.forEach((g) => {
      g.entries.forEach((e) => {
        CHECK(btxt.indexOf(e) >= 0, "差分档位 " + e + " 要有按钮");
      });
      CHECK(btxt.indexOf("关掉") >= 0, "差分要能整组关掉");
    });

    /* 开关 */
    ["暂停动画", "眨一下", "视线跟随", "参数全复位"].forEach((x) => {
      CHECK(btxt.indexOf(x) >= 0, "要有「" + x + "」");
    });

    /* 形变器读数：光看图分不出裙摆在不在荡 */
    CHECK(txt.includes("形变器") && txt.includes("skirt_sway_x"),
          "形变器当前量要显示出来");

    /* 参数：46 个要分组，不能平铺。组名点开才出滑块。 */
    CHECK(txt.includes("参数 " + PARAMS.params.length + " 个"),
          "参数总数要显示（" + PARAMS.params.length + "）");
    const groups = btxt.filter((t) => t && t.indexOf("▸") === 0);
    CHECK(groups.length >= 3,
          "参数要分组折叠（实际 " + groups.length + " 组）");
    /* 分组要真的按前缀分对：眉毛参数不能跑到眼睛组里 */
    CHECK(groups.some((g) => g.includes("眼睛")) && groups.some((g) => g.includes("眉毛")),
          "眼睛和眉毛要分成两组（Live2D 官方前缀规则）");
    const browGroup = groups.find((g) => g.includes("眉毛"));
    CHECK(browGroup && browGroup.includes("(1)"),
          "眉毛组应有 1 个参数（stub 里只放了 ParamBrowLY），实际 " + browGroup);
  }

  SECTION("形态路线图（G68）：没做的形态要看得见但点不了");
  {
    const el = slotOf("appearance");
    const txt = walk(el).map((n) => n._text).join(" ");
    const btns = walk(el).filter((n) => n.tagName === "BUTTON");
    const opts = walk(el).filter((n) => n.tagName === "OPTION");

    /* 能切的形态只有 ready 的，planned 的绝不能进下拉 —— 切过去会白屏 */
    const formOpts = opts.map((o) => o.value);
    CHECK(formOpts.indexOf("teen") >= 0, "ready 的形态要进下拉");
    CHECK(formOpts.indexOf("loli") < 0 && formOpts.indexOf("chibi") < 0,
          "planned 的形态不能进切换下拉（实际 " + formOpts.join(",") + "）");

    /* 但要在界面上看得见，否则用户不知道还有这些规划 */
    INFO.form_roadmap.filter((g) => g.status !== "ready").forEach((g) => {
      const b = btns.find((x) => x._text && x._text.indexOf(g.name) === 0);
      CHECK(!!b, "未实装形态 " + g.name + " 要显示出来");
      CHECK(b && b.disabled === true, "未实装形态 " + g.name + " 的按钮要禁用");
    });
    CHECK(txt.includes("还没做的形态"), "要说明这些是还没做的");
  }

  SECTION("舞台交互（G67）：hover / region / speak 要在界面上点得到");
  {
    const el = slotOf("interact");
    for (let i = 0; i < 6; i++) await new Promise((r) => setImmediate(r));
    const txt = walk(el).map((n) => n._text).join(" ");
    const btns = walk(el).filter((n) => n.tagName === "BUTTON");
    const btxt = btns.map((b) => b._text);

    /* 三个开关 */
    ["视线跟随鼠标", "区域探针开", "工具：手"].forEach((x) => {
      CHECK(btxt.some((t) => t && t.indexOf(x) === 0), "要有「" + x + "」开关");
    });

    /* 区域按钮要从 info.regions 来，不能硬编码。带上动作名，一眼知道点下去会发生什么 */
    INFO.regions.forEach((g) => {
      CHECK(btxt.some((t) => t && t.indexOf(g.id) === 0 && t.includes(g.action)),
            "区域 " + g.id + " 要有按钮且标出动作 " + g.action);
    });
    /* rect 要显示出来：调区域边界时要能直接读数，不然只能靠点 */
    CHECK(txt.includes("244,0,357,391"),
          "区域 rect 要显示（head 的画布矩形）");

    /* 台词：从 voice_manifest.json 来 */
    CHECK(txt.includes("台词口型"), "要有台词口型区块");
    const opts = walk(el).filter((n) => n.tagName === "OPTION");
    CHECK(opts.length === 2, "两条台词要进下拉（stub 给了 2 条，实际 " + opts.length + "）");
    CHECK(opts.some((o) => o._text && o._text.includes("摸头好舒服")),
          "下拉里要显示台词正文，不能只有 id");
    CHECK(opts.some((o) => o._text && o._text.indexOf("pat_1_base0") === 0),
          "speak 的 id 是 <line>_<variant>，manifest 没写 variant 时要补 base0");
    ["播放口型", "停止"].forEach((x) => {
      CHECK(btxt.indexOf(x) >= 0, "要有「" + x + "」按钮");
    });

    /* 点区域按钮要发 poke，且坐标必须是**帧坐标**（画布 rect 中心换算过的），
       直接把画布坐标丢给 /api/poke 会点到画面外 —— 这是本组件最容易写错的地方 */
    callsFull.length = 0;
    const headBtn = btns.find((b) => b._text && b._text.indexOf("head") === 0);
    headBtn.dispatch("click");
    await new Promise((r) => setImmediate(r));
    const pk = callsFull.find((c) => c.includes("/api/poke"));
    CHECK(!!pk, "点区域按钮要发 /api/poke");
    if (pk) {
      const u = new URLSearchParams(pk.split("?")[1] || "");
      const px = Number(u.get("x")), py = Number(u.get("y"));
      /* head rect [244,0,357,391] 中心 = 画布(422.5, 195.5) → 帧(232, 107) */
      CHECK(px > 220 && px < 245, "poke 的 x 要换算成帧坐标（期望约 232，实际 " + px + "）");
      CHECK(py > 95 && py < 120, "poke 的 y 要换算成帧坐标（期望约 107，实际 " + py + "）");
      CHECK(px < INFO.frame_w && py < INFO.frame_h,
            "坐标必须落在帧内（" + INFO.frame_w + "x" + INFO.frame_h + "），"
            + "直接传画布坐标就会越界");
    }
  }

  SECTION("音色库（G64）：契约 → 清单 → 面板，四种情绪通路要显示得出来");
  {
    const el = slotOf("voicebank");
    await new Promise((r) => setImmediate(r));
    await new Promise((r) => setImmediate(r));
    const vbf = path.join(WEB, "voicebank.json");
    const vb = JSON.parse(fs.readFileSync(vbf, "utf8"));
    const txt = walk(el).map((n) => n._text).join(" ");

    CHECK(vb.voices.length >= 12,
          "音色得够挑（清单 " + vb.voices.length + " 个）");
    /* 用户要三种人设都有 */
    ["loli", "shoujo", "young_woman"].forEach((p) => {
      CHECK(vb.voices.some((v) => v.persona === p), "要有 " + p + " 音色");
    });
    /* 按内容核对而不是数行数：真实音色名要出现在面板里 */
    const first = vb.voices[0];
    CHECK(txt.includes(first.name),
          "面板要列出音色名字（找 " + first.name + "）");
    /* 诚实标注：免费通道做不了情绪，界面必须说清楚，不能让人以为选了也有情绪 */
    const pros = vb.voices.filter((v) => v.emotion_mode === "prosody");
    CHECK(pros.length > 0 && pros.every((v) => v.emotion_distinct === 0),
          "prosody 档的情绪区分度应为 0（实际 " + pros.map((v) => v.emotion_distinct) + "）");
    CHECK(txt.includes("无情绪"),
          "做不了情绪的音色要在界面上写明白");
    /* 用户两条硬要求要在界面上看得见 */
    const agents = (vb.cast && vb.cast.agents) || [];
    CHECK(agents.length >= 3 && agents.every((a) => txt.includes(a.agent)),
          "每个 AI 用哪把嗓子要列出来");
    const avoices = agents.map((a) => a.voice);
    CHECK(new Set(avoices).size === avoices.length,
          "每个 AI 的声音都不一样（用户硬要求）");
    const vmap = {};
    vb.voices.forEach((v) => { vmap[v.id] = v; });
    CHECK(new Set(avoices.map((v) => vmap[v] && vmap[v].provider)).size > 1,
          "AI 的声音不能都来自同一家（用户硬要求）");
    /* 没配密钥的音色要标出来，且角色要显示正在用的兜底 —— 否则界面说能用、实际发不出去 */
    if (vb.voices.some((v) => !v.ready)) {
      CHECK(txt.includes("待配密钥"), "没配密钥的音色要标出来");
    }
    /* 四种通路的差别必须显示得出来：选中音色后要说清这个情绪怎么发 */
    const em = JSON.parse(fs.readFileSync(
      path.join(__dirname, "..", "config", "emotion_map.json"), "utf8"));
    CHECK(Object.keys(em.emotions).length >= 8,
          "情绪种类要够用（" + Object.keys(em.emotions).length + " 种）");
    const sel = vb.voices.find((v) => v.ready) || vb.voices[0];
    const expect = { style: "SSML style=", emotion: 'emotion="',
                     inline_tag: "文本里加", prosody: "只能模拟" }[sel.emotion_mode];
    CHECK(txt.includes(expect),
          "选中 " + sel.emotion_mode + " 档音色时要显示它怎么发情绪（找「" + expect + "」）");
  }

  SECTION("平台能力总览（G50/G51）：契约 → 清单 → 网关 → 面板");
  {
    const el = slotOf("platform");
    await new Promise((r) => setImmediate(r));       /* 等它 fetch 完 */
    await new Promise((r) => setImmediate(r));
    const pf = JSON.parse(fs.readFileSync(path.join(WEB, "platform.json"), "utf8"));
    const rows = walk(el).filter((n) => n.className === "voice-item");
    CHECK(rows.length === pf.capabilities.length,
          "每种能力都应列出来（契约 " + pf.capabilities.length + " 种，面板 " + rows.length + " 行）");
    const chips = walk(el).filter((n) => n.className.startsWith("chip"));
    CHECK(chips.length === pf.providers.length,
          "每个供应商都应有一枚标签（契约 " + pf.providers.length + " 个，面板 " + chips.length + "）");
    const txt = walk(el).map((n) => n._text).join(" ");
    CHECK(txt.includes("本机") && txt.includes("网络"),
          "要分得清本地模型和网络服务（用户要求两者都兼容）");
    CHECK(txt.includes("（待接入）"),
          "还没有供应商的能力要明确标出来，不能假装能用");
    /* 契约与清单必须同步：清单里的供应商 id 都要能在 config/providers 下找到文件 */
    const provDir = path.join(__dirname, "..", "config", "providers");
    const missing = pf.providers.filter((p) => !fs.existsSync(path.join(provDir, p.id + ".json")));
    CHECK(missing.length === 0,
          "清单里的供应商都应有契约文件（缺 " + missing.map((m) => m.id).join(",") + "）");
    /* 上面那些只数行数和标签数 —— 字段名写错（清单把 capabilities 扁平成 caps、
       balance 扁平成 balance_mode）时行数照样对，断言照样绿。所以这里按内容核对：
       真实的供应商归属和余额口径必须出现在面板文本里。 */
    const apiProv = pf.providers.filter((p) => p.balance_mode === "api");
    CHECK(apiProv.length > 0 && apiProv.every((p) => txt.includes(p.name + " · 网络 · 余额:api")),
          "能查余额的供应商要标出余额口径（" + apiProv.map((p) => p.id).join(",") + "）");
    /* 网关状态（G51）：账本和路由结果要真的显示出来 */
    CHECK(txt.includes("16 条路由") && txt.includes("prefer_local"),
          "网关的路由条数和策略要显示出来");
    CHECK(txt.includes("1.2345"), "已花费要显示真实数字（账本 spent）");
    CHECK(txt.includes("失败 1 次"), "失败次数要显示——它是换供应商的依据");
    CHECK(txt.includes("→ ollama（免费）"),
          "能用的能力要说清楚走谁、花不花钱");
    CHECK(txt.includes("+1 备选"), "有备选要标出来（candidates=2 时）");
    CHECK(txt.includes("都没开，去设置里打开"),
          "全关着的能力要给出可操作的指引，而不是只说不可用");
    const served = pf.capabilities.filter((c) => c.providers.length);
    CHECK(served.length > 0 && served.every((c) => txt.includes(c.name + " — " + c.providers.join(" / "))),
          "每种能力要列出真实的供应商归属，不能只渲染空行（" + served.length + " 种有供应商）");
  }

  SECTION("双路由沙盘（G99/DC18）：规则要在界面上看得见、拨得动");
  {
    const el = slotOf("route");
    await new Promise((r) => setImmediate(r));
    await new Promise((r) => setImmediate(r));
    const txt = () => walk(el).map((n) => n._text).join(" ");
    CHECK(txt().includes("本地"), "默认应显示落点在本地");
    CHECK(txt().includes("70~85%"), "要把目标分流区间摆出来，否则用户不知道这个数算好还是坏");
    CHECK(!txt().includes("default_local") || txt().includes("没有任何理由上云"),
          "理由不能只给英文枚举，要翻成人话");

    /* 拨动"带隐私标记"：落点和理由都得跟着变 —— 只渲染不联动的面板等于贴图 */
    const before = txt();
    const bsens = walk(el).find((n) => n.id === "route-sensitive");
    CHECK(!!bsens, "要有『带隐私标记』开关");
    bsens.onclick();
    await new Promise((r) => setImmediate(r));
    await new Promise((r) => setImmediate(r));
    CHECK(txt() !== before, "拨开关之后面板内容必须变化");
    CHECK(txt().includes("强制本地"), "带隐私标记时要说清楚是『强制本地』");
    CHECK(bsens.className.includes("pri"), "按下的开关要高亮（classList.toggle 要真的起作用）");

    /* 长请求要上云 —— 这条是"本地优先不是无脑优先"的可见证据 */
    /* 打一句"帮我写个函数"：面板应该自己判成重活并说出凭哪个词 */
    const qin = walk(el).find((n) => n.id === "route-q");
    CHECK(!!qin, "要有能打字的输入框");
    qin.value = "帮我写个函数"; qin.oninput();
    await new Promise((r) => setImmediate(r));
    await new Promise((r) => setImmediate(r));
    CHECK(txt().includes("重活") && txt().includes("函数"),
          "要判成重活并说出凭哪个词（不能只给个 heavy）");
    qin.value = "陪我聊聊天"; qin.oninput();
    await new Promise((r) => setImmediate(r));
    await new Promise((r) => setImmediate(r));
    CHECK(txt().includes("简单活"), "闲聊要判成简单活，否则每句寒暄都要花钱");

    const tokr = walk(el).find((n) => n.id === "route-tokens");
    bsens.onclick();                       /* 先关掉隐私标记 */
    await new Promise((r) => setImmediate(r));
    tokr.value = "4000"; tokr.oninput();
    await new Promise((r) => setImmediate(r));
    await new Promise((r) => setImmediate(r));
    CHECK(txt().includes("云端"), "4000 token 的请求应该落到云端");

    /* 流水条数要露在面上：占比只有攒够量才说明问题，
       而且用户得能看出"这些决策是存下来了的"，不然 usage_report 跑出来是空的也不知道为什么 */
    CHECK(txt().includes("4 条") || txt().includes("已存 4"),
          "要显示决策流水存了多少条（现在是 " + (txt().match(/已存[^，\n]*/) || ["没显示"])[0] + "）");
    CHECK(txt().includes("usage.jsonl"), "要写明流水存在哪，用户才找得到文件");
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
