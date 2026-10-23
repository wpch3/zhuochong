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
    this.bubbleSeq = null;   /* 上一次显示的台词序号，见 onSpeech */

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
    /* ★★★ 2026-10-23 第四十八问：远程上限从 12fps 提到 **30fps**。
       用户问「Live2D 推荐多少帧、怎么提高」。查官方口径（全部落在
       docs/REFERENCE_NOTES.md 第六十一批）：
         · cybernoids FAQ「一个模型最低 **30FPS 以上**」是性能目标线；
         · nizima LIVE 播放器把帧率拆成 Drawing FPS / Physics FPS 两档，
           各 30/60；物理演算默认 60（Cubism 5.0 起）；
         · 官方动作数据通常按 30fps 定义，60fps 环境靠插值补帧。
       我们的物理侧已经是 60Hz 固定步长（zrig.c ZRIG_PHYS_FPS），
       短板在**取帧侧**：这里写死了 12fps。
       实测服务端单帧成本（直连 127.0.0.1:5176，每档 12 次取中位）：
         s25 18.9ms/22.2KB   s40 22.3ms/48.9KB   s50 21.7ms/71.3KB
         s65 26.1ms/111.9KB  s80 30.0ms/161.2KB  s100 32.8ms/240.4KB
       ⇒ 即使原生分辨率也只要 32.8ms，30fps 服务端给得起；12fps 纯属
       客户端保守。慢链路由 tuneQuality() 往下退（封底 10fps）。 */
    this.minInterval = this.isLocal ? 1000 / 60 : 1000 / 30;
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

  /* 卡的时候怎么退、顺的时候怎么回。
     ★★★ 2026-10-23 第四十八问重排了这条阶梯。
     老版是「先把帧率一路掉到 6fps，还不够才掉分辨率」—— 那是 12fps 上限
     时代的权衡（"清晰的 8fps 比糊的 12fps 好看"）。现在上限是 30fps，
     同一句话就反过来了：**30fps 掉到 20fps 肉眼几乎无感，而分辨率一掉
     立刻就看出来糊**，所以要先在 30fps 这一档上省带宽（掉一级分辨率），
     再考虑动帧率；而且绝不掉到 10fps 以下 —— 官方的性能底线就是 30fps，
     10fps 已经是"卡顿"区（note.com/chekiarisato：10~15 卡顿 / 24~30 自然）。
     顺序（慢）：① 分辨率退一级 → ② 20fps → ③ 分辨率退到底 → ④ 10fps 封底
     顺序（快）：① 先把帧率加回 30fps → ② 再把分辨率加回原生
     本地永不降级（2026-10-15 用户明确要求）。 */
  tuneQuality() {
    if (this.qualityMode !== "auto") return;
    if (this.isLocal) return;                /* ★ 本地永不降级 */
    const SLOW = 220, FAST = 90;
    const CEIL_MS = 1000 / 30, KEEP_MS = 1000 / 20, FLOOR_MS = 1000 / 10;
    if (this.frameMs > SLOW) {
      if (this.minInterval <= CEIL_MS && this.qualityIdx > 1) this.qualityIdx--;
      else if (this.minInterval < KEEP_MS) this.minInterval = KEEP_MS;
      else if (this.qualityIdx > 0) this.qualityIdx--;
      else if (this.minInterval < FLOOR_MS) this.minInterval = FLOOR_MS;
    } else if (this.frameMs < FAST) {
      if (this.minInterval > CEIL_MS) {
        this.minInterval = Math.max(CEIL_MS, this.minInterval / 1.35);
      } else if (this.qualityIdx < this.QUALITY_SCALES.length - 1) {
        this.qualityIdx++;
      }
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

  /* 气泡只认 seq：seq 没变就什么都不做。
     以前这里每次轮询（~80ms）都 clearTimeout 再重设 4500ms，而 /api/speech.json 的
     line 是"最后说过的那句"、会一直返回同一句，于是隐藏计时被无限推后 ——
     气泡**永远不会消失**（G105）。line 为空则立刻收掉。 */
  onSpeech(d) {
    const b = this.bubble;
    const seq = d && typeof d.seq === "number" ? d.seq : null;
    if (seq !== null && seq === this.bubbleSeq) return;   /* 还是同一句，别碰计时器 */
    this.bubbleSeq = seq;
    clearTimeout(this.bubbleTimer);
    if (!d || !d.line) { b.hidden = true; return; }
    this.bubbleText.textContent = "「" + d.line + "」";
    b.hidden = false;
    /* age 是这句话在引擎侧已经存在的秒数：刚开页面时接上一句说了很久的台词，
       应该按它剩下的时间收，而不是从头再给 4.5 秒。 */
    const age = d && typeof d.age === "number" && d.age > 0 ? d.age : 0;
    const left = Math.max(300, 4500 - age * 1000);
    this.bubbleTimer = setTimeout(() => { b.hidden = true; }, left);
  },

  destroy() {
    this.alive = false;
    clearTimeout(this.timer);
    clearTimeout(this.bubbleTimer);
    if (this.ro) { this.ro.disconnect(); this.ro = null; }
  },
});
