/* 顶栏状态胶囊：动作 / 情绪 / 好感 / 形态 / 缩放 + 测试台入口 */
"use strict";
ZC.register({
  id: "statuschips",
  title: "状态条",
  mount(host, root, opts) {
    this.host = host;
    const box = host.el("div", "chips");
    this.chips = {};
    const SPEC = opts.chips || [
      ["action", "动作"], ["mood", "情绪"], ["aff", "好感"], ["form", "形态"], ["scale", "缩放"],
    ];
    SPEC.forEach(([k, label]) => {
      const c = host.el("span", "chip", label + " —");
      c.dataset.label = label;
      box.appendChild(c);
      this.chips[k] = c;
    });
    if (opts.test_link !== false) {
      const a = host.el("a", "chip", "测试台");
      a.href = "test.html";
      a.style.textDecoration = "none";
      a.style.cursor = "pointer";
      box.appendChild(a);
    }
    root.appendChild(box);
  },
  onInfo(d) {
    const set = (k, v) => {
      const c = this.chips[k];
      if (c) c.textContent = c.dataset.label + " " + v;
    };
    set("action", d.action || "—");
    set("mood", d.mood || "—");
    set("aff", (d.affection != null ? d.affection : "—") + (d.tier_name ? " · " + d.tier_name : ""));
    set("form", d.form_name || d.form || "—");
    set("scale", d.scale != null ? d.scale : "—");
  },
});
