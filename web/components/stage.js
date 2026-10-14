/* 立绘舞台：帧循环 + 画质自适应 + 点击互动 + 气泡。
   逻辑原样来自重构前的 app.js，只是把"直接操作全局 DOM"换成了"在自己的 slot 里建 DOM"。 */
"use strict";
ZC.register({
  id: "stage",
  title: "立绘舞台",

  mount(host, root, opts) {
    this.host = host;
    const sec = host.el("section", "stage card");

    const bubble = host.el("div", "bubble");
    bubble.hidden = true;
    const bubbleText = host.el("span");
    bubble.appendChild(bubbleText);
    sec.appendChild(bubble);

    const wrap = host.el("div", "pet-wrap");
    const img = host.el("img");
    img.id = "pet";
    img.src = "/api/frame.png";
    img.alt = "小寻的立绘";
    img.draggable = false;
    wrap.appendChild(img);
    sec.appendChild(wrap);

    const quick = host.el("div", "quick");
    const BTNS = opts.buttons || [
      { poke: "head", label: "摸头", cls: "primary" },
      { poke: "body", label: "抚摸" },
      { poke: "feet", label: "点脚" },
      { poke: "hammer", label: "锤击", cls: "warn" },
      { act: "wake", label: "叫醒" },
    ];
    BTNS.forEach((b) => {
      const btn = host.el("button", "btn " + (b.cls || ""), b.label);
      btn.addEventListener("click", () => (b.act === "wake" ? this.wake() : this.poke(b.poke)));
      quick.appendChild(btn);
    });
    sec.appendChild(quick);
    sec.appendChild(host.el("p", "hint",
      opts.hint || "点击立绘任意位置 = 手（头部为摸头，身体为抚摸）；拖动在 Windows 真机上有效。"));

    root.appendChild(sec);
    this.img = img; this.bubble = bubble; this.bubbleText = bubbleText;

    img.addEventListener("click", (ev) => this.poke("auto", ev));

    /* ---- 帧循环（含画质自适应）---- */
    this.QUALITY_STEPS = [50, 60, 75, 100];
    this.qualityMode = "auto";
    this.qualityIdx = 1;
    this.frameMs = 0;
    this.failures = 0;
    this.interval = 1000 / 12;
    this.alive = true;
    host.on("quality", (mode) => { this.qualityMode = mode; this.frameMs = 0; });
    this.scheduleFrame();
  },

  currentQuality() {
    return this.qualityMode === "auto"
      ? this.QUALITY_STEPS[this.qualityIdx]
      : parseInt(this.qualityMode, 10);
  },

  tuneQuality() {
    if (this.qualityMode !== "auto") return;
    if (this.frameMs > 220 && this.qualityIdx > 0) this.qualityIdx--;
    else if (this.frameMs < 90 && this.qualityIdx < this.QUALITY_STEPS.length - 1) this.qualityIdx++;
  },

  scheduleFrame() {
    if (!this.alive) return;
    this.timer = setTimeout(async () => {
      if (!document.hidden) {
        const t0 = performance.now();
        try {
          const url = "/api/frame.png?s=" + this.currentQuality() + "&t=" + Date.now();
          const resp = await fetch(url, { cache: "no-store" });
          const blob = await resp.blob();
          const next = URL.createObjectURL(blob);
          const old = this.img.dataset.blob;
          this.img.src = next;
          if (old) URL.revokeObjectURL(old);
          this.img.dataset.blob = next;
          const dt = performance.now() - t0;
          this.frameMs = this.frameMs ? this.frameMs * 0.7 + dt * 0.3 : dt;
          this.tuneQuality();
          this.host.emit("frame", { bytes: blob.size, quality: this.currentQuality() });
          this.failures = 0;
          /* 上一帧还没到就不要再排队，否则请求会堆成雪球 */
          this.interval = Math.max(1000 / 12, this.frameMs * 0.2);
        } catch (e) {
          this.failures++;
          this.interval = Math.min(2000, 500 * this.failures);
          this.host.emit("conn", false);
        }
      }
      this.scheduleFrame();
    }, this.interval);
  },

  async poke(kind, ev) {
    /* 坐标系：/api/poke 吃的是**引擎帧缓冲**坐标（画布 × pet scale），
       而 this.img 的尺寸是画布 × 画质档 s%（currentQuality 会在 40/55/100 之间切）。
       拿 naturalWidth 换算只在两者碰巧相等时对，画质一变或 /api/scale 一改就整体点偏。
       所以一律按 info.frame_w/h 来。 */
    const info = (this.host.info && this.host.info()) || {};
    const w = info.frame_w || this.img.naturalWidth || 445;
    const h = info.frame_h || this.img.naturalHeight || 1292;
    let x = w * 0.5, y = h * 0.25, tool = 0;
    if (kind === "hammer") { tool = 1; y = h * 0.3; }
    else if (kind === "body") y = h * 0.45;
    else if (kind === "feet") y = h * 0.9;
    if (ev) {   /* 立绘上的点击：按显示比例换算成帧坐标 */
      const rect = this.img.getBoundingClientRect();
      x = (ev.clientX - rect.left) / rect.width * w;
      y = (ev.clientY - rect.top) / rect.height * h;
    }
    await this.host.api("/api/poke", { x: Math.round(x), y: Math.round(y), tool: tool });
    this.host.refresh();
  },

  async wake() {
    await this.host.api("/api/action", { id: "idle" });
    await this.host.api("/api/idle", { s: 0 });
    this.host.refresh();
  },

  onSpeech(d) {
    const b = this.bubble;
    if (!d.line) { b.hidden = true; return; }
    this.bubbleText.textContent = "「" + d.line + "」";
    b.hidden = false;
    clearTimeout(this.bubbleTimer);
    this.bubbleTimer = setTimeout(() => { b.hidden = true; }, 4500);
  },

  destroy() { this.alive = false; clearTimeout(this.timer); clearTimeout(this.bubbleTimer); },
});
