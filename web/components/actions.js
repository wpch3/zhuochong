/* 动作按钮。列表由引擎 /api/info.json 的 actions 给出 —— 引擎新增动作会自动出现。
   显示名优先用引擎给的 action_names（来自 rig.json）。
   下面那张 NAMES 表只是旧版引擎的兜底，**不要再往里加新动作** ——
   名字属于数据层，加在 tools/make_rig.py 的 ACTION_TITLES 里，
   否则正式软件的 UI 重做时这些文案要重写一遍。 */
"use strict";
ZC.register({
  id: "actions",
  title: "动作",
  /* 兜底表：引擎没给 action_names 时才用（旧版引擎 / 旧 rig.json） */
  NAMES: {
    idle: "待机", focus: "专注", happy: "开心", sad: "难过", surprised: "惊讶",
    think: "思考", talk: "说话", sleep: "睡觉", head_pat: "摸头", stroke: "抚摸",
    hammered: "被锤", clicked: "被点", dragged: "被拖", wake: "叫醒",
    breath: "呼吸", sway: "摇摆", wave: "挥手",
  },
  mount(host, root, opts) {
    this.host = host;
    const c = host.card(opts.title || "动作");
    this.grid = host.el("div", "grid");
    c.body.appendChild(this.grid);
    this.error = host.el("p", "hint");
    this.error.hidden = true;
    c.body.appendChild(this.error);
    root.appendChild(c.box);
    this.signature = null;
  },
  onInfo(d) {
    if (!Array.isArray(d.actions)) return;
    /* 形态或角色切换后动作和显示名可能变化；相同清单才跳过重建。 */
    const signature = JSON.stringify([d.character, d.form, d.actions, d.action_names || []]);
    if (signature === this.signature) return;
    /* 引擎给的名字优先 —— actions 和 action_names 一一对应 */
    const fromEngine = {};
    (d.action_names || []).forEach((nm, i) => {
      if (nm && d.actions[i]) fromEngine[d.actions[i]] = nm;
    });
    const label = (id) => fromEngine[id] || this.NAMES[id] || id;
    const ids = ["idle"].concat(d.actions.filter((x) => x !== "idle"));
    this.grid.innerHTML = "";
    ids.forEach((id) => {
      const b = this.host.el("button", "btn small", label(id));
      b.addEventListener("click", async () => {
        try {
          await this.host.api("/api/action", { id: id });
          this.error.hidden = true;
          this.grid.querySelectorAll(".btn").forEach((x) => x.classList.remove("active"));
          b.classList.add("active");
          this.host.refresh();
        } catch (e) {
          this.error.textContent = "动作播放失败：" + e.message;
          this.error.hidden = false;
          this.host.refresh();
        }
      });
      this.grid.appendChild(b);
    });
    this.signature = signature;
  },
});
