/* 语音清单：读 /voice_manifest.json，按前缀分组，点一条就播并进入说话动作。 */
"use strict";
ZC.register({
  id: "voice",
  title: "语音",
  GROUP_NAMES: {
    all: "全部", greet: "问候", pat: "摸头 / 抚摸", click: "点击 / 拖动", mood: "情绪",
    call: "语音通话", aff: "好感", sleep: "睡醒", other: "其他",
  },
  groupOf(id) {
    if (id.startsWith("pat_") || id.startsWith("stroke_") || id.startsWith("feet_")) return "pat";
    if (id.startsWith("click_") || id.startsWith("drag_") || id.startsWith("drop_")) return "click";
    if (id.startsWith("mood_")) return "mood";
    if (id.startsWith("call_")) return "call";
    if (id.startsWith("tier_")) return "aff";
    if (id.startsWith("wake_") || id.startsWith("hammer_")) return "sleep";
    return "other";
  },
  mount(host, root, opts) {
    this.host = host;
    this.group = "all";
    this.data = [];
    const c = host.card(opts.title || "语音", "加载中…");
    this.engineTag = c.box.querySelector(".tag");
    const row = host.el("div", "row");
    row.appendChild(host.el("label", null, "分组"));
    this.sel = host.el("select");
    row.appendChild(this.sel);
    c.body.appendChild(row);
    this.list = host.el("div", "voice-list");
    c.body.appendChild(this.list);
    this.player = host.el("audio");
    this.player.preload = "none";
    c.body.appendChild(this.player);
    this.note = host.el("p", "hint", "台词为已渲染的音频；说话时立绘会自动进入说话动作。");
    c.body.appendChild(this.note);
    root.appendChild(c.box);
    this.sel.addEventListener("change", () => { this.group = this.sel.value; this.render(); });
    this.load();
  },
  async load() {
    try {
      const d = await this.host.api("/voice_manifest.json");
      this.data = d.lines || [];
      this.engineTag.textContent = d.engine || "未知";
      if (d.note) this.note.textContent = d.note;
    } catch (e) {
      this.engineTag.textContent = "清单缺失";
      return;
    }
    const groups = new Set(this.data.map((v) => this.groupOf(v.id)));
    this.sel.innerHTML = "";
    const all = this.host.el("option", null, this.GROUP_NAMES.all);
    all.value = "all";
    this.sel.appendChild(all);
    [...groups].sort().forEach((g) => {
      const o = this.host.el("option", null, this.GROUP_NAMES[g] || g);
      o.value = g;
      this.sel.appendChild(o);
    });
    this.render();
  },
  render() {
    this.list.innerHTML = "";
    this.data
      .filter((v) => this.group === "all" || this.groupOf(v.id) === this.group)
      .forEach((v) => {
        const row = this.host.el("div", "voice-item");
        row.appendChild(this.host.el("span", "id", v.id));
        row.appendChild(this.host.el("span", "text", v.text));
        row.addEventListener("click", () => this.play(v));
        this.list.appendChild(row);
      });
  },
  async play(v) {
    this.player.src = "/media/" + v.file;
    try { await this.player.play(); } catch (e) { /* 自动播放限制，由用户点击触发即可 */ }
    await this.host.api("/api/action", { id: "talk" });
    this.host.emit("usage", { calls: 1, tokens: Math.ceil((v.text || "").length / 2) });
    this.host.emit("speech", { line: v.text, fresh: true });
  },
});
