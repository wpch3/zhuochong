/* 舞台交互：把立绘最后三个「点不到」的能力接出来
 *
 *   /api/hover?x=&y=&in=   鼠标靠近时角色看过来（zpet_hover 内部换算视线，比直接写 gaze 更接近真实桌宠）
 *   /api/region?x=&y=      命中测试：指到哪个区域、点下去会触发什么动作、该用什么光标
 *   /api/speak?id= / ?stop=1   台词 + 口型包络（39 条台词在 characters/<c>/voice/lipsync/）
 *
 * 坐标契约（踩过坑，别改）：这三个端点吃的都是**引擎帧缓冲坐标**，
 * 其尺寸就是 info.frame_w/frame_h（= 画布 × pet scale）。
 * 既不是画布坐标（848x1360），也不是屏幕像素，更不是 img.naturalWidth
 * —— 图片尺寸是画布 × 画质档 s%，和帧缓冲是两回事。
 * C 侧 zrig_region_at 会把它再换回画布坐标去比 rect，并且**要求该点是不透明像素**，
 * 所以透明的边角不会响应，这是设计如此。
 */
ZC.register({
  id: "interact",
  title: "舞台交互",

  async mount(host, root) {
    this.host = host;
    this.hoverOn = false;
    this.probeOn = true;
    this.tool = 0;
    this.lines = [];
    this.lineIdx = 0;
    this.last = { region: "", action: "", fx: 0, fy: 0 };
    this.lip = { active: false, id: "", level: 0, remain: 0 };

    const c = host.card("舞台交互", "hover · 区域 · 台词");
    root.appendChild(c.box);
    this.body = c.body;

    await this.reload();
    this.bindStage();
  },

  async reload() {
    try {
      this.info = await this.host.api("/api/info.json");
    } catch (e) { this.info = {}; }
    await this.loadLines();
  },

  /* ---------------- 台词清单 ---------------- */
  async loadLines() {
    try {
      const js = await this.host.api("/voice_manifest.json");
      /* speak 的 id 是 <line>_<variant>（对应 voice/lipsync/<id>.json），
         manifest 里没写 variant 的按 base0 算 —— 生成器就是这么命名的 */
      this.lines = (js.lines || []).map((l) => ({
        id: l.id + "_" + (l.variant || "base0"),
        text: l.text || "",
      }));
    } catch (e) {
      this.lines = [];
    }
    this.render();
  },

  /* ---------------- 界面 ---------------- */
  render() {
    const host = this.host;
    this.body.textContent = "";

    /* —— 开关 —— */
    const sw = host.el("div", "chips");
    const mk = (label, on, fn) => {
      const b = host.el("button", "btn small" + (on ? " active" : ""), label);
      b.addEventListener("click", fn);
      sw.appendChild(b);
      return b;
    };
    mk(this.hoverOn ? "视线跟随中" : "视线跟随鼠标", this.hoverOn, () => {
      this.hoverOn = !this.hoverOn;
      if (!this.hoverOn) this.send("/api/hover", { x: 0, y: 0, in: 0 });
      this.render();
    });
    mk(this.probeOn ? "区域探针开" : "区域探针关", this.probeOn, () => {
      this.probeOn = !this.probeOn;
      const img = this.stageImg();
      if (img && !this.probeOn) img.style.cursor = "";
      this.render();
    });
    mk(this.tool ? "工具：锤子" : "工具：手", !!this.tool, () => {
      this.tool = this.tool ? 0 : 1;
      this.render();
    });
    this.body.appendChild(sw);

    this.body.appendChild(host.el("p", "hint",
      "把鼠标移到左边的立绘上。区域命中要求那一点是不透明像素，所以透明边角不响应。"));

    /* —— 探针读数 —— */
    const L = this.last;
    this.body.appendChild(host.el("p", "mono",
      L.region
        ? "指向 " + L.region + " → " + L.action + "　帧(" + L.fx + "," + L.fy + ")"
        : "指向 —　（移到立绘上看读数）"));

    /* —— 区域一览 —— */
    const info = this.info || {};
    const regs = info.regions || [];
    if (regs.length) {
      const rowr = host.el("div", "chips");
      regs.forEach((g) => {
        const rid = g.id || g;
        const b = host.el("button", "btn small" + (L.region === rid ? " active" : ""),
                          rid + (g.action ? "→" + g.action : ""));
        b.addEventListener("click", () => this.pokeRegion(g));
        rowr.appendChild(b);
      });
      this.body.appendChild(rowr);
      this.body.appendChild(host.el("p", "mono", regs.map(
        (g) => g.id + " [" + (g.rect || []).join(",") + "]").join("　")));
    }

    /* —— 台词 + 口型 —— */
    this.body.appendChild(host.el("p", "hint", "台词口型（" + this.lines.length + " 条）"));
    if (this.lines.length) {
      const sel = host.el("select", "");
      this.lines.forEach((l, i) => {
        const o = host.el("option", "", l.id + "　" + l.text);
        o.value = String(i);
        if (i === this.lineIdx) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener("change", () => { this.lineIdx = Number(sel.value) || 0; });
      this.body.appendChild(sel);

      const rows = host.el("div", "chips");
      const play = host.el("button", "btn small primary", "播放口型");
      play.addEventListener("click", () => this.speak());
      const stop = host.el("button", "btn small", "停止");
      stop.addEventListener("click", () => this.send("/api/speak", { stop: 1 }));
      rows.appendChild(play);
      rows.appendChild(stop);
      this.body.appendChild(rows);

      /* 口型电平：光看嘴分不出是不是真在动，这条给个数 */
      const m = host.el("div", "meter");
      this.fill = host.el("div", "meter-fill");
      this.fill.style.width = Math.round(this.lip.level * 100) + "%";
      m.appendChild(this.fill);
      this.body.appendChild(m);
      this.body.appendChild(host.el("p", "mono",
        this.lip.active
          ? "播放中 " + this.lip.id + "　电平 " + this.lip.level.toFixed(3)
            + "　剩余 " + this.lip.remain.toFixed(2) + "s"
          : "口型空闲"));
    }
  },

  /* ---------------- 舞台绑定 ---------------- */
  stageImg() {
    return document.querySelector("#slot-stage img, .stage img");
  },

  bindStage() {
    const img = this.stageImg();
    if (!img || this._bound) return;
    this._bound = true;

    this._mm = (ev) => {
      const p = this.toFrame(img, ev);
      if (!p) return;
      if (this.hoverOn) this.send("/api/hover", { x: p.x, y: p.y, in: 1 });
      if (this.probeOn) this.probe(img, p);
    };
    this._ml = () => {
      if (this.hoverOn) this.send("/api/hover", { x: 0, y: 0, in: 0 });
    };
    img.addEventListener("mousemove", this._mm);
    img.addEventListener("mouseleave", this._ml);
  },

  /* 屏幕坐标 → 引擎帧缓冲坐标。
     这里**必须**用 info.frame_w/h，不能用 img.naturalWidth：
       · img 的尺寸 = 画布 × 画质档 s%（stage.js 按网速在 40/55/100 之间切）
       · 引擎帧缓冲 fb 的尺寸 = 画布 × pet scale（/api/scale 改的那个）
     两者只有在 s% 恰好等于 scale 时才相等。region/poke/hover 在 C 侧都是按 fb
     换算回画布的（zrig_region_at: fx = x * fb->w / cw），传错坐标系就会整体点偏。 */
  frameSize() {
    const info = this.info || {};
    return { w: info.frame_w || 466, h: info.frame_h || 748 };
  },

  toFrame(img, ev) {
    const r = img.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    const f = this.frameSize();
    return {
      x: Math.round((ev.clientX - r.left) / r.width * f.w),
      y: Math.round((ev.clientY - r.top) / r.height * f.h),
    };
  },

  async probe(img, p) {
    if (this._probing) return;            /* 鼠标事件比请求快得多，不节流会堆成几百个 */
    this._probing = true;
    try {
      const d = await this.host.api("/api/region", { x: p.x, y: p.y });
      const changed = d.region !== this.last.region;
      this.last = { region: d.region || "", action: d.action || "", fx: p.x, fy: p.y };
      img.style.cursor = d.cursor === "hand" ? "pointer" : "default";
      if (changed) this.render();
    } catch (e) { /* 探针失败不该影响别的 */ }
    this._probing = false;
  },

  /* 点区域按钮：拿该区域矩形的中心去 poke，等价于在立绘上点一下 */
  /* 点区域按钮 = 拿 info 报来的 rect 中心换算成帧坐标再 poke。
     rect 是画布坐标，帧坐标 = 画布 × (帧宽/画布宽)，别直接拿画布坐标丢给 /api/poke。 */
  async pokeRegion(g) {
    const info = this.info || {};
    const f = this.frameSize();
    const fw = f.w, fh = f.h;
    const rect = g && g.rect;
    let x = fw * 0.5, y = fh * 0.3;
    if (rect && rect.length === 4) {
      const cw = info.canvas_w || 848, ch = info.canvas_h || 1360;
      x = (rect[0] + rect[2] / 2) / cw * fw;
      y = (rect[1] + rect[3] / 2) / ch * fh;
    }
    await this.send("/api/poke", {
      x: Math.round(x), y: Math.round(y), tool: this.tool,
    });
    this.host.refresh();
  },

  async speak() {
    const l = this.lines[this.lineIdx];
    if (!l) return;
    await this.send("/api/speak", { id: l.id });
  },

  send(path, q) {
    return this.host.api(path, q).catch(() => ({}));
  },

  /* 口型实时读数走 speech.json 的推送，不另开轮询 */
  onSpeech(d) {
    const ls = (d && d.lipsync) || {};
    const act = !!ls.active;
    const lv = Number(ls.level) || 0;
    const was = this.lip;
    this.lip = { active: act, id: ls.id || "", level: lv, remain: Number(ls.remain) || 0 };
    if (this.fill) this.fill.style.width = Math.round(lv * 100) + "%";
    /* 只在开始/结束时重画整块，播放中只动电平条，免得每 400ms 重建一次 DOM */
    if (act !== was.active) this.render();
  },

  /* scale 一改，帧缓冲尺寸就变，坐标换算要跟着走；区域表也可能随 rig 重载而变 */
  onInfo(d) {
    if (!d) return;
    const old = this.info || {};
    this.info = d;
    if (old.frame_w !== d.frame_w || old.frame_h !== d.frame_h
        || (old.regions || []).length !== (d.regions || []).length) {
      this.render();
    }
  },

  destroy() {
    const img = this.stageImg();
    if (img) {
      if (this._mm) img.removeEventListener("mousemove", this._mm);
      if (this._ml) img.removeEventListener("mouseleave", this._ml);
      img.style.cursor = "";
    }
    this._bound = false;
  },
});
