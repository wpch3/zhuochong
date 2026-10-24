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

    /* 网关实时状态（G51）：契约说"谁能做"，网关说"现在实际会走谁"。
       两者不是一回事——契约里写了四家，但没开密钥的都不会被选中。 */
    let gw = null;
    try { gw = await host.api("/api/gateway.json"); } catch (e) { gw = null; }
    if (gw && gw.loaded) {
      const lg = gw.ledger || {};
      this.body.appendChild(host.el("p", "mono",
        "网关：" + gw.routes + " 条路由 · 策略 " + gw.strategy
        + (gw.fallback ? " · 失败可换家" : " · 不换家")
        + " · 已花 " + (lg.spent || 0).toFixed(4)
        + (lg.held ? "（另占用 " + lg.held.toFixed(4) + "）" : "")
        + " · 调用 " + (lg.calls || 0) + " 次"
        + ((lg.failed || 0) ? "，失败 " + lg.failed + " 次" : "")));
    } else if (gw) {
      this.body.appendChild(host.el("p", "hint",
        "网关没加载路由表：跑一次 python3 tools/check_platform.py 生成 config/gateway_routes.json"));
    }
    const pick = {};
    if (gw && gw.caps) gw.caps.forEach((c) => { pick[c.cap] = c; });

    /* 能力清单：谁能提供它 + 现在实际走谁 */
    const list = host.el("div", "cap-list");
    caps.forEach((cp) => {
      const row = host.el("div", "voice-item");
      row.appendChild(host.el("span", "id", cp.id));
      const who = cp.providers.length
        ? cp.providers.join(" / ")
        : "（待接入）";
      const g = pick[cp.id];
      /* 三种状态给三种话术：能用就说走谁，全关着就说去打开，没接入就说还没接
         —— 统一说"不可用"的话用户不知道该做什么。 */
      let tail = "";
      if (g && g.state === "ready") {
        tail = " → " + g.provider + (g.free ? "（免费）" : "")
             + (g.candidates > 1 ? " +" + (g.candidates - 1) + " 备选" : "");
      } else if (g && g.state === "disabled") {
        tail = " → 都没开，去设置里打开";
      }
      const t = host.el("span", "text", cp.name + " — " + who + tail);
      if (!cp.providers.length) t.style.opacity = "0.55";
      row.appendChild(t);
      list.appendChild(row);
    });
    this.body.appendChild(list);
    this.body.appendChild(host.el("p", "hint",
      "能力和供应商都是 config/ 下的契约文件，加一种新能力不用改代码；密钥只写 secret:// 引用，真实值留在本机。"));
  },
});
