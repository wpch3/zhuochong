/* 音色库（G64）：挑嗓子 + 调参数 + 看情绪怎么表达。
   数据来自 web/voicebank.json 与 /emotion_map.json —— 都由 tools/check_platform.py
   从 config/voicebank/ 与 config/voice_cast.json 生成，加一个音色只是多一份契约文件。

   这个面板要回答三个问题：
     1. 有哪些嗓子可以用（按人设分组，标出二次元向、支不支持情绪）
     2. 谁在用哪一把（角色形态 / 各家 AI，用户要求"每个 AI 都不一样"）
     3. 选中的这把，某个情绪到底怎么发出去（四种通路差别很大，要让人看见） */
"use strict";
ZC.register({
  id: "voicebank",
  title: "音色库",
  async mount(host, root, opts) {
    this.host = host;
    const c = host.card(opts.title || "音色库", "语音");
    this.body = c.body;
    root.appendChild(c.box);
    this.body.appendChild(host.el("p", "hint", "读取中…"));

    let d, em;
    try {
      d = await host.api("/voicebank.json");
    } catch (e) {
      this.body.innerHTML = "";
      this.body.appendChild(host.el("p", "hint",
        "voicebank.json 还没生成：跑一次 python3 tools/check_platform.py"));
      return;
    }
    try { em = await host.api("/emotion_map.json"); } catch (e) { em = { emotions: {} }; }

    /* 清单可能是空的或旧版的——别让一个缺字段把整块界面干掉 */
    if (!d || !Array.isArray(d.voices) || !d.voices.length) {
      this.body.innerHTML = "";
      this.body.appendChild(host.el("p", "hint",
        "音色库是空的：检查 config/voicebank/ 下有没有契约，再跑 python3 tools/check_platform.py"));
      return;
    }
    this.d = d;
    this.em = em && em.emotions ? em : { emotions: {} };
    this.sel = (d.voices.find((v) => v.ready) || d.voices[0] || {}).id;
    this.emo = "happy";
    this.tune = {};
    this.render();
  },

  render() {
    const host = this.host, d = this.d, em = this.em;
    this.body.innerHTML = "";
    const voices = d.voices || [];
    const byId = {};
    voices.forEach((v) => { byId[v.id] = v; });

    const ready = voices.filter((v) => v.ready).length;
    this.body.appendChild(host.el("p", "mono",
      voices.length + " 个音色 · " + ready + " 个现在就能用 · 全部云端"
      + "（本地声源已按要求去掉）"));

    /* ---- 谁在用哪一把 ---- */
    const cast = d.cast || {};
    const castBox = host.el("div", "cap-list");
    (cast.characters || []).forEach((c) => {
      const v = byId[c.voice], fb = byId[c.fallback];
      const row = host.el("div", "voice-item");
      row.appendChild(host.el("span", "id", "小寻 " + c.form));
      /* 首选没开就如实说现在用的是兜底，别让界面显示一个发不出去的音色 */
      const using = v && v.ready ? v : fb;
      row.appendChild(host.el("span", "text",
        (v ? v.name : c.voice)
        + (v && !v.ready ? "（没配密钥，现在用 " + (fb ? fb.name : "—") + "）" : "")));
      castBox.appendChild(row);
    });
    (cast.agents || []).forEach((a) => {
      const v = byId[a.voice];
      const row = host.el("div", "voice-item");
      row.appendChild(host.el("span", "id", a.agent));
      row.appendChild(host.el("span", "text",
        (v ? v.name : a.voice) + " · " + a.lang
        + (v ? " · " + v.provider : "")));
      castBox.appendChild(row);
    });
    this.body.appendChild(host.el("p", "hint", "谁在用哪把嗓子（每个 AI 都不一样，也不同源）"));
    this.body.appendChild(castBox);

    /* ---- 挑一把 ---- */
    const PN = { loli: "萝莉", shoujo: "少女", young_woman: "青年女性",
                 onee_san: "御姐", mature: "成熟", boy: "男童", youth: "青年" };
    this.body.appendChild(host.el("p", "hint", "挑一把嗓子（点一下选中）"));
    const list = host.el("div", "cap-list");
    let lastP = null;
    voices.forEach((v) => {
      if (v.persona !== lastP) {
        lastP = v.persona;
        list.appendChild(host.el("p", "hint", "— " + (PN[v.persona] || v.persona) + " —"));
      }
      const row = host.el("div", "voice-item");
      row.style.cursor = "pointer";
      if (v.id === this.sel) row.style.fontWeight = "bold";
      const tag = host.el("span", "id", v.anime ? "二次元" : "写实");
      row.appendChild(tag);
      /* 情绪区分度写成人话：0 就直说做不到，别让用户以为选了它也有情绪 */
      const emoTxt = v.emotion_distinct > 0
        ? "情绪 " + v.emotion_distinct + " 档"
        : "无情绪（只能调语速音调）";
      row.appendChild(host.el("span", "text",
        v.name + " · " + emoTxt + " · " + v.langs.join("/")
        + (v.ready ? "" : " · 待配密钥")));
      if (!v.ready) row.style.opacity = "0.6";
      row.onclick = () => { this.sel = v.id; this.tune = {}; this.render(); };
      list.appendChild(row);
    });
    this.body.appendChild(list);

    /* ---- 调这一把 ---- */
    const v = byId[this.sel];
    if (!v) return;
    this.body.appendChild(host.el("p", "hint", "调「" + v.name + "」"));
    const detail = host.el("div", "panels");
    detail.appendChild(host.el("p", "mono",
      v.provider + " · " + v.voice_id + " · 情绪通路 " + v.emotion_mode));
    if (v.recommend) detail.appendChild(host.el("p", "hint", v.recommend));

    const tun = v.tunable || {};
    Object.keys(tun).forEach((k) => {
      const lo = tun[k][0], hi = tun[k][1];
      const cur = (this.tune[k] === undefined) ? (lo <= 0 && hi >= 0 ? 0 : lo) : this.tune[k];
      const wrap = host.el("div", "voice-item");
      wrap.appendChild(host.el("span", "id", k));
      const sl = host.el("input");
      sl.type = "range";
      sl.min = String(lo); sl.max = String(hi);
      sl.step = String((hi - lo) > 20 ? 1 : 0.1);
      sl.value = String(cur);
      const out = host.el("span", "text", String(cur));
      sl.oninput = () => { this.tune[k] = Number(sl.value); out._text = sl.value;
                           if (out.textContent !== undefined) out.textContent = sl.value; };
      wrap.appendChild(sl);
      wrap.appendChild(out);
      detail.appendChild(wrap);
    });

    /* ---- 这个情绪会怎么发出去 ---- */
    const emos = em.emotions || {};
    const keys = Object.keys(emos);
    if (keys.length) {
      const pick = host.el("div", "voice-item");
      pick.appendChild(host.el("span", "id", "情绪"));
      const sel = host.el("select");
      keys.forEach((k) => {
        const o = host.el("option", "", emos[k].name || k);
        o.value = k;
        if (k === this.emo) o.selected = true;
        sel.appendChild(o);
      });
      sel.onchange = () => { this.emo = sel.value; this.render(); };
      pick.appendChild(sel);
      detail.appendChild(pick);

      const e = emos[this.emo] || {};
      let how;
      /* 四种通路发出去的东西完全不同，直接把实际会发的参数显示出来 */
      if (v.emotion_mode === "style") {
        const ok = (v.emotions || []).indexOf(e.style) >= 0;
        how = ok ? 'SSML style="' + e.style + '"'
                 : "这把嗓子不支持 " + (e.style || "—") + " → 退回语速音调模拟";
      } else if (v.emotion_mode === "emotion") {
        how = 'emotion="' + e.minimax + '"';
      } else if (v.emotion_mode === "inline_tag") {
        how = "文本里加 " + (e.tag || "（无标签）");
      } else {
        const p = e.prosody || {};
        how = "只能模拟：rate " + (p.rate || 0) + "% · pitch " + (p.pitch || 0)
            + " · volume " + (p.volume || 0) + "%";
      }
      detail.appendChild(host.el("p", "mono", "→ " + how));
      if (e.expression) {
        detail.appendChild(host.el("p", "hint",
          "说这句话时脸上同时做「" + e.expression + "」表情"));
      }
    }
    this.body.appendChild(detail);
  },
});
