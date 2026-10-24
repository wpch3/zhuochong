/* 装扮（T46.4）：发型 / 兜帽 / 猫尾 / 眼高光的用户开关。

   和"立绘调试台"的区别：调试台把 rig.json 里的档位按**英文 id** 原样铺出来给我自己验
   引擎；这块面板是给用户用的 —— 中文名、成对的开关语义、还有"选了就记住"。

   档位表仍然从 /api/info.json 的 poses 读，不在前端写死：
   rig.json 新加一档，这里会自动多出一个按钮（名字没登记就退回英文 id，不会漏掉）。

   持久化：引擎目前不存外观状态（开进程就回默认档），所以记在浏览器 localStorage，
   每次面板挂载时把存下来的档位重新打一遍 /api/pose。
   说明：这是**前端侧**持久化，换浏览器不跟随；引擎侧的状态落盘等 T46.6 做桌面端配置时统一上。 */
"use strict";
ZC.register({
  id: "dressup",
  title: "装扮",

  KEY: "zc.dressup.v1",

  /* 中文名表：组 id → { name: 组名, 档位 id: 档位名 }。
     `extra` 列的是引擎支持、但 /api/info.json 的 entries 里不会出现的档
     （entries 只列"有部件的档"，整组关掉用的 none 不在里面）。
     兜帽故意不给 none：那一档会把呆毛和猫耳一起吞掉，不是用户要的"摘下"。 */
  NAMES: {
    hairstyle: {
      name: "发型", order: 0, extra: ["none"],
      none: "短发（原装）", long: "长发", twin: "双马尾", pony: "马尾",
    },
    hood_pose: {
      name: "兜帽", order: 1,
      down: "摘下", up: "戴上",
    },
    tail_pose: {
      name: "猫尾", order: 2,
      /* 空串 = 四条尾巴全隐藏，和 hairstyle 的空档 = 短发同一套机制。
         「兽耳娘 关」会把它打到这一档。 */
      extra: [""], "": "收起",
      relaxed: "自然", up: "竖起", puff: "炸毛", tuck: "夹起",
    },
    eye_hl_style: {
      name: "眼高光", order: 3,
      round: "圆形", star: "星形",
    },
  },

  /* 参数开关：不是互斥档位，而是直接把若干个 0/1 参数一起推给引擎。
     兽耳娘模式就是这种形状 —— 猫耳(左/右)和猫尾分属三个参数、
     又分别挂在不同的层和物理链上，但对用户来说是**一个**选择。
     用户 2026-10-19 原话：「猫耳和猫尾的动物娘模式不能关闭吗？」
     —— 开关引擎里一直有（ParamAccEarL/R、ParamAccTailCat，默认都是 1），
     只是这块面板只铺 poses，没有铺 params，所以界面上够不着。 */
  SWITCHES: [{
    id: "kemonomimi",
    name: "兽耳娘",
    /* 猫耳是两个 0/1 参数；猫尾不是参数而是一个 pose 组（自然/竖起/炸毛/夹起），
       它的"收起"就是把档位设成空串 —— 和 hairstyle 的空档 = 短发同一套机制。
       所以这个开关要同时走 /api/param 和 /api/pose 两条路。 */
    params: ["ParamAccEarL", "ParamAccEarR"],
    poses: { tail_pose: "relaxed" },
    on: "开（猫耳+猫尾）",
    off: "关（纯人类）",
    hint: "关掉之后猫耳和猫尾一起收起来；两者是同一个\u201c设定\u201d，不拆开给两个开关。再打开时猫尾回到\u201c自然\u201d。",
  }],

  async mount(host, root, opts) {
    this.host = host;
    const c = host.card(opts.title || "装扮", "外观");
    this.body = c.body;
    root.appendChild(c.box);
    this.pending = false;
    await this.reload(true);
  },

  /* 读存档。坏掉的 JSON 当没存过，不要让一条脏数据把整块面板打黑。 */
  load() {
    try { return JSON.parse(localStorage.getItem(this.KEY) || "{}") || {}; }
    catch (e) { return {}; }
  },
  save(g, id) {
    const s = this.load();
    s[g] = id;
    try { localStorage.setItem(this.KEY, JSON.stringify(s)); } catch (e) { /* 隐私模式会抛，忽略 */ }
  },

  async reload(restore) {
    const host = this.host;
    try {
      this.info = await host.api("/api/info.json");
    } catch (e) {
      this.body.innerHTML = "";
      this.body.appendChild(host.el("p", "hint", "取不到立绘数据：" + e.message));
      return;
    }
    try {
      const pj = await host.api("/api/params.json");
      this.params = pj.params || pj;
    } catch (e) { this.params = []; }
    if (restore) await this.restore();
    this.render();
  },

  /* 开关当前是开还是关：取这组参数里**任意一个**的值。
     三个参数理论上同进同退；真要不一致（比如有人在调试台单独拉过），
     以"只要还有一个是开的就算开"为准，这样再点一次「关」能把它们拉齐。 */
  swOn(sw) {
    const m = {};
    (this.params || []).forEach((p) => { m[p.id] = p.value; });
    if ((sw.params || []).some((id) => m[id] !== undefined && Number(m[id]) > 0.5)) return true;
    const cur = {};
    (this.info.poses || []).forEach((g) => { cur[g.id] = g.current; });
    if (Object.keys(sw.poses || {}).some((g) => cur[g])) return true;
    /* 参数和档位都查不到（形态里压根没这些件）就按"开"显示，免得空面板 */
    return (sw.params || []).some((id) => m[id] === undefined);
  },

  async toggle(sw, on) {
    if (this.pending) return;
    this.pending = true;
    try {
      for (const id of (sw.params || [])) {
        await this.host.api("/api/param?id=" + encodeURIComponent(id) + "&v=" + (on ? 1 : 0));
      }
      for (const g of Object.keys(sw.poses || {})) {
        await this.host.api("/api/pose?group=" + g + "&id=" + (on ? sw.poses[g] : ""));
      }
      this.saveSw(sw.id, on);
      const pj = await this.host.api("/api/params.json");
      this.params = pj.params || pj;
      this.info = await this.host.api("/api/info.json");
      this.render();
    } catch (e) { /* 失败在状态栏体现 */ }
    this.pending = false;
  },

  saveSw(id, on) {
    const st = this.load();
    st["sw." + id] = on ? 1 : 0;
    try { localStorage.setItem(this.KEY, JSON.stringify(st)); } catch (e) { /* 隐私模式 */ }
  },

  /* 把上次选的档重新打给引擎。只打和当前档不一样的，省得刷屏。 */
  async restore() {
    const saved = this.load();
    const cur = {};
    (this.info.poses || []).forEach((g) => { cur[g.id] = g.current; });
    let n = 0;
    for (const g of Object.keys(saved)) {
      if (g.indexOf("sw.") === 0) continue;
      if (!(g in cur) || cur[g] === saved[g]) continue;
      try { await this.host.api("/api/pose?group=" + g + "&id=" + saved[g]); n++; } catch (e) { /* 档没了就跳过 */ }
    }
    /* 参数开关也要还原。引擎每次开进程都回默认值（猫耳猫尾默认都是开），
       用户上次关掉了就得替他关回去，否则"关了又自己长出来"。 */
    for (const sw of this.SWITCHES) {
      const want = saved["sw." + sw.id];
      if (want === undefined || this.swOn(sw) === (want === 1)) continue;
      for (const id of (sw.params || [])) {
        try { await this.host.api("/api/param?id=" + encodeURIComponent(id) + "&v=" + want); } catch (e) { /* 参数没了就跳过 */ }
      }
      for (const g of Object.keys(sw.poses || {})) {
        try { await this.host.api("/api/pose?group=" + g + "&id=" + (want ? sw.poses[g] : "")); } catch (e) { /* 组没了就跳过 */ }
      }
      try {
        const pj = await this.host.api("/api/params.json");
        this.params = pj.params || pj;
        this.info = await this.host.api("/api/info.json");
      } catch (e) { /* 保持旧的 */ }
    }
    if (n) {
      try { this.info = await this.host.api("/api/info.json"); } catch (e) { /* 保持旧的 */ }
    }
  },

  async pick(g, id) {
    if (this.pending) return;
    this.pending = true;
    try {
      await this.host.api("/api/pose?group=" + g + "&id=" + id);
      this.save(g, id);
      this.info = await this.host.api("/api/info.json");
      this.render();
    } catch (e) { /* 失败在状态栏体现 */ }
    this.pending = false;
  },

  btnRow(label, items, g, cur) {
    const host = this.host;
    const wrap = host.el("div", "voice-item");
    wrap.appendChild(host.el("span", "id", label));
    const box = host.el("span", "grid");
    items.forEach((it) => {
      const b = host.el("button", it.id === cur ? "btn small active" : "btn small", it.label);
      b.onclick = () => this.pick(g, it.id);
      box.appendChild(b);
    });
    wrap.appendChild(box);
    return wrap;
  },

  render() {
    const host = this.host;
    this.body.innerHTML = "";
    const groups = (this.info.poses || []).slice();
    if (!groups.length) {
      this.body.appendChild(host.el("p", "hint", "这个形态还没有可切换的外观差分。"));
      return;
    }
    /* 名字表里登记过的排前面（按 order），没登记的按原顺序跟在后面 */
    groups.sort((a, b) => {
      const oa = (this.NAMES[a.id] || {}).order, ob = (this.NAMES[b.id] || {}).order;
      return (oa === undefined ? 99 : oa) - (ob === undefined ? 99 : ob);
    });
    groups.forEach((g) => {
      const nm = this.NAMES[g.id] || {};
      const ids = (nm.extra || []).concat(g.entries || []);
      const items = ids.map((id) => ({ id: id, label: nm[id] || id }));
      this.body.appendChild(this.btnRow(nm.name || g.id, items, g.id, g.current));
    });
    /* 参数开关铺在档位后面 */
    this.SWITCHES.forEach((sw) => {
      const on = this.swOn(sw);
      const wrap = host.el("div", "voice-item");
      wrap.appendChild(host.el("span", "id", sw.name));
      const box = host.el("span", "grid");
      [[true, sw.on], [false, sw.off]].forEach((it) => {
        const b = host.el("button", (it[0] === on) ? "btn small active" : "btn small", it[1]);
        b.onclick = () => this.toggle(sw, it[0]);
        box.appendChild(b);
      });
      wrap.appendChild(box);
      this.body.appendChild(wrap);
    });
    const h = host.el("p", "hint",
      "兜帽戴上时会盖住呆毛和猫耳 —— 想看猫耳就点「摘下」。"
      + this.SWITCHES.map((s) => s.hint).join(" ")
      + " 选择记在本机浏览器里，刷新后自动还原。");
    this.body.appendChild(h);
  },

  /* 别人（调试台 / 动作）改了档位时跟着高亮，不重发请求。 */
  onInfo(d) {
    if (!d || !d.poses || !this.info) return;
    const cur = JSON.stringify((this.info.poses || []).map((g) => g.id + "=" + g.current));
    const now = JSON.stringify(d.poses.map((g) => g.id + "=" + g.current));
    if (cur === now) return;
    this.info = d;
    this.render();
  },
});
