/* 设置：主题切换（G1 的验收点之一）、整窗穿透说明、日志查看。 */
"use strict";
ZC.register({
  id: "settings",
  title: "设置",
  mount(host, root, opts) {
    this.host = host;
    const c = host.card(opts.title || "设置");

    /* 主题下拉：选项来自 layout.json 的 themes 列表，换主题不改代码 */
    const trow = host.el("div", "row");
    trow.appendChild(host.el("label", null, "主题"));
    this.themeSel = host.el("select");
    const themes = (host.state.layout && host.state.layout.themes)
      || [{ id: "sakura", name: "樱色（默认）" }, { id: "dusk", name: "暮色（深色）" }];
    themes.forEach((t) => {
      const o = host.el("option", null, t.name || t.id);
      o.value = t.id;
      this.themeSel.appendChild(o);
    });
    const cur = host.theme();
    if (cur && cur.id) this.themeSel.value = cur.id;
    this.themeSel.addEventListener("change", () => host.setTheme(this.themeSel.value));
    trow.appendChild(this.themeSel);
    c.body.appendChild(trow);

    const prow = host.el("div", "row");
    prow.appendChild(host.el("label", null, "整窗穿透"));
    const pbtn = host.el("button", "btn small", "仅真机可用");
    pbtn.addEventListener("click", () => {
      alert("整窗穿透（Ctrl+Alt+T）与托盘菜单只在 Windows 真机生效；沙箱预览用于演示引擎与交互。");
    });
    prow.appendChild(pbtn);
    c.body.appendChild(prow);

    const lrow = host.el("div", "row");
    lrow.appendChild(host.el("label", null, "日志"));
    const lbtn = host.el("button", "btn small", "查看末尾");
    lrow.appendChild(lbtn);
    c.body.appendChild(lrow);
    const pre = host.el("pre", "log");
    pre.hidden = true;
    c.body.appendChild(pre);
    lbtn.addEventListener("click", async () => {
      if (!pre.hidden) { pre.hidden = true; return; }
      try {
        const t = await host.api("/media/logs/preview.log");
        pre.textContent = String(t).slice(-3000);
      } catch (e) {
        pre.textContent = "日志读取失败（logs/ 可能尚未生成）";
      }
      pre.hidden = false;
    });

    c.body.appendChild(host.el("p", "hint",
      "透明窗、像素级穿透、托盘与热键在 Windows 真机上生效，沙箱预览只演示引擎与交互。"));
    root.appendChild(c.box);
  },
});
