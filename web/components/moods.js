/* 情绪按钮（/api/express?mood=） */
"use strict";
ZC.register({
  id: "moods",
  title: "情绪",
  LIST: [["joy", "开心"], ["sad", "难过"], ["surprise", "惊讶"], ["think", "思考"], ["sleepy", "困倦"]],
  mount(host, root, opts) {
    this.host = host;
    const c = host.card(opts.title || "情绪");
    const grid = host.el("div", "grid");
    (opts.list || this.LIST).forEach(([id, name]) => {
      const b = host.el("button", "btn small", name);
      b.addEventListener("click", async () => {
        await host.api("/api/express", { mood: id });
        grid.querySelectorAll(".btn").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        host.refresh();
      });
      grid.appendChild(b);
    });
    c.body.appendChild(grid);
    root.appendChild(c.box);
  },
});
