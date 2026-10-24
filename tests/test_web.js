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
  let chatFail = false;
  const chatCalls = [];
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
  /* 引擎（/api/info.json）和 actions 一一对应地给出中文名，名字来自 rig.json */
  action_names: ["待机", "开心", "挥手", "睡觉"],
  expressions: [{ id: "smile", name: "微笑" }],
  deformers: { skirt_sway_x: 0.0, skirt_hem_x: 0.0 },
  // 物理摆链输出和形变器分开给：形变器 = 物理 + 环境摆动之和（T45.9）
  physics: { skirt_x: 0.0, skirt_y: 0.0 },
  // 物理 2.0 的摆链（T47.2）："<链>.<粒子>" 是摆角（度），"<链>#<第几条输出>"
  // 是翻译成通道之后真正写出去的值（像素或形变量）。
  physics2: { "longhair2.1": 0.0, "longhair2#0": 0.0 },
  // 力场（T47.3）：重力、定常风、常驻微风，以及本帧真正吹到头发上的合成风
  forces: { gx: 0, gy: 1, wx: 0, wy: 0, breeze: 0.03, wind_x: 0, wind_y: 0 },
  /* 下面这些字段真服务都有。stub 漏字段的后果是组件在测试里跑得好好的、
     一上真服务就空白 —— api_smoke 有一条闸专门比对这两边的字段集。 */
  expression: "",
  viseme: "", viseme_weight: 0.0, visemes: ["SIL", "A", "I", "U", "E", "O", "N"],
  poses: [{ id: "eye_hl_style", current: "round", entries: ["round", "star"] },
           { id: "tail_pose", current: "relaxed", entries: ["relaxed", "up", "puff", "tuck"] },
           { id: "hood_pose", current: "down", entries: ["up", "down"] },
           { id: "hairstyle", current: "none", entries: ["long", "twin", "pony"] }],
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
    if (u.includes("/api/chat")) {
      /* 三种局面都要能模拟：dry-run / 真发成功 / 上游拒绝（502）。
         最后那种最重要 —— 界面不许把失败显示成一条正常回复。 */
      const q = new URLSearchParams(u.split("?")[1] || "");
      chatCalls.push(Object.fromEntries(q.entries()));
      if (q.get("dry") === "1") {
        return json({
          ok: true, dry: true, provider: "ollama", model: "qwen2.5:7b", local: true,
          reason: "default_local", http_status: 0, attempts: 0,
          tokens_in: 0, tokens_out: 0, cost: 0, persona_bytes: 781, text: "", error: "",
          url: "http://127.0.0.1:11434/v1/chat/completions",
          request_body: "{\"model\":\"qwen2.5:7b\",\"messages\":[{\"role\":\"system\",\"content\":\"你现在扮演「小寻」\"},{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":false}",
        });
      }
      if (chatFail) {
        return { ok: false, status: 502,
          headers: { get: () => "application/json" },
          json: async () => ({ ok: false, provider: "ollama", model: "qwen2.5:7b",
            local: true, reason: "default_local", http_status: 0, attempts: 1,
            text: "", error: "http://127.0.0.1:11434/v1/chat/completions：连不上（服务没开，或者端口不对）" }),
          text: async () => "" };
      }
      return json({
        ok: true, dry: false, provider: "ollama", model: "qwen2.5:7b", local: true,
        reason: "default_local", http_status: 200, attempts: 1,
        tokens_in: 101, tokens_out: 19, cost: 0, persona_bytes: 781,
        text: "当然开心啦！今天你终于能跟我说话了喵～", error: "",
      });
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
/* localStorage：浏览器有、node 没有。装扮面板的"选了就记住"靠它，
   所以这里给个最小实现（并留了 _fail 开关，用来验"隐私模式下抛异常也不许崩"）。 */
const LS = {
  _d: {}, _fail: false,
  getItem(k) { if (this._fail) throw new Error("denied"); return k in this._d ? this._d[k] : null; },
  setItem(k, v) { if (this._fail) throw new Error("denied"); this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};
ctx.localStorage = LS;
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

    /* ★ 名字必须来自引擎的 action_names（数据层），不是界面里的硬编码表。
       正式软件的 UI 要整个重做，界面层存的文案到时候得重写一遍；
       数据层存的，换几个界面都还在。 */
    CHECK(!!(INFO.action_names && INFO.action_names.length === INFO.actions.length),
          "引擎要给出和 actions 一一对应的 action_names");

    /* ★ 2026-10-24 截图里 nod / wave_both / heart_hands / kirara_jump /
       look_around / star_eyes / shift_weight / tiptoe 八个按钮露了英文 id。
       根因是名字写在界面的硬编码表里、漏了新动作。这条断言盯住它不许再犯。 */
    const leaked = btns.filter((b) => /^[a-z][a-z0-9_]*$/.test(b._text || ""));
    CHECK(leaked.length === 0,
          "★ 按钮上不许出现英文 id（漏了：" + leaked.map((b) => b._text).join(" ") + "）");
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

  {
    /* 画质 = 显示尺寸 × dpr，不能是写死的低档。
       2026-10-15 之前这里固定请求 s=60（279x448），再被 CSS 拉到 ~680px 高显示，
       用户看到的"动作时脸部模糊"就是这一步；而且换档会连带改变图片固有尺寸，
       立绘跟着忽大忽小（看起来像脸被拉扯）。 */
    const stage = ZC.host.find("stage");
    CHECK(!!stage && typeof stage.fitDisplay === "function", "舞台应有 fitDisplay()");
    if (stage && stage.fitDisplay) {
      const pct = stage.fitDisplay();
      /* stub：info.frame_h = 748，可用高度上限 680，dpr 1 → ceil(680/748*100) = 91 */
      CHECK(pct === 91, "原生画质应按显示高度算（期望 91，实际 " + pct + "）");
      CHECK(stage.currentQuality() === 91,
            "自动档应从原生清晰起步（实际 " + stage.currentQuality() + "）");
      const img = walk(slotOf("stage")).filter((n) => n.tagName === "IMG")[0];
      CHECK(img.style.height === "680px" && img.style.width === "424px",
            "显示尺寸应被显式钉死，和画质档无关（实际 "
            + img.style.width + "x" + img.style.height + "）");
      /* 降档只该降分辨率，不该改变显示尺寸 */
      stage.qualityIdx = 0;
      CHECK(stage.currentQuality() < 91 && img.style.height === "680px",
            "降档后分辨率变小但显示尺寸不变（实际 " + stage.currentQuality()
            + " / " + img.style.height + "）");
      stage.qualityIdx = stage.QUALITY_SCALES.length - 1;
      /* 手动档仍按用户选的百分比走 */
      stage.qualityMode = "50";
      CHECK(stage.currentQuality() === 50, "手动选 50% 应原样生效");

      /* ★ 台词气泡只认 seq（G105）。
         原来 onSpeech 每次轮询（~80ms）都 clearTimeout + 重设 4500ms 隐藏计时，
         而 /api/speech.json 的 line 是"最后说过的那句"、会一直返回同一句，
         于是计时被无限推后 —— 气泡**永远不会消失**。
         这里用 stub 的 timers 数组数"有没有重新排过计时"：同一个 seq 连续喂 5 次，
         只应该排 1 次。 */
      {
        const bubble = walk(slotOf("stage")).filter(
          (n) => n.className && String(n.className).indexOf("bubble") >= 0)[0];
        CHECK(!!bubble, "舞台应有气泡元素");
        const n0 = timers.length;
        stage.onSpeech({ line: "你好呀", seq: 7, age: 0 });
        const n1 = timers.length;
        CHECK(n1 === n0 + 1, "新台词应排一次隐藏计时（实际 " + (n1 - n0) + " 次）");
        CHECK(bubble && bubble.hidden === false, "新台词应显示气泡");
        for (let i = 0; i < 5; ++i) stage.onSpeech({ line: "你好呀", seq: 7, age: i });
        CHECK(timers.length === n1,
              "seq 没变就不许重排计时，否则气泡永不消失（多排了 "
              + (timers.length - n1) + " 次）");
        stage.onSpeech({ line: "哇！别敲啦", seq: 8, age: 0 });
        CHECK(timers.length === n1 + 1, "换了 seq 才重新计时");
        CHECK(bubble && bubble.hidden === false, "换句后气泡仍显示");
        stage.onSpeech({ line: "", seq: 9, age: -1 });
        CHECK(bubble && bubble.hidden === true, "line 为空应立刻收掉气泡");
        /* 接上一句说了很久的台词时，按剩余时间收，不从头再给 4.5 秒 */
        const n2 = timers.length;
        stage.onSpeech({ line: "说了很久了", seq: 10, age: 4.0 });
        CHECK(timers.length === n2 + 1 && timers[timers.length - 1].ms <= 600,
              "age 大的台词应只剩很短的显示时间（实际 "
              + timers[timers.length - 1].ms + "ms）");
      }

      /* ★ 本地模式必须一律不降级（2026-10-15 用户要求：本地要正常分辨率和帧率，
         要能放大到整个桌面还清晰）。降级那套只为沙箱预览的 PNG 传输开销存在。 */
      stage.qualityMode = "auto";
      CHECK(stage.isLocalHost("localhost", "http:") === true, "localhost 应判为本地");
      CHECK(stage.isLocalHost("127.0.0.1", "http:") === true, "127.0.0.1 应判为本地");
      CHECK(stage.isLocalHost(null, "file:") === true, "file: 协议应判为本地");
      /* 方向负控：沙箱预览域名绝不能被当成本地，否则远端用户会卡死 */
      CHECK(stage.isLocalHost("5173-abc123.e2b.app", "https:") === false,
            "沙箱预览域名必须判为远程");
      CHECK(stage.isLocalHost(null, "https:") === false, "读不到 location 时按远程处理");

      const wasLocal = stage.isLocal, wasScales = stage.QUALITY_SCALES, wasMin = stage.minInterval;
      /* 远程：卡住时该降级 */
      stage.isLocal = false; stage.QUALITY_SCALES = [0.5, 0.65, 0.8, 1.0];
      stage.qualityIdx = 3; stage.minInterval = 1000 / 12; stage.frameMs = 500;
      stage.tuneQuality();
      CHECK(stage.minInterval > 1000 / 12 || stage.qualityIdx < 3,
            "远程模式下卡顿应该降级（帧率或分辨率）");
      /* ★★★ 2026-10-23 第四十八问：远程帧率上限 12→30fps，降级阶梯重排。
         官方口径是「一个模型最低 30FPS 以上」，10fps 已经进"卡顿"区，
         所以这条阶梯有**封底**：无论多卡都不许掉到 10fps 以下。 */
      stage.isLocal = false; stage.QUALITY_SCALES = [0.5, 0.65, 0.8, 1.0];
      stage.qualityIdx = 3; stage.minInterval = 1000 / 30; stage.frameMs = 500;
      for (let i = 0; i < 40; ++i) stage.tuneQuality();
      CHECK(Math.abs(stage.minInterval - 1000 / 10) < 1e-6,
            "一路卡下去帧率应封底在 10fps（实际 "
            + (1000 / stage.minInterval).toFixed(1) + "fps）");
      CHECK(stage.qualityIdx === 0,
            "一路卡下去分辨率应退到最低档（实际 idx=" + stage.qualityIdx + "）");
      /* 恢复顺畅：先把帧率加回 30fps，再把分辨率加回原生 */
      stage.frameMs = 30;
      stage.tuneQuality();
      CHECK(stage.minInterval < 1000 / 10 && stage.qualityIdx === 0,
            "恢复时应先提帧率、分辨率先不动（实际 "
            + (1000 / stage.minInterval).toFixed(1) + "fps idx=" + stage.qualityIdx + "）");
      for (let i = 0; i < 40; ++i) stage.tuneQuality();
      CHECK(Math.abs(stage.minInterval - 1000 / 30) < 1e-6
            && stage.qualityIdx === stage.QUALITY_SCALES.length - 1,
            "恢复到底应是 30fps + 原生分辨率（实际 "
            + (1000 / stage.minInterval).toFixed(1) + "fps idx=" + stage.qualityIdx + "）");

      /* 本地：同样卡住也绝不降级 */
      stage.isLocal = true; stage.qualityIdx = 3; stage.minInterval = 1000 / 60; stage.frameMs = 500;
      stage.tuneQuality();
      CHECK(stage.qualityIdx === 3 && stage.minInterval === 1000 / 60,
            "本地模式下即使卡顿也不许降级（实际 idx=" + stage.qualityIdx
            + " minInterval=" + stage.minInterval + "）");
      /* 本地：显示高度吃视口、解开 CSS 的 max-height 上限 */
      ctx.innerHeight = 1400;
      stage.fitDisplay();
      CHECK(img.style.maxHeight === "none", "本地模式应解开 #pet 的 max-height 限制");
      CHECK(parseInt(img.style.height, 10) > 680,
            "本地模式显示高度应吃满视口而不是钉在 680（实际 " + img.style.height + "）");
      /* 还原，别影响后面的断言 */
      stage.isLocal = wasLocal; stage.QUALITY_SCALES = wasScales;
      stage.minInterval = wasMin; stage.qualityIdx = stage.QUALITY_SCALES.length - 1;
      delete ctx.innerHeight; img.style.maxHeight = "";
      stage.fitDisplay();
      stage.qualityMode = "auto";
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

  SECTION("装扮面板（T46.4/T46.6）：用户点得到的外观开关 + 选了就记住");
  {
    const el = slotOf("dressup");
    for (let i = 0; i < 6; i++) await new Promise((r) => setImmediate(r));
    const btns = () => walk(el).filter((n) => n.tagName === "BUTTON");
    const btxt = () => btns().map((b) => b._text);
    const txt = walk(el).map((n) => n._text).join(" ");

    /* ① 中文名：用户面板和调试台的分界线就在这儿。英文 id 直接出现在按钮上 = 没登记 */
    ["发型", "兜帽", "猫尾", "眼高光"].forEach((n) => {
      CHECK(txt.indexOf(n) >= 0, "装扮面板要有「" + n + "」这一行");
    });
    ["短发（原装）", "长发", "双马尾", "马尾", "戴上", "摘下"].forEach((n) => {
      CHECK(btxt().indexOf(n) >= 0, "要有「" + n + "」按钮");
    });
    CHECK(btxt().indexOf("hairstyle") < 0 && btxt().indexOf("twin") < 0,
          "按钮上不许直接露英文 id（那是调试台的做法）");

    /* ② 短发这一档 /api/info.json 的 entries 里没有（entries 只列有部件的档），
          靠组件的 extra 补出来。少了它用户就没法切回原装短发。 */
    CHECK(btxt().filter((t) => t === "短发（原装）").length === 1,
          "原装短发要补出按钮，而且只补一颗");

    /* ③ 兜帽只给两档，不给「关掉」—— none 会把呆毛和猫耳一起吞掉。
          查的是**按钮文案**而不是整面板文本：提示语里出现「关」字是正常的
          （2026-10-19 加兽耳娘开关时被这条宽断言误伤过一次）。 */
    CHECK(btxt().indexOf("关掉") < 0, "装扮面板不给「关掉」按钮（兜帽那档会连呆毛猫耳一起吞）");

    /* ③b 兽耳娘模式要能关（用户 2026-10-19：「猫耳和猫尾的动物娘模式不能关闭吗？」）。
           猫耳是两个 0/1 参数、猫尾是一个 pose 组，对用户必须是**一个**开关。 */
    CHECK(txt.indexOf("兽耳娘") >= 0, "装扮面板要有「兽耳娘」这一行");
    CHECK(btxt().indexOf("关（纯人类）") >= 0, "兽耳娘要给得出「关」这一档");
    {
      callsFull.length = 0;
      btns().find((b) => b._text === "关（纯人类）").onclick();
      for (let i = 0; i < 8; i++) await new Promise((r) => setImmediate(r));
      const j = callsFull.join(" ");
      CHECK(j.includes("id=ParamAccEarL&v=0") && j.includes("id=ParamAccEarR&v=0"),
            "关兽耳娘要把两只猫耳参数打到 0（实际 " + j + "）");
      CHECK(/group=tail_pose&id=(&|$|\s)/.test(j + " "),
            "关兽耳娘要把猫尾档位打成空（= 四条尾巴全收）（实际 " + j + "）");
      const sv = JSON.parse(LS._d["zc.dressup.v1"] || "{}");
      CHECK(sv["sw.kemonomimi"] === 0, "关掉要记进 localStorage，刷新后不许自己长回来（实际 "
            + JSON.stringify(sv) + "）");
    }

    /* ④ 点下去要发对请求 */
    callsFull.length = 0;
    btns().find((b) => b._text === "双马尾").onclick();
    for (let i = 0; i < 6; i++) await new Promise((r) => setImmediate(r));
    const pose = callsFull.find((u) => u.includes("/api/pose"));
    CHECK(!!pose && pose.includes("group=hairstyle") && pose.includes("id=twin"),
          "点「双马尾」应调 /api/pose?group=hairstyle&id=twin（实际 " + pose + "）");

    /* ⑤ 选了要记住：写进 localStorage，而且下次挂载时重新打给引擎 */
    const saved = JSON.parse(LS._d["zc.dressup.v1"] || "{}");
    CHECK(saved.hairstyle === "twin", "选过的档要落进 localStorage（实际 " + JSON.stringify(saved) + "）");
    {
      const host2 = { card: (t) => { const b = makeEl("div"); const body = makeEl("div");
                        b.appendChild(body); return { box: b, body: body }; },
                      el: (t, c, x) => { const n = makeEl(t); if (x) n._text = x; return n; },
                      api: async (u) => { callsFull.push(String(u)); return ctx.fetch(u).then((r) => r.json()); },
                      refresh() {} };
      const def = ZC.registry.get("dressup");
      const fresh = Object.create(def || {});
      if (def) {
        callsFull.length = 0;
        await fresh.mount(host2, makeEl("div"), {});
        for (let i = 0; i < 8; i++) await new Promise((r) => setImmediate(r));
        const re = callsFull.find((u) => u.includes("group=hairstyle") && u.includes("id=twin"));
        CHECK(!!re, "重新挂载时要把存档档位重新打一遍（实际 " + callsFull.join(",") + "）");
      }
    }

    /* ⑥ 隐私模式：localStorage 抛异常也不许把面板打黑 */
    LS._fail = true;
    let boom = false;
    try { btns().find((b) => b._text === "摘下").onclick(); } catch (e) { boom = true; }
    for (let i = 0; i < 4; i++) await new Promise((r) => setImmediate(r));
    LS._fail = false;
    CHECK(!boom, "localStorage 不可用时（隐私模式）面板也要能点");
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

  SECTION("聊天框（G54/T61.10）：能打字、能发出去、而且不许藏事");
  {
    const el = slotOf("chat");
    const tick = async () => {
      await new Promise((r) => setImmediate(r));
      await new Promise((r) => setImmediate(r));
      await new Promise((r) => setImmediate(r));
    };
    const txt = () => walk(el).map((n) => n._text).join(" ");
    const find = (id) => walk(el).find((n) => n.id === id);

    CHECK(!!find("chat-input"), "要有能打字的输入框");
    CHECK(!!find("chat-send"), "要有发送按钮");
    CHECK(!!find("chat-dry"), "要有『看看将要发什么』——用户有权在发出去之前看一眼");

    /* ---- 真发一条 ---- */
    chatCalls.length = 0;
    chatFail = false;
    const input = find("chat-input");
    input.value = "你今天开心吗";
    find("chat-send").onclick();
    await tick();

    CHECK(chatCalls.length === 1, "点发送要真的打一次 /api/chat（实际 " + chatCalls.length + " 次）");
    CHECK(chatCalls[0] && chatCalls[0].text === "你今天开心吗", "用户原话要原样送出，不许改写");
    CHECK(chatCalls[0] && chatCalls[0].dry === undefined, "真发时不该带 dry");
    CHECK(txt().includes("你今天开心吗"), "自己说的话要显示在对话里");
    CHECK(txt().includes("当然开心啦"), "模型的回复要显示出来");

    /* 这一段是这块面板和普通聊天界面最不一样的地方：
       每条回复都必须标明是谁答的、走没走出这台机器。 */
    CHECK(txt().includes("ollama"), "★ 要标明是谁答的");
    CHECK(txt().includes("qwen2.5:7b"), "★ 要标明用的哪个型号");
    CHECK(txt().includes("本地"), "★ 要标明这句话有没有离开这台机器");
    CHECK(txt().includes("101") && txt().includes("19"), "要显示 token 用量");
    CHECK(txt().includes("不花钱"), "免费的也要说清是免费的（别让用户以为在烧钱）");
    CHECK(input.value === "", "发完要清空输入框");

    /* ---- 上游失败：不许伪装成一条正常回复 ---- */
    chatFail = true;
    input.value = "再说一句";
    find("chat-send").onclick();
    await tick();
    CHECK(txt().includes("连不上"), "★ 上游失败要把服务端原话显示出来");
    CHECK(txt().includes("出错了"), "失败要标成出错，不能混在正常回复里");
    CHECK(!txt().includes("当然开心啦！今天你终于能跟我说话了喵～ 当然开心啦"),
          "失败时不该再冒出一条假回复");
    chatFail = false;

    /* ---- dry-run：把真会发出去的东西摆出来 ---- */
    chatCalls.length = 0;
    input.value = "看看会发什么";
    find("chat-dry").onclick();
    await tick();
    CHECK(chatCalls.length === 1 && chatCalls[0].dry === "1", "『看看将要发什么』要带 dry=1");
    CHECK(txt().includes("127.0.0.1:11434"), "要摆出真正的目标地址");
    CHECK(txt().includes("\"stream\"") || txt().includes("stream"),
          "要摆出真正的请求体");
    CHECK(txt().includes("781"), "要说明人设占了多少字节");
    CHECK(input.value === "看看会发什么", "dry-run 不该清空输入框（用户多半还要接着发）");

    /* ---- 隐私标记要真的传下去 ---- */
    chatCalls.length = 0;
    const bsens = find("chat-sensitive");
    CHECK(!!bsens, "要有『隐私标记』开关");
    bsens.onclick();
    input.value = "我的身份证号";
    find("chat-send").onclick();
    await tick();
    CHECK(chatCalls[0] && chatCalls[0].sensitive === "1",
          "★ 拨了隐私标记就必须传给后端（不传等于开关是假的）");

    /* ---- 带人设开关 ---- */
    chatCalls.length = 0;
    find("chat-persona").onclick();
    input.value = "不带人设试试";
    find("chat-send").onclick();
    await tick();
    CHECK(chatCalls[0] && chatCalls[0].persona === "0", "关掉『带人设』要传 persona=0");
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

  /* ---------------------------------------------------------------- G114 */
  /* 测试台状态行不许"左右抽搐"：那一行的胶囊每 600ms 换一次内容
     （动作 idle↔surprised、眨眼 0.00↔1.00、fps 9.9↔10.1），
     只要是 inline-block + 比例字体，任何一个变长都会把右边所有胶囊推着走。
     用户 2026-10-16 原话："测试台状态会左右轻微抽搐"。
     这里不跑浏览器，直接查死 test.html 的结构与样式约定。 */
  {
    SECTION("测试台状态行：内容变长也不许推动邻居（G114）");
    const html = fs.readFileSync(path.join(WEB, "test.html"), "utf8");
    const IDS = ["p-act", "p-expr", "p-blink", "p-scale", "p-sleep", "p-fps", "p-region"];
    const row = html.match(/<div class="pillrow"[\s\S]*?<\/div>/);
    CHECK(!!row, "状态行应挂 class=pillrow（固定格子排版）");
    if (row) {
      IDS.forEach((id) => {
        CHECK(row[0].includes('id="' + id + '"'), "状态行应包含胶囊 " + id);
      });
      const keys = (row[0].match(/data-w="([a-z]+)"/g) || []).map((m) => m.slice(8, -1));
      CHECK(keys.length === IDS.length,
            "每个胶囊都要带 data-w 才能定宽（实际 " + keys.length + "/" + IDS.length + "）");
      keys.forEach((k) => {
        const re = new RegExp("\\.pillrow \\.pill\\[data-w=\"" + k + "\"\\][^}]*min-width:\\s*\\d+px");
        CHECK(re.test(html), "data-w=" + k + " 必须有 min-width，否则内容一变长就推邻居");
      });
    }
    CHECK(/\.pillrow\s*\{[^}]*display:\s*flex/.test(html), "pillrow 应是 flex 容器");
    CHECK(/\.pillrow \.pill\s*\{[^}]*font-variant-numeric:\s*tabular-nums/.test(html),
          "状态行数字要走 tabular-nums，否则 0.00→1.00 这种也会抖宽度");
    /* fps 本身仍要在刷新，别把抖动"修"成不更新了 */
    const tjs = fs.readFileSync(path.join(WEB, "test.js"), "utf8");
    CHECK(/\$\("p-fps"\)\.textContent\s*=/.test(tjs), "p-fps 仍要被刷新（别把问题修成不更新）");
  }

  /* ---------------------------------------------------------- 帧刷新节流器 */
  {
    SECTION("测试台画面刷新：在途保护 / 丢弃迟到帧 / 按显示尺寸要图（2026-10-16 抽搐）");
    const sandbox = { window: {}, console };
    sandbox.globalThis = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(path.join(WEB, "frameloop.js"), "utf8"), sandbox);
    const FL = sandbox.window.ZFrameLoop;
    CHECK(!!FL && typeof FL.makeFrameLoop === "function", "frameloop.js 应导出 ZFrameLoop");
    const html = fs.readFileSync(path.join(WEB, "test.html"), "utf8");
    CHECK(html.indexOf("frameloop.js") < html.indexOf("test.js"),
          "test.html 要先引 frameloop.js 再引 test.js（后者启动时就会用它）");

    if (FL) {
      /* ① 按显示尺寸要图：别拿 466px 的图去填 320px 的框 */
      CHECK(FL.frameScale(320, 466, 1) === 69,
            "320px 显示 / 466px 帧 / dpr1 应要 69%（实际 " + FL.frameScale(320, 466, 1) + "）");
      CHECK(FL.frameScale(320, 466, 2) === 100,
            "HiDPI（dpr2）要封顶 100 而不是糊图（实际 " + FL.frameScale(320, 466, 2) + "）");
      CHECK(FL.frameScale(50, 466, 1) === 25,
            "极小显示要卡在下限 25（实际 " + FL.frameScale(50, 466, 1) + "）");
      CHECK(FL.frameScale(320, 0, 1) === 100,
            "还没拿到 info（frame_w=0）时要退回 100，不能乱猜");

      /* ② 在途保护：上一帧没回来，连发多少次都只出一发 */
      let t = 0, loads = [], shown = [];
      const lp = FL.makeFrameLoop({
        now: () => t,
        url: (s) => "F" + s,
        load: (url, ok, fail) => loads.push({ url, ok, fail }),
        show: (url) => shown.push(url),
      });
      lp.tick(50); lp.tick(50); lp.tick(50); lp.tick(50);
      CHECK(loads.length === 1,
            "上一帧没回来时后续 tick 必须不发请求（实际发了 " + loads.length + " 发）—— " +
            "原来的 setInterval(100) 不管这个，链路一慢就把请求堆进队列");
      CHECK(lp.stats().skipped === 3, "被跳过的 tick 要计数（实际 " + lp.stats().skipped + "）");

      /* ③ 回来之后能继续发 */
      loads[0].ok();
      CHECK(shown.length === 1 && shown[0] === "F50", "第一帧回来后要上屏");
      lp.tick(50);
      CHECK(loads.length === 2, "上一帧回来后应能发下一帧（实际 " + loads.length + "）");

      /* ④ 迟到的旧帧要丢掉 —— 画面只许往前走 */
      t += 5000;                       /* 第 2 发超时，放行第 3 发 */
      lp.tick(60);
      CHECK(loads.length === 3, "在途超时后要放行，不能永久卡死停更");
      loads[2].ok();                   /* 第 3 发（新）先回来 */
      CHECK(shown.length === 2 && shown[1] === "F60", "新帧应上屏");
      loads[1].ok();                   /* 第 2 发（旧）后到 */
      CHECK(shown.length === 2,
            "迟到的旧帧必须丢掉（实际上屏 " + shown.length + " 次）—— " +
            "上屏会让画面倒退一帧再跳回来，这正是肉眼看到的\"抽一下\"");
      CHECK(lp.stats().dropped === 1, "丢弃的迟到帧要计数（实际 " + lp.stats().dropped + "）");

      /* ⑤ 加载失败也要放行，否则一次 404 就永久停更 */
      const lp2 = FL.makeFrameLoop({
        now: () => 0, url: () => "X",
        load: (u, ok, fail) => { lp2._f = fail; },
        show: () => {},
      });
      lp2.tick(100); lp2._f();
      CHECK(lp2.tick(100) === true, "上一发失败后要能继续发（否则一次网络错误就黑屏）");
    }

    /* 源码层面兜一道：别哪天又改回写死的 100ms 轮询 */
    const tjs2 = fs.readFileSync(path.join(WEB, "test.js"), "utf8");
    CHECK(/ZFrameLoop\.makeFrameLoop/.test(tjs2), "test.js 要走 frameLoop，不许自己再写一套");
    CHECK(!/setInterval\(\(\) => \{ if \(!suiteRunning\) refresh\(\); \}, 100\)/.test(tjs2),
          "不许退回 setInterval(refresh, 100) 那版无保护的刷新");
  }

  SECTION("T62.1 产品视图：气泡与贴身输入条独立于测试台");
  {
    const html = fs.readFileSync(path.join(WEB, "product.html"), "utf8");
    const js = fs.readFileSync(path.join(WEB, "product.js"), "utf8");
    const css = fs.readFileSync(path.join(WEB, "product.css"), "utf8");
    const cp = JSON.parse(fs.readFileSync(path.join(WEB, "product_copy.json"), "utf8"));
    const mk = fs.readFileSync(path.join(WEB, "..", "Makefile"), "utf8");
    CHECK(/product\.css/.test(html) && /product\.js/.test(html), "产品视图应有独立样式与逻辑");
    CHECK(!/app\.js|components\/chat\.js|layout\.json/.test(html), "产品视图不能复用测试台内核/聊天卡片");
    CHECK(/id=\"conversation\"/.test(html) && /class=\"dock\"/.test(html), "页面必须有气泡区域和贴身输入条");
    CHECK(/\/api\/chat\?/.test(js) && /\/api\/context\.json\?reset=1/.test(js), "真聊和清空上下文两条链路必须保留");
    CHECK(/history_sent/.test(js) && /turns_held/.test(js) && /route_reasons/.test(js), "展开详情必须保留多轮、隐私与人话路由理由");
    CHECK(/\/api\/action\?id=think/.test(js) && /\/api\/action\?id=talk/.test(js), "发送/回复要联动立绘动作");
    CHECK(!!cp.sensitive && !!cp.dry && !!cp.route_reasons.default_local, "用户文案与路由理由翻译必须在数据文件");
    CHECK(/\.dock/.test(css) && /\.bubble/.test(css), "产品视图样式必须形成输入条与对话气泡，而非侧栏卡片");
    CHECK(/node tests\/test_product\.js/.test(mk), "产品视图行为测试必须接进 make web-test，不能只留本地脚本");
  }

  console.log("");
  console.log(fail === 0
    ? "通过 " + pass + " 项，失败 0 项"
    : "通过 " + pass + " 项，失败 " + fail + " 项");
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
