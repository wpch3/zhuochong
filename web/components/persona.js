/* 人设与剧情（第三十问 e/f）：性格预设 + 八个滑杆 + 相遇引导 + 提示词实时预览。
 *
 * 这块面板的核心主张是**所见即所得**：下面那个灰框里显示的不是"示意"，
 * 是 zpersona_compose 真的会喂给模型的那段文本，一个字都不差（/api/persona.json 的 prompt）。
 * 改一个滑杆就重新取一次，能当场看见提示词哪一行变了 —— 人设跑偏时不用猜。
 *
 * 所有写入都走 /api/persona/set 的白名单，和"用对话改人设"是同一条通道、同一套限制：
 * 面板改不了的字段，让模型去改也一样改不了。
 */
"use strict";
ZC.register({
  id: "persona",
  title: "人设与剧情",

  /* 相遇引导的四步。顺序就是问的顺序，问完就不再出现。 */
  MEET: [
    { k: "meeting.user",     q: "我该怎么称呼你？",         ph: "比如：阿泽" },
    { k: "meeting.when",     q: "我们是什么时候认识的？",   ph: "比如：去年冬天" },
    { k: "meeting.where",    q: "在哪儿第一次见面？",       ph: "比如：深夜的便利店" },
    { k: "meeting.how",      q: "当时发生了什么？",         ph: "比如：你把最后一个肉包让给了我" },
  ],

  async mount(host, root, opts) {
    this.host = host;
    const c = host.card(opts.title || "人设与剧情", "角色");
    this.body = c.body;
    root.appendChild(c.box);
    await this.reload();
  },

  async set(k, v) {
    try {
      const r = await this.host.api("/api/persona/set", { k, v });
      if (!r.ok) { this.note("改不了：" + (r.error || k), true); return false; }
      return true;
    } catch (e) { this.note("写入失败：" + e.message, true); return false; }
  },

  note(msg, bad) {
    if (!this.noteEl) return;
    this.noteEl.textContent = msg;
    this.noteEl.style.color = bad ? "var(--err,#c2436b)" : "var(--dim,#8a8aa0)";
  },

  async reload() {
    let d;
    try { d = await this.host.api("/api/persona.json"); }
    catch (e) { this.body.textContent = "人设读取失败：" + e.message; return; }
    this.data = d;
    const el = this.host.el;
    this.body.innerHTML = "";

    /* ── 相遇引导：没填完就顶在最上面，填完自动消失 ───────────────── */
    if (d.meeting_todo > 0) this.body.appendChild(this.meetingBox(el, d));

    /* ── 预设下拉 ──────────────────────────────────────────────── */
    const row = el("div", "row");
    row.style.cssText = "display:flex;align-items:center;gap:8px;margin:6px 0";
    row.appendChild(el("label", "lbl", "性格预设"));
    const sel = el("select");
    (d.presets || []).forEach((p) => {
      const o = document.createElement("option");
      o.value = p.id; o.textContent = p.name;
      if (p.id === d.preset) o.selected = true;
      sel.appendChild(o);
    });
    sel.onchange = async () => {
      /* 换预设会把整组滑杆一次铺好，所以必须整块重画 */
      if (await this.set("preset", sel.value)) { await this.reload(); this.note("已套用预设"); }
    };
    row.appendChild(sel);
    this.body.appendChild(row);

    /* ── 八个微调滑杆 ──────────────────────────────────────────── */
    const tip = el("div", "dim", "拖动 = 在预设基础上微调；拖到正中间 = 这条不写进提示词");
    tip.style.cssText = "font-size:11px;opacity:.65;margin:2px 0 6px";
    this.body.appendChild(tip);

    (d.traits || []).forEach((t) => {
      const line = el("div");
      line.style.cssText = "display:grid;grid-template-columns:56px 1fr 72px;" +
                           "align-items:center;gap:8px;margin:3px 0";
      line.appendChild(el("span", "lbl", t.name));
      const s = document.createElement("input");
      s.type = "range"; s.min = "1"; s.max = "5"; s.step = "1"; s.value = String(t.v);
      s.style.width = "100%";
      const out = el("span", "dim", this.word(t, t.v));
      out.style.cssText = "font-size:11px;opacity:.75;text-align:right";
      s.oninput = () => { out.textContent = this.word(t, Number(s.value)); };
      s.onchange = async () => {
        if (await this.set("trait." + t.id, s.value)) {
          this.note("已改 " + t.name);
          await this.refreshPrompt();
        }
      };
      s.title = t.low + " ↔ " + t.high;
      line.appendChild(s); line.appendChild(out);
      this.body.appendChild(line);
    });

    /* ── 称呼 + 自由补充 ───────────────────────────────────────── */
    this.body.appendChild(this.textRow(el, "怎么叫你", "nickname", d.nickname || "", "留空=不特别称呼"));
    this.body.appendChild(this.textRow(el, "补充设定", "custom", d.custom || "",
                                       "自己写一段，优先级最高"));

    /* ── 提示词实时预览 ────────────────────────────────────────── */
    const h = el("div", "lbl", "实际喂给模型的系统提示词");
    h.style.cssText = "margin:10px 0 4px;font-size:12px";
    this.body.appendChild(h);
    this.pre = el("pre");
    this.pre.style.cssText = "white-space:pre-wrap;font-size:11px;line-height:1.5;" +
      "max-height:210px;overflow:auto;padding:8px;border-radius:6px;" +
      "background:rgba(0,0,0,.18);margin:0";
    this.body.appendChild(this.pre);

    this.noteEl = el("div", "dim", "");
    this.noteEl.style.cssText = "font-size:11px;margin-top:6px;min-height:14px";
    this.body.appendChild(this.noteEl);

    this.paintPrompt(d);
  },

  /* 滑杆取值翻成人话 —— 和 C 侧 trait_phrase 同一套规则，省得两边说法不一致 */
  word(t, v) {
    if (v === 1) return t.low;
    if (v === 2) return "比较" + t.low;
    if (v === 4) return "比较" + t.high;
    if (v === 5) return t.high;
    return "不特别设定";
  },

  textRow(el, label, key, val, ph) {
    const line = el("div");
    line.style.cssText = "display:grid;grid-template-columns:56px 1fr;align-items:center;" +
                         "gap:8px;margin:5px 0";
    line.appendChild(el("span", "lbl", label));
    const i = document.createElement("input");
    i.type = "text"; i.value = val; i.placeholder = ph;
    i.style.cssText = "width:100%;box-sizing:border-box";
    i.onchange = async () => {
      if (await this.set(key, i.value)) { this.note("已保存"); await this.refreshPrompt(); }
    };
    line.appendChild(i);
    return line;
  },

  meetingBox(el, d) {
    const box = el("div");
    box.style.cssText = "border:1px solid rgba(255,255,255,.14);border-radius:8px;" +
                        "padding:8px;margin-bottom:10px;background:rgba(255,255,255,.04)";
    const step = this.MEET.find((m) => !this.filled(d, m.k)) || this.MEET[0];
    const t = el("div", "lbl", "初次见面（还剩 " + d.meeting_todo + " 步）");
    t.style.cssText = "font-size:12px;margin-bottom:4px";
    box.appendChild(t);
    box.appendChild(Object.assign(el("div", "dim", step.q),
                    { style: "font-size:12px;margin-bottom:6px" }));
    const i = document.createElement("input");
    i.type = "text"; i.placeholder = step.ph;
    i.style.cssText = "width:100%;box-sizing:border-box";
    const go = async () => {
      if (!i.value.trim()) return;
      if (await this.set(step.k, i.value.trim())) await this.reload();
    };
    i.onkeydown = (e) => { if (e.key === "Enter") go(); };
    box.appendChild(i);
    const skip = el("button", "", "跳过，让它自己发挥");
    skip.style.cssText = "margin-top:6px;font-size:11px";
    skip.onclick = async () => {
      if (await this.set("meeting.enabled", "0")) await this.reload();
    };
    box.appendChild(skip);
    return box;
  },

  /* meeting_todo 是后端算的总数，这里只需要知道**具体哪一步**还空着。
     后端没把每个字段单独吐出来，所以从 prompt 里找 —— 填了就一定会出现在提示词里。 */
  filled(d, key) {
    const mark = { "meeting.user": "对方叫", "meeting.when": "时间：",
                   "meeting.where": "地点：", "meeting.how": "经过：" }[key];
    return mark ? (d.prompt || "").includes(mark) : true;
  },

  async refreshPrompt() {
    try {
      const d = await this.host.api("/api/persona.json");
      this.data = d;
      this.paintPrompt(d);
    } catch (e) { /* 预览刷不出来不算致命，设定本身已经存了 */ }
  },

  paintPrompt(d) {
    if (!this.pre) return;
    this.pre.textContent = d.prompt || "（空）";
    if (this.noteEl && !this.noteEl.textContent)
      this.note(d.prompt_bytes + " 字节 · 当前好感档 " + d.tier);
  },

  onInfo() { /* 人设不随每帧状态变，不跟轮询 */ },
  destroy() { this.body = null; this.pre = null; },
});
