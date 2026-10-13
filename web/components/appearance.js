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
    if (d.form) this.form.value = d.form;
    if (d.outfit) this.outfit.value = d.outfit;
    if (d.scale != null && Math.abs(Number(this.scale.value) - d.scale) > 0.001) {
      this.scale.value = d.scale;
      this.scaleVal.textContent = Number(d.scale).toFixed(2);
    }
  },
});
