/* 平台能力总览（G50）：能力 × 供应商矩阵 + 余额口径 + 本地/网络标记。
   数据来自 web/platform.json —— 由 tools/check_platform.py 从 config/ 的契约生成，
   所以"加一种新能力"只是多一份契约文件，这个面板会自动多出一行。 */
"use strict";
ZC.register({
  id: "platform",
  title: "能力与供应商",
  mount(host, root, opts) {
    this.host = host;
    const c = host.card(opts.title || "能力与供应商", "框架");
    this.body = c.body;
    this.body.appendChild(host.el("p", "hint", "读取中…"));
    root.appendChild(c.box);
    this.load(opts);
  },
  async load(opts) {
    const host = this.host;
    let d;
    try {
      d = await host.api("/platform.json");
    } catch (e) {
      this.body.innerHTML = "";
      this.body.appendChild(host.el("p", "hint",
        "platform.json 还没生成：跑一次 python3 tools/check_platform.py"));
      return;
    }
    this.body.innerHTML = "";
    const caps = d.capabilities || [], provs = d.providers || [];

    const sum = host.el("p", "mono",
      caps.length + " 种能力 · " + provs.length + " 个供应商 · 路由策略 " + (d.routing || "—")
      + (d.proxy_enabled ? " · 代理开" : ""));
    this.body.appendChild(sum);

    /* 供应商：本地/网络、是否启用、余额口径 */
    const pbox = host.el("div", "grid");
    provs.forEach((p) => {
      const tag = host.el("span", "chip" + (p.enabled ? " active" : ""),
        p.name + (p.local ? " · 本机" : " · 网络")
        + (p.balance_mode === "none" ? "" : " · 余额:" + p.balance_mode));
      tag.title = p.caps.join(", ");
      if (!p.enabled) tag.style.opacity = "0.5";
      pbox.appendChild(tag);
    });
    this.body.appendChild(pbox);

    /* 能力清单：谁能提供它 */
    const list = host.el("div", "cap-list");
    caps.forEach((cp) => {
      const row = host.el("div", "voice-item");
      row.appendChild(host.el("span", "id", cp.id));
      const who = cp.providers.length
        ? cp.providers.join(" / ")
        : "（待接入）";
      const t = host.el("span", "text", cp.name + " — " + who);
      if (!cp.providers.length) t.style.opacity = "0.55";
      row.appendChild(t);
      list.appendChild(row);
    });
    this.body.appendChild(list);
    this.body.appendChild(host.el("p", "hint",
      "能力和供应商都是 config/ 下的契约文件，加一种新能力不用改代码；密钥只写 secret:// 引用，真实值留在本机。"));
  },
});
