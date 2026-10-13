/* 底栏：引擎说明 + 画质档位 + fps/流量 + 连接状态。 */
"use strict";
ZC.register({
  id: "statusbar",
  title: "状态栏",
  mount(host, root, opts) {
    this.host = host;
    const bar = host.el("div", "footer-inner");
    bar.appendChild(host.el("span", null,
      opts.note || "引擎：C11 数据驱动立绘（rig.json）｜界面：web/（组件 + layout.json，改界面不动 C 代码）"));

    const qwrap = host.el("span", "mono", "画质 ");
    this.quality = host.el("select");
    [["auto", "自动"], ["50", "流畅 50%"], ["60", "均衡 60%"], ["75", "清晰 75%"], ["100", "原始 100%"]]
      .forEach(([v, t]) => {
        const o = host.el("option", null, t);
        o.value = v;
        this.quality.appendChild(o);
      });
    this.quality.title = "远程预览是按帧传 PNG 的，画质越高越吃带宽";
    this.quality.addEventListener("change", () => host.emit("quality", this.quality.value));
    qwrap.appendChild(this.quality);
    bar.appendChild(qwrap);

    this.fps = host.el("span", "mono", "—");
    this.conn = host.el("span", "mono", "连接中…");
    bar.appendChild(this.fps);
    bar.appendChild(this.conn);
    root.appendChild(bar);

    this.count = 0; this.at = Date.now(); this.lastBytes = 0; this.lastQ = 60;
    host.on("frame", (f) => this.onFrame(f));
    host.on("conn", (ok) => this.setConn(ok));
    if (typeof document !== "undefined" && document.addEventListener) {
      document.addEventListener("visibilitychange", () => this.setConn(!document.hidden));
    }
  },
  onFrame(f) {
    this.count++;
    if (f.bytes) this.lastBytes = f.bytes;
    if (f.quality) this.lastQ = f.quality;
    const now = Date.now();
    if (now - this.at >= 1000) {
      this.fps.textContent = this.count + " fps · " + Math.round(this.lastBytes / 1024)
                           + " KB/帧 · " + this.lastQ + "%";
      this.count = 0;
      this.at = now;
    }
  },
  setConn(ok) {
    this.conn.textContent = ok ? "已连接引擎" : "引擎无响应，重试中…";
    this.conn.style.color = ok ? "var(--blue)" : "var(--pink-deep)";
  },
});
