/* 用量（Token 计费占位）。本地网关接入前只统计本次会话的演示数字。 */
"use strict";
ZC.register({
  id: "usage",
  title: "用量",
  mount(host, root, opts) {
    this.host = host;
    this.budget = opts.budget_tokens || 2000;
    const c = host.card(opts.title || "用量（Token 计费）", "占位");
    const meter = host.el("div", "meter");
    this.fill = host.el("div", "meter-fill");
    meter.appendChild(this.fill);
    c.body.appendChild(meter);
    this.text = host.el("p", "mono");
    c.body.appendChild(this.text);
    c.body.appendChild(host.el("p", "hint",
      "本地网关（T9.2）接入后，这里显示真实用量与费用；数据只存本机。"));
    root.appendChild(c.box);
    host.on("usage", (u) => {
      const s = host.state.usage;
      s.calls += (u.calls || 0);
      s.tokens += (u.tokens || 0);
      this.render();
    });
    this.render();
  },
  onSpeech(d) {
    /* 引擎自己说的话也算一次调用（和重构前一致） */
    if (d.fresh && d.line) { this.host.state.usage.calls += 1; this.render(); }
  },
  render() {
    const s = this.host.state.usage;
    this.text.textContent = `本次会话：${s.calls} 次调用 · ${s.tokens} token（演示估算）`;
    const pct = Math.min(100, (s.tokens / this.budget) * 100);
    this.fill.style.width = pct.toFixed(1) + "%";
  },
});
