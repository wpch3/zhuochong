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
      relaxed: "自然", up: "竖起", puff: "炸毛", tuck: "夹起",
    },
    eye_hl_style: {
      name: "眼高光", order: 3,
      round: "圆形", star: "星形",
    },
  },

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
    if (restore) await this.restore();
    this.render();
  },

  /* 把上次选的档重新打给引擎。只打和当前档不一样的，省得刷屏。 */
  async restore() {
    const saved = this.load();
    const cur = {};
    (this.info.poses || []).forEach((g) => { cur[g.id] = g.current; });
    let n = 0;
    for (const g of Object.keys(saved)) {
      if (!(g in cur) || cur[g] === saved[g]) continue;
      try { await this.host.api("/api/pose?group=" + g + "&id=" + saved[g]); n++; } catch (e) { /* 档没了就跳过 */ }
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
    const h = host.el("p", "hint",
      "兜帽戴上时会盖住呆毛和猫耳 —— 想看猫耳就点「摘下」。选择记在本机浏览器里，刷新后自动还原。");
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
