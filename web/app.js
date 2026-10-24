/* web/app.js —— 基础软件的**内核**（G1 主工作区骨架）
 *
 * 这一层只做四件事，业务一行都不写：
 *   1. 组件注册表：组件调 ZC.register({...}) 把自己登记进来；
 *   2. 布局配置：layout.json 说"哪些组件、放在哪个区域、什么顺序、给什么参数"，
 *      内核按它动态加载 components/<id>.js 并挂载 —— **加卡片不用改任何代码**；
 *   3. 主题：themes/<id>.json 是一张 CSS 变量表，直接写到 :root 上；
 *   4. 事件总线 + 统一轮询：info/speech 只轮询一份，广播给所有组件，
 *      省得每个卡片各开一个定时器。
 *
 * 参考（见 docs/REFERENCE_NOTES.md 第十批）：VPet 的 MainPlugin/IMainWindow —— 
 * 插件拿到一个**宿主门面对象**，生命周期是固定的几个钩子，插件之间能互相发现。
 * 这里的 host 就是那个门面，mount/onInfo/onSpeech/destroy 就是那几个钩子。
 *
 * 与引擎的约定：所有请求都走相对路径（/api/*、/media/*），由 C 预览服务
 * 同端口提供，因此不存在跨域，也不写死 localhost 端口。
 */
"use strict";

(function (global) {

  /* ----------------------------------------------------------- 事件总线 */
  function makeBus() {
    const map = new Map();
    return {
      on(evt, fn) {
        if (!map.has(evt)) map.set(evt, new Set());
        map.get(evt).add(fn);
        return () => map.get(evt).delete(fn);
      },
      off(evt, fn) { const s = map.get(evt); if (s) s.delete(fn); },
      emit(evt, data) {
        const s = map.get(evt);
        if (!s) return;
        /* 一个组件抛错不该让别的组件收不到事件 */
        s.forEach((fn) => { try { fn(data); } catch (e) { console.error("[" + evt + "]", e); } });
      },
      count(evt) { return map.has(evt) ? map.get(evt).size : 0; },
    };
  }

  /* ----------------------------------------------------------- 注册表 */
  const registry = new Map();
  const mounted = [];

  function register(def) {
    if (!def || !def.id) throw new Error("组件必须有 id");
    if (typeof def.mount !== "function") throw new Error("组件 " + def.id + " 必须有 mount()");
    if (registry.has(def.id)) throw new Error("组件 id 重复：" + def.id);
    registry.set(def.id, def);
    return def;
  }

  /* ----------------------------------------------------------- DOM 小工具 */
  function el(tag, cls, text) {
    const d = document.createElement(tag);
    if (cls) d.className = cls;
    if (text != null) d.textContent = text;
    return d;
  }

  /* 卡片外壳：标题 + 内容区。组件只管往 body 里填东西，长相统一归内核管。 */
  function card(title, tagText) {
    const box = el("div", "card");
    if (title) {
      const h = el("h2", null, title);
      if (tagText) h.appendChild(el("span", "tag", tagText));
      box.appendChild(h);
    }
    const body = el("div", "card-body");
    box.appendChild(body);
    return { box, body };
  }

  /* ----------------------------------------------------------- 宿主门面 */
  const bus = makeBus();
  const state = {
    info: null, speech: "", usage: { calls: 0, tokens: 0 }, lastSpeechAt: 0,
    layout: null, theme: null,
  };

  const host = {
    bus,
    state,
    el, card,
    on: bus.on, off: bus.off, emit: bus.emit,

    /* 统一的 API 调用口。相对路径，失败时抛错由调用方决定怎么提示。 */
    async api(path, params) {
      let url = path.startsWith("/") ? path : "/api/" + path;
      if (params) {
        const q = new URLSearchParams(params).toString();
        if (q) url += (url.includes("?") ? "&" : "?") + q;
      }
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error(url + " → " + r.status);
      const ct = r.headers.get("content-type") || "";
      return ct.includes("json") ? r.json() : r.text();
    },

    info() { return state.info; },

    /* 组件互相发现（VPet 的"所有三方插件"那条） */
    components() { return mounted.map((m) => ({ id: m.def.id, title: m.def.title || m.def.id })); },
    find(id) { const m = mounted.find((x) => x.def.id === id); return m ? m.def : null; },

    theme() { return state.theme; },
    async setTheme(id) { return applyTheme(id); },

    /* 让组件能主动要一次状态刷新（点完按钮立刻看到变化） */
    refresh() { return pollInfo(); },
  };

  /* ----------------------------------------------------------- 主题 */
  async function applyTheme(id) {
    let vars = {};
    try {
      const r = await fetch("themes/" + id + ".json", { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      vars = d.vars || {};
      state.theme = { id, name: d.name || id, vars };
    } catch (e) {
      console.error("主题加载失败：" + id, e);
      state.theme = { id: null, name: "(默认)", vars: {} };
      return state.theme;
    }
    const root = document.documentElement;
    Object.keys(vars).forEach((k) => {
      root.style.setProperty(k.startsWith("--") ? k : "--" + k, String(vars[k]));
    });
    bus.emit("theme", state.theme);
    return state.theme;
  }

  /* ----------------------------------------------------------- 组件加载 */
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.async = false;                  /* 保序：按 layout 里的顺序执行 */
      s.onload = () => resolve(src);
      s.onerror = () => reject(new Error("组件脚本加载失败：" + src));
      document.head.appendChild(s);
    });
  }

  function mountOne(def, regionEl, opts) {
    const slot = el("div", "slot slot-" + def.id);
    slot.dataset.component = def.id;
    regionEl.appendChild(slot);
    try {
      def.mount(host, slot, opts || {});
      mounted.push({ def: def, el: slot, opts: opts || {} });
      if (typeof def.onInfo === "function") bus.on("info", def.onInfo.bind(def));
      if (typeof def.onSpeech === "function") bus.on("speech", def.onSpeech.bind(def));
    } catch (e) {
      console.error("组件挂载失败：" + def.id, e);
      slot.appendChild(el("div", "err", "组件 " + def.id + " 挂载失败：" + e.message));
    }
  }

  async function boot() {
    let layout;
    try {
      const r = await fetch("layout.json", { cache: "no-store" });
      layout = await r.json();
    } catch (e) {
      document.body.appendChild(el("div", "err", "layout.json 读取失败，界面无法组装：" + e.message));
      return;
    }
    state.layout = layout;
    if (layout.title) document.title = layout.title;
    await applyTheme(layout.theme || "sakura");

    /* 先把 layout 里出现过的组件脚本都拉下来（它们会自行 register） */
    const regions = layout.regions || {};
    const ids = [];
    Object.keys(regions).forEach((rk) => {
      (regions[rk] || []).forEach((item) => {
        const id = typeof item === "string" ? item : item.id;
        if (id && ids.indexOf(id) < 0) ids.push(id);
      });
    });
    for (const id of ids) {
      if (registry.has(id)) continue;
      try { await loadScript("components/" + id + ".js"); }
      catch (e) { console.error(e); }
    }

    /* 再按区域顺序挂载 */
    Object.keys(regions).forEach((rk) => {
      const host_el = document.getElementById("region-" + rk);
      if (!host_el) { console.warn("布局里写了区域 " + rk + "，但页面上没有 #region-" + rk); return; }
      (regions[rk] || []).forEach((item) => {
        const id = typeof item === "string" ? item : item.id;
        const opts = (typeof item === "object" && item.options) ? item.options : {};
        const def = registry.get(id);
        if (!def) {
          console.error("布局引用了未注册的组件：" + id);
          host_el.appendChild(el("div", "err", "缺少组件：" + id));
          return;
        }
        mountOne(def, host_el, opts);
      });
    });

    bus.emit("ready", { components: host.components() });
    startPolling(layout.poll || {});
  }

  /* ----------------------------------------------------------- 统一轮询 */
  async function pollInfo() {
    try {
      const d = await host.api("/api/info.json");
      state.info = d;
      bus.emit("conn", true);
      bus.emit("info", d);
      return d;
    } catch (e) {
      bus.emit("conn", false);
      return null;
    }
  }

  async function pollSpeech() {
    try {
      const d = await host.api("/api/speech.json");
      if (d.line && d.line !== state.speech) {
        state.speech = d.line;
        state.lastSpeechAt = Date.now();
        bus.emit("speech", { line: d.line, fresh: true });
      } else if (state.speech && Date.now() - state.lastSpeechAt > 4000) {
        state.speech = "";
        bus.emit("speech", { line: "", fresh: false });
      }
    } catch (e) { /* 静默：轮询失败不打扰用户 */ }
  }

  function startPolling(cfg) {
    pollInfo();
    pollSpeech();
    setInterval(pollInfo, cfg.info_ms || 600);
    setInterval(pollSpeech, cfg.speech_ms || 400);
  }

  /* ----------------------------------------------------------- 导出 */
  const ZC = { register, host, boot, bus, registry, mounted, applyTheme, el, card, version: "1.0" };
  global.ZC = ZC;
  if (typeof module !== "undefined" && module.exports) module.exports = ZC;   /* 给 node 单测用 */

  if (typeof document !== "undefined" && !global.ZC_NO_AUTOBOOT) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
  }

})(typeof window !== "undefined" ? window : globalThis);
