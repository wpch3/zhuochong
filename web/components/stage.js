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
    this.img = img; this.wrap = wrap; this.bubble = bubble; this.bubbleText = bubbleText;

    img.addEventListener("click", (ev) => this.poke("auto", ev));

    /* ---- 帧循环（含画质自适应）----
       ⚠ 2026-10-15 实测修正（用户报"动作时脸部模糊 / 点击时脸部轻微扭曲"）：
       老代码固定请求 /api/frame.png?s=<档位>，自动档从 60% 起步，于是浏览器
       拿到的是 279x448 的图，再被 CSS 放大到 ~680px 高显示 —— 糊的是这一步，
       不是引擎。量化：同样显示成 424x680，引擎原生渲染眼区锐度 1641，
       先渲染成 466x748 再 bilinear 缩放只剩 850（−48%）。而引擎内部，
       所有动作相对 idle 的锐度差都在 ±11% 的噪声里（嘴鼻区 idle −7.4% /
       clicked −7.0% / stroke −10.6%），即"动作让画面变糊"并不存在。
       另外 tuneQuality 换档会连带改变图片的**固有尺寸**，而 #pet 只写了
       max-height，于是档位一跳立绘就跟着变大变小 —— 用户两张截图裙宽
       155px(=s75 档) 对 147px 就是这么来的，看上去像"脸被轻微拉扯"。

       现在：显示尺寸由 fitDisplay() 显式钉死（跟画质档无关），请求的分辨率
       按"显示尺寸 × devicePixelRatio"算，正常情况下浏览器 1:1 直贴不重采样。*/
    /* ★ 本地模式：一律不降级。
       降分辨率 / 降帧率这套只有一个存在理由——沙箱预览要把每帧 PNG 经 HTTP
       送到远端浏览器（实测 scale 1.0 时编码+传输 82ms，比渲染的 60ms 还贵）。
       在本机跑的时候这段开销根本不存在，用户要的是"放大到整个桌面依然清晰"，
       任何自动降级都是帮倒忙（2026-10-15 用户明确要求：本地必须正常分辨率和帧率）。
       判据用 hostname：localhost / 127.0.0.1 / [::1] / file: 都算本地；
       沙箱预览域名（*.e2b.app 之类）走远程策略。 */
    this.isLocal = this.isLocalHost(
      (typeof window !== "undefined" && window.location && window.location.hostname) || null,
      (typeof window !== "undefined" && window.location && window.location.protocol) || null);
    this.QUALITY_SCALES = this.isLocal ? [1.0] : [0.5, 0.65, 0.8, 1.0];
    this.qualityMode = "auto";
    this.qualityIdx = this.QUALITY_SCALES.length - 1;  /* 自动档从"原生清晰"起步，卡了再降 */
    this.frameMs = 0;
    this.failures = 0;
    /* 本地不设 12fps 的保守上限，直接按机器能力跑 */
    this.minInterval = this.isLocal ? 1000 / 60 : 1000 / 12;
    this.interval = this.minInterval;
    this.alive = true;
    this.nativePct = 100;
    host.on("quality", (mode) => { this.qualityMode = mode; this.frameMs = 0; });
    this.fitDisplay();
    if (typeof ResizeObserver === "function") {
      this.ro = new ResizeObserver(() => this.fitDisplay());
      this.ro.observe(wrap);
    } else if (typeof window !== "undefined" && window.addEventListener) {
      window.addEventListener("resize", () => this.fitDisplay());
    }
    this.scheduleFrame();
  },

  /* 这台机器上跑的页面算不算"本地"。抽成独立函数是为了能单测——
     判定写在 mount 里的话，测试拿不到不同 hostname 的分支。
     location 读不到时按**远程**处理（保守：远程策略只是会降级，不会坏）。 */
  isLocalHost(hostname, protocol) {
    if (protocol === "file:") return true;
    if (hostname === null || hostname === undefined) return false;
    return hostname === "localhost" || hostname === "127.0.0.1"
        || hostname === "::1" || hostname === "[::1]";
  },

  /* 把立绘的显示尺寸钉成固定值，并算出"1:1 不重采样"需要的渲染百分比。
     钉死尺寸是为了：画质档变化时立绘不会忽大忽小（老代码会）。 */
  fitDisplay() {
    const img = this.img;
    if (!img) return 100;
    const info = (this.host && this.host.info && this.host.info()) || {};
    const fw = info.frame_w || img.naturalWidth || 466;
    const fh = info.frame_h || img.naturalHeight || 748;
    const wrap = this.wrap || img.parentNode || img.parent;
    const availW = (wrap && wrap.clientWidth ? wrap.clientWidth : fw) - 8;
    /* 远程预览钉在 680（与 app.css 的 #pet max-height 一致，省带宽）；
       本地要能放大到整个桌面，所以吃满视口高度，并解开 CSS 的 max-height。 */
    const vh = (typeof window !== "undefined" && window.innerHeight) || 680;
    const availH = this.isLocal ? Math.max(680, vh - 24) : 680;
    if (this.isLocal) img.style.maxHeight = "none";
    let h = Math.min(availH, fh);
    if (availW > 0 && h * (fw / fh) > availW) h = availW * (fh / fw);
    h = Math.max(120, Math.round(h));
    const w = Math.round(h * (fw / fh));
    img.style.height = h + "px";
    img.style.width = w + "px";
    const dpr = (typeof window !== "undefined" && window.devicePixelRatio) || 1;
    /* 服务端 s 是"相对引擎帧的百分比"，上限 100（见 main_headless.c 的钳位） */
    this.nativePct = Math.max(25, Math.min(100, Math.ceil(h * dpr / fh * 100)));
    return this.nativePct;
  },

  currentQuality() {
    if (this.qualityMode !== "auto") return parseInt(this.qualityMode, 10);
    const k = this.QUALITY_SCALES[this.qualityIdx];
    return Math.max(25, Math.min(100, Math.round(this.nativePct * k)));
  },

  /* 卡的时候先掉**帧率**，掉到 6fps 还不够才掉分辨率。
     桌宠这种画面，"清晰的 8fps"比"糊的 12fps"好看得多；而且掉分辨率是用户
     肉眼最先注意到的退化（2026-10-15 报的"模糊"就是老代码一上来就掉到 60%）。 */
  tuneQuality() {
    if (this.qualityMode !== "auto") return;
    if (this.isLocal) return;                /* ★ 本地永不降级 */
    const SLOW = 220, FAST = 90, FLOOR_MS = 1000 / 6;
    if (this.frameMs > SLOW) {
      if (this.minInterval < FLOOR_MS) this.minInterval = Math.min(FLOOR_MS, this.minInterval * 1.35);
      else if (this.qualityIdx > 0) this.qualityIdx--;
    } else if (this.frameMs < FAST) {
      if (this.qualityIdx < this.QUALITY_SCALES.length - 1) this.qualityIdx++;
      else if (this.minInterval > 1000 / 12) this.minInterval = Math.max(1000 / 12, this.minInterval / 1.35);
    }
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
          this.interval = Math.max(this.minInterval, this.frameMs * 0.2);
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

  /* info 里才有权威的 frame_w/frame_h（画质档不影响它们），拿到就重算一次显示尺寸 */
  onInfo(d) {
    if (!d || !this.img) return;
    if (d.frame_h && d.frame_h !== this.lastFrameH) {
      this.lastFrameH = d.frame_h;
      this.fitDisplay();
    }
  },

  onSpeech(d) {
    const b = this.bubble;
    if (!d.line) { b.hidden = true; return; }
    this.bubbleText.textContent = "「" + d.line + "」";
    b.hidden = false;
    clearTimeout(this.bubbleTimer);
    this.bubbleTimer = setTimeout(() => { b.hidden = true; }, 4500);
  },

  destroy() {
    this.alive = false;
    clearTimeout(this.timer);
    clearTimeout(this.bubbleTimer);
    if (this.ro) { this.ro.disconnect(); this.ro = null; }
  },
});
