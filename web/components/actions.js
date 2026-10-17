/* 动作按钮。列表由引擎 /api/info.json 的 actions 给出 —— 引擎新增动作会自动出现。 */
"use strict";
ZC.register({
  id: "actions",
  title: "动作",
  /* 引擎给的 id → 中文显示；没列到的直接显示 id（所以新增动作不改这里也能用） */
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
    root.appendChild(c.box);
    this.built = false;
  },
  onInfo(d) {
    if (this.built || !d.actions || !d.actions.length) return;
    const ids = ["idle"].concat(d.actions.filter((x) => x !== "idle"));
    this.grid.innerHTML = "";
    ids.forEach((id) => {
      const b = this.host.el("button", "btn small", this.NAMES[id] || id);
      b.addEventListener("click", async () => {
        await this.host.api("/api/action", { id: id });
        this.grid.querySelectorAll(".btn").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        this.host.refresh();
      });
      this.grid.appendChild(b);
    });
    this.built = true;
  },
});
