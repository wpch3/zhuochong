/* 双路由沙盘（G99 / DC18）：给一条假请求，看它会落到本地还是云端、为什么。
   为什么要有这个面板：路由规则是"看不见的东西"，写完没人知道它到底怎么判。
   把判据摆在界面上、让用户自己拨开关看落点变化，比写十页文档管用。
   所有请求都是纯决策，不会真的调用任何模型、不花一分钱。 */
"use strict";
ZC.register({
  id: "route",
  title: "本地 / 云端路由",
  mount(host, root, opts) {
    this.host = host;
    const c = host.card(opts.title || "本地 / 云端路由", "框架");
    this.body = c.body;
    root.appendChild(c.box);

    this.state = { sensitive: 0, tokens: 200, load: -1, cloud_down: 0, heavy: 0 };

    const row = (label, node) => {
      const r = host.el("div", "row");
      r.appendChild(host.el("span", "", label));
      r.appendChild(node);
      this.body.appendChild(r);
      return r;
    };

    this.btns = {};
    const mk = (key, label) => {
      const b = host.el("button", "", label);
      b.id = "route-" + key;
      this.btns[key] = b;
      b.onclick = () => { this.state[key] = this.state[key] ? 0 : 1; this.refresh(); };
      return b;
    };
    const toggles = host.el("div", "wrap");
    toggles.appendChild(mk("sensitive", "带隐私标记"));
    toggles.appendChild(mk("heavy", "重活（推理/写码）"));
    toggles.appendChild(mk("cloud_down", "云端挂了"));
    row("请求长什么样", toggles);

    const tok = host.el("input");
    tok.type = "range"; tok.min = "0"; tok.max = "4000"; tok.step = "100";
    tok.value = String(this.state.tokens);
    tok.id = "route-tokens";
    tok.oninput = () => { this.state.tokens = parseInt(tok.value, 10); this.refresh(); };
    row("预估 token", tok);

    const load = host.el("input");
    load.type = "range"; load.min = "-1"; load.max = "100"; load.step = "1";
    load.value = String(this.state.load);
    load.id = "route-load";
    load.oninput = () => { this.state.load = parseInt(load.value, 10); this.refresh(); };
    row("本地负载 %", load);

    this.out = host.el("div", "mono");
    this.out.id = "route-out";
    this.body.appendChild(this.out);
    this.why = host.el("p", "hint", "");
    this.body.appendChild(this.why);
    this.refresh();
  },

  /* 把理由翻译成人话 —— 界面上只给英文枚举等于没解释 */
  explain(reason, d) {
    const r = (d.rules || {});
    const m = {
      default_local:     "没有任何理由上云，留在本地（免费、不出网）",
      sensitive_local:   "带隐私标记 → 强制本地",
      sensitive_blocked: "带隐私标记但本机没有可用模型 → 拒绝。宁可功能不可用，也不偷偷上云",
      long_cloud:        "预估 token 超过 " + (r.tokens_cloud || 512) + " → 上云",
      heavy_cloud:       "推理 / 写代码 / 工具调用这类重活 → 上云",
      local_busy:        "本地负载超过 " + (r.local_busy_pct || 85) + "% → 溢出到云端",
      cloud_down:        "本想上云，但云端不可用 → 退回本地",
      only_choice:       "想要的那边没有可用候选，只剩另一边",
    };
    return m[reason] || reason;
  },

  async refresh() {
    const host = this.host, s = this.state;
    const q = "route?cap=chat.completion&sensitive=" + s.sensitive +
              "&tokens=" + s.tokens + "&load=" + s.load +
              "&cloud_down=" + s.cloud_down + "&heavy=" + s.heavy;
    let d;
    try { d = await host.api(q); } catch (e) { this.out.textContent = "读不到 /api/route"; return; }
    /* 直接用手里的引用，不走 document.getElementById —— 组件不该依赖全局 DOM，
       而且测试台的假 DOM 里没有这个函数，用了就会在 await 里静默崩掉。 */
    ["sensitive", "heavy", "cloud_down"].forEach((k) => {
      const b = this.btns[k];
      if (b) b.classList.toggle("pri", !!s[k]);
    });
    const where = d.ok ? (d.local ? "本地" : "云端") : "拒绝";
    const who = d.ok ? (d.provider + " / " + d.model) : "——";
    const st = d.stats || {};
    this.out.textContent =
      "落点：" + where + "　供应商：" + who + "\n" +
      "理由：" + d.reason + "\n" +
      "本地分流占比：" + (st.local_share >= 0 ? (st.local_share * 100).toFixed(0) + "%" : "—") +
      "（本地 " + (st.local || 0) + " 次 / 云端 " + (st.cloud || 0) + " 次，目标区间 70~85%）";
    this.why.textContent = this.explain(d.reason, d);
    this.why.classList.toggle("warn", d.blocked_sensitive === true);
  },
});
