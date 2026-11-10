/* 形态 / 服装 / 缩放。列表全部由引擎扫描角色包给出，新增形态或服装会自动出现。 */
"use strict";
ZC.register({
  id: "appearance",
  title: "形态 / 服装 / 缩放",
  /* 兜底名字表：引擎没给名字时才用（新增形态应在 character.json 里写 name，不改这里） */
  FORM_NAMES: { teen: "少女", loli: "萝莉", adult: "青年女性", chibi: "Q 版" },
  mount(host, root, opts) {
    this.host = host;
    const c = host.card(opts.title || "形态 / 服装 / 缩放");
    const mkRow = (label, node) => {
      const row = host.el("div", "row");
      row.appendChild(host.el("label", null, label));
      row.appendChild(node);
      return row;
    };
    this.form = host.el("select");
    this.outfit = host.el("select");
    this.scale = host.el("input");
    this.scale.type = "range";
    this.scale.min = "0.30"; this.scale.max = "1.20"; this.scale.step = "0.05";
    this.scaleVal = host.el("span", "mono", "—");

    c.body.appendChild(mkRow("形态", this.form));
    c.body.appendChild(mkRow("服装", this.outfit));
    const srow = mkRow("缩放", this.scale);
    srow.appendChild(this.scaleVal);
    c.body.appendChild(srow);
    root.appendChild(c.box);
    this.body = c.body;

    this.form.addEventListener("change", async () => {
      await host.api("/api/form", { id: this.form.value });
      host.refresh();
    });
    this.outfit.addEventListener("change", async () => {
      await host.api("/api/outfit", { id: this.outfit.value });
      host.refresh();
    });
    this.scale.addEventListener("input", (e) => {
      this.scaleVal.textContent = Number(e.target.value).toFixed(2);
    });
    this.scale.addEventListener("change", async (e) => {
      await host.api("/api/scale", { s: e.target.value });
      host.refresh();
    });
    this.filled = false;
  },
  onInfo(d) {
    if (!this.filled && (d.forms || d.outfits)) {
      const fill = (sel, ids, names, fallback) => {
        sel.innerHTML = "";
        (ids || []).forEach((id, i) => {
          const o = this.host.el("option");
          o.value = id;
          o.textContent = ((names || [])[i] || fallback(id) || id) + "（" + id + "）";
          sel.appendChild(o);
        });
      };
      fill(this.form, d.forms, d.form_names, (id) => this.FORM_NAMES[id]);
      fill(this.outfit, d.outfits, d.outfit_names, (id) => (id === "default" ? "常服" : id));
      this.filled = true;
    }
    /* 形态路线图：把「规划了但还没做」的形态也摆出来（灰色，点不了）。
       不这么做的话，界面上只有一个 teen，看不出这个角色将来还会有萝莉/御姐/Q 版，
       而那三个的音色其实早就选好了。做好一个 = 素材进 forms/<id>/ 并生成 rig.json，
       引擎扫到就自动从 planned 变 ready，这里不用改代码。 */
    const road = d.form_roadmap || [];
    const todo = road.filter((g) => g.status !== "ready");
    if (todo.length && this._roadKey !== todo.map((g) => g.id).join(",")) {
      this._roadKey = todo.map((g) => g.id).join(",");
      if (!this.roadBox) {
        this.roadBox = this.host.el("div", "");
        this.body.appendChild(this.roadBox);
      }
      this.roadBox.textContent = "";
      this.roadBox.appendChild(this.host.el("p", "hint",
        "还没做的形态（" + todo.length + "）：做好后放进 characters/<角色>/forms/ 即可自动启用"));
      const chips = this.host.el("div", "chips");
      todo.forEach((g) => {
        const b = this.host.el("button", "btn small", g.name + "（" + g.id + "）");
        b.disabled = true;
        b.title = g.note || "还没做";
        chips.appendChild(b);
      });
      this.roadBox.appendChild(chips);
    }
    if (d.form) this.form.value = d.form;
    if (d.outfit) this.outfit.value = d.outfit;
    if (d.scale != null && Math.abs(Number(this.scale.value) - d.scale) > 0.001) {
      this.scale.value = d.scale;
      this.scaleVal.textContent = Number(d.scale).toFixed(2);
    }
  },
});
