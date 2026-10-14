/* 立绘调试台（G65）：把立绘底层已经做好、但界面上点不到的能力全部接出来。

   做之前实测过：24 个 API 端点里，界面只用到 9 个。
   46 个参数、7 个表情、7 个口型、互斥差分、视线、眨眼、暂停 —— 底层都有闸门焊死，
   但没有任何入口能点。这个面板补的就是这一段。

   口型表、表情表、差分档位全部从 /api/info.json 读，不在前端硬编码：
   rig.json 改了之后前端要跟着对，否则按钮点下去是 404。 */
"use strict";
ZC.register({
  id: "rig",
  title: "立绘调试台",

  /* 参数按 id 前缀归组。Live2D 官方参数名就是这个前缀规则，
     新参数只要照着命名就会自动落到对的组里。 */
  GROUPS: [
    ["头部朝向", /^ParamAngle/],
    ["眼睛", /^(ParamEye|ParamIris)/],
    ["眉毛", /^ParamBrow/],
    ["嘴", /^ParamMouth/],
    ["脸颊", /^ParamCheek/],
    ["身体", /^(ParamBody|ParamBreath|ParamBase|ParamShoulder)/],
    ["手臂", /^(ParamArm|ParamHand)/],
    ["腿", /^(ParamLeg|ParamFoot)/],
    ["头发 · 裙摆", /^(ParamHair|ParamAhoge|ParamSkirt)/],
  ],

  async mount(host, root, opts) {
    this.host = host;
    this.open = {};           /* 哪几组是展开的 */
    this.pending = false;     /* 拖动时的请求节流：上一个没回来就不发新的 */
    this.paused = false;
    this.gazeOn = false;
    const c = host.card(opts.title || "立绘调试台", "立绘");
    this.body = c.body;
    root.appendChild(c.box);
    await this.reload();
  },

  async reload() {
    const host = this.host;
    try {
      this.info = await host.api("/api/info.json");
      const pj = await host.api("/api/params.json");
      this.params = pj.params || pj;
    } catch (e) {
      this.body.innerHTML = "";
      this.body.appendChild(host.el("p", "hint", "取不到立绘数据：" + e.message));
      return;
    }
    this.render();
  },

  /* 发请求 + 让舞台尽快显示出来。舞台自己在跑 ~12fps 的帧循环，
     所以这里只要把值写进去就行，不用手动推帧。 */
  async send(path) {
    if (this.pending) return;
    this.pending = true;
    try { await this.host.api(path); } catch (e) { /* 失败在状态栏体现 */ }
    this.pending = false;
  },

  btnRow(label, items, onPick, cur) {
    const host = this.host;
    const wrap = host.el("div", "voice-item");
    wrap.appendChild(host.el("span", "id", label));
    const box = host.el("span", "grid");
    items.forEach((it) => {
      const b = host.el("button", "btn small", it.label);
      if (it.id === cur) b.className = "btn small active";
      b.onclick = () => onPick(it.id);
      box.appendChild(b);
    });
    wrap.appendChild(box);
    return wrap;
  },

  render() {
    const host = this.host, info = this.info;
    this.body.innerHTML = "";

    /* ---- 动作 ---- */
    const acts = (info.actions || []).slice();
    /* idle / sleep 不在 /api/info.json 的列表里（一个是默认动作，一个由睡眠状态自动触发），
       但调试台要能手动验证它们，实测 /api/action?id= 两个都认。 */
    ["idle", "sleep"].forEach((x) => { if (acts.indexOf(x) < 0) acts.push(x); });
    this.body.appendChild(this.btnRow("动作",
      acts.map((a) => ({ id: a, label: a })),
      (id) => this.send("/api/action?id=" + id).then(() => this.refreshHead()),
      info.action));

    /* ---- 表情层 ---- */
    const exps = (info.expressions || []).map((e) => ({ id: e.id, label: e.name || e.id }));
    exps.push({ id: "", label: "取消" });
    this.body.appendChild(this.btnRow("表情", exps,
      (id) => this.send(id ? "/api/expression?id=" + id : "/api/expression?off=1")
                  .then(() => this.refreshHead()),
      info.expression));

    /* ---- 口型：点一下按住那个音素，再点同一个松开 ---- */
    const vis = (info.visemes || []).map((v) => ({ id: v, label: v }));
    if (vis.length) {
      this.body.appendChild(this.btnRow("口型", vis, (id) => {
        const same = this.info.viseme === id;
        /* 端点签名是 v=音素 & w=音量，不是 id/v —— 对着 C 侧 qstr 核过 */
        this.send(same ? "/api/viseme?v=off" : "/api/viseme?v=" + id + "&w=1")
            .then(() => this.refreshHead());
      }, info.viseme));
    }

    /* ---- 互斥差分（眼高光形状这类）---- */
    (info.poses || []).forEach((g) => {
      const items = g.entries.map((e) => ({ id: e, label: e }));
      items.push({ id: "none", label: "关掉" });
      this.body.appendChild(this.btnRow(g.id, items,
        (id) => this.send("/api/pose?group=" + g.id + "&id=" + id).then(() => this.refreshHead()),
        g.current));
    });

    /* ---- 开关 ---- */
    const sw = host.el("div", "voice-item");
    sw.appendChild(host.el("span", "id", "开关"));
    const swbox = host.el("span", "grid");
    const mk = (txt, on, fn) => {
      const b = host.el("button", on ? "btn small active" : "btn small", txt);
      b.onclick = fn;
      swbox.appendChild(b);
      return b;
    };
    mk(this.paused ? "已暂停" : "暂停动画", this.paused, () => {
      this.paused = !this.paused;
      this.send("/api/pause?on=" + (this.paused ? 1 : 0)).then(() => this.render());
    });
    mk("眨一下", false, () => this.send("/api/blink?v=1"));
    mk(this.gazeOn ? "视线跟随中" : "视线跟随", this.gazeOn, () => {
      this.gazeOn = !this.gazeOn;
      this.bindGaze();
      this.render();
    });
    mk("参数全复位", false, () => this.send("/api/param?all=1").then(() => this.reload()));
    sw.appendChild(swbox);
    this.body.appendChild(sw);

    /* ---- 形变器输出（只读）：光看图分不出裙摆到底在不在荡，这几个数能直接读 ---- */
    const df = info.deformers || {};
    const dk = Object.keys(df);
    if (dk.length) {
      this.body.appendChild(host.el("p", "mono",
        "形变器 " + dk.map((k) => k + " " + Number(df[k]).toFixed(3)).join("  ")));
    }

    /* ---- 参数 ---- */
    this.body.appendChild(host.el("p", "hint",
      "参数 " + this.params.length + " 个（点组名展开）"));
    const used = {};
    this.GROUPS.forEach(([name, re]) => {
      const list = this.params.filter((p) => re.test(p.id));
      list.forEach((p) => { used[p.id] = 1; });
      if (list.length) this.groupBox(name, list);
    });
    const rest = this.params.filter((p) => !used[p.id]);
    if (rest.length) this.groupBox("其他", rest);
  },

  groupBox(name, list) {
    const host = this.host;
    const head = host.el("button", "btn small",
      (this.open[name] ? "▾ " : "▸ ") + name + " (" + list.length + ")");
    head.onclick = () => { this.open[name] = !this.open[name]; this.render(); };
    this.body.appendChild(head);
    if (!this.open[name]) return;
    const box = host.el("div", "voice-list");
    list.forEach((p) => box.appendChild(this.slider(p)));
    this.body.appendChild(box);
  },

  slider(p) {
    const host = this.host;
    const row = host.el("div", "voice-item");
    row.appendChild(host.el("span", "id", p.label || p.id));
    const sl = host.el("input");
    sl.type = "range";
    sl.min = String(p.min); sl.max = String(p.max);
    sl.step = String((p.max - p.min) / 200);
    sl.value = String(p.value);
    const out = host.el("span", "text", Number(p.value).toFixed(2));
    sl.oninput = () => {
      const v = Number(sl.value);
      out.textContent = v.toFixed(2);
      /* 内建参数（binds=0）走的是渲染器内部通道，不是 bind —— 标出来，
         免得有人以为"调了没反应 = 坏了" */
      this.send("/api/param?id=" + encodeURIComponent(p.id) + "&v=" + v);
    };
    row.appendChild(sl);
    row.appendChild(out);
    if (!p.binds && !p.builtin) {
      row.appendChild(host.el("span", "hint", " 没接任何部件"));
    }
    return row;
  },

  /* 在舞台上移动鼠标 → 视线跟过去。桌宠的标配交互，之前只有 API 没有入口。 */
  bindGaze() {
    const stage = document.querySelector("#slot-stage img, .stage img, canvas");
    if (!stage) return;
    if (!this.gazeOn) {
      if (this._gh) stage.removeEventListener("mousemove", this._gh);
      this._gh = null;
      this.send("/api/gaze?x=0&y=0");
      return;
    }
    this._gh = (ev) => {
      const r = stage.getBoundingClientRect();
      const x = ((ev.clientX - r.left) / r.width) * 2 - 1;
      const y = ((ev.clientY - r.top) / r.height) * 2 - 1;
      this.send("/api/gaze?x=" + x.toFixed(3) + "&y=" + (-y).toFixed(3));
    };
    stage.addEventListener("mousemove", this._gh);
  },

  /* 动作/表情/口型切换后，头部那几行的高亮要跟着变 */
  async refreshHead() {
    try {
      this.info = await this.host.api("/api/info.json");
      this.render();
    } catch (e) { /* 忽略 */ }
  },

  onInfo(d) {
    /* 轮询来的 info 只用来更新形变器读数和高亮，不整块重绘 —— 否则拖滑块会被打断 */
    if (!this.info || this.dragging) return;
    this.info.deformers = d.deformers || this.info.deformers;
  },

  destroy() {
    if (this._gh) {
      const stage = document.querySelector("#slot-stage img, .stage img, canvas");
      if (stage) stage.removeEventListener("mousemove", this._gh);
    }
  },
});
