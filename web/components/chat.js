/* 聊天框（G54 / T61.10）—— 真的把话发给模型的那个输入框。
 *
 * 在这块面板出现之前，整条链路是哑的：人设写得再细、路由判得再准，
 * 界面上也没有一个能打字的地方。
 *
 * 这块面板和别的聊天界面不一样的地方在于**它不藏事**：
 *   · 每条回复都标明是谁答的（供应商 / 型号 / 本地还是云端 / 花了多少）
 *     —— 用户有权知道自己这句话去过哪里；
 *   · "看看将要发什么"按钮会把真会出网的地址和请求体原样摆出来，
 *     而且那是和真发**同一段代码**算出来的（/api/chat?dry=1），不是示意图；
 *   · 失败就说失败，带上服务端的原话。不拿"网络开小差"糊弄人。
 *
 * 另外：发消息时小寻会 think，回复到了会 talk —— 立绘要跟着对话动，
 * 不然她就只是个贴图。
 */
"use strict";
ZC.register({
  id: "chat",
  title: "聊天",

  mount(host, root, opts) {
    this.host = host;
    const c = host.card(opts.title || "聊天", "G54");
    this.body = c.body;
    root.appendChild(c.box);

    this.opts = { persona: 1, sensitive: 0, tries: 1 };
    this.busy = false;

    /* ---- 对话区 ---- */
    this.log = host.el("div", "chat-log");
    this.body.appendChild(this.log);

    /* ---- 开关 ---- */
    const toggles = host.el("div", "wrap");
    this.tog = {};
    const mkTog = (key, label, tip) => {
      const b = host.el("button", "", label);
      b.id = "chat-" + key;
      b.title = tip || "";
      this.tog[key] = b;
      b.onclick = () => { this.opts[key] = this.opts[key] ? 0 : 1; this.syncTog(); };
      toggles.appendChild(b);
      return b;
    };
    mkTog("persona", "带人设", "把当前角色和好感档合成的系统提示词一起发过去");
    mkTog("sensitive", "隐私标记",
          "标记后只允许本地模型处理。本地不可用时宁可失败，也不会改发云端");
    this.body.appendChild(toggles);

    /* ---- 输入 ---- */
    const row = host.el("div", "row");
    this.input = host.el("input");
    this.input.type = "text";
    this.input.id = "chat-input";
    this.input.placeholder = "跟小寻说点什么…（回车发送）";
    this.input.onkeydown = (e) => { if (e.key === "Enter") this.send(); };
    const send = host.el("button", "btn", "发送");
    send.id = "chat-send";
    send.onclick = () => this.send();
    const reset = host.el("button", "", "重新开始聊");
    reset.id = "chat-reset";
    reset.title = "忘掉前面说过的话，从头开始（人设不受影响）";
    reset.onclick = async () => {
      try { await this.host.api("/api/context.json", { reset: 1 }); } catch (e) { /* 无妨 */ }
      this.log.innerHTML = "";
      this.say("sys", "好，忘干净了。从头开始吧。");
    };
    const dry = host.el("button", "", "看看将要发什么");
    dry.id = "chat-dry";
    dry.title = "只准备不发送：把真会出网的地址和请求体原样给你看，一个字节都不出网";
    dry.onclick = () => this.send(true);
    row.appendChild(this.input);
    row.appendChild(send);
    row.appendChild(dry);
    row.appendChild(reset);
    this.body.appendChild(row);

    this.note = host.el("div", "hint", "");
    this.body.appendChild(this.note);

    this.syncTog();
    this.say("sys", "连上本地模型（比如 ollama）就能直接聊。"
                  + "没开模型也可以点「看看将要发什么」——那条不需要模型。");
  },

  syncTog() {
    for (const k in this.tog) {
      this.tog[k].style.opacity = this.opts[k] ? "1" : "0.45";
      this.tog[k].setAttribute("aria-pressed", this.opts[k] ? "true" : "false");
    }
  },

  /* 往对话区加一条。who: me / her / sys / err */
  say(who, text, meta) {
    const wrap = this.host.el("div", "chat-msg chat-" + who);
    const name = { me: "你", her: "小寻", sys: "说明", err: "出错了" }[who] || who;
    wrap.appendChild(this.host.el("div", "chat-who", name));
    wrap.appendChild(this.host.el("div", "chat-text", text));
    if (meta) wrap.appendChild(this.host.el("div", "chat-meta", meta));
    this.log.appendChild(wrap);
    this.log.scrollTop = this.log.scrollHeight;
    return wrap;
  },

  /* /api/chat 失败时回 502，host.api 会抛 —— 这里要连状态码一起拿到，
     因为"上游拒绝"和"界面坏了"是两回事，不能混成一句"请求失败"。 */
  async call(params) {
    const q = new URLSearchParams(params).toString();
    const r = await fetch("/api/chat?" + q, { cache: "no-store" });
    let d = {};
    try { d = await r.json(); } catch (e) { d = { error: "服务端回的不是 JSON" }; }
    return { status: r.status, d };
  },

  /* 立绘联动：发出去时想一下，回来了就说话。
     动作不存在也不要紧（/api/action 对不认识的 id 是静默的）。 */
  async act(id) {
    try { await this.host.api("/api/action", { id: id }); } catch (e) { /* 不影响聊天 */ }
  },

  async send(dryRun) {
    if (this.busy) return;
    const text = (this.input.value || "").trim();
    if (!text) { this.input.focus(); return; }

    this.busy = true;
    this.note.textContent = dryRun ? "正在准备（不会发出去）…" : "正在问小寻…";
    if (!dryRun) {
      this.say("me", text);
      this.input.value = "";
      this.act("think");
    }

    const params = {
      text: text,
      persona: this.opts.persona,
      sensitive: this.opts.sensitive,
      tries: this.opts.tries,
    };
    if (dryRun) params.dry = 1;

    try {
      const { status, d } = await this.call(params);

      if (dryRun) {
        this.showDry(d, status);
      } else if (d.ok) {
        this.say("her", d.text || "（她没说话）", this.badge(d));
        this.act("talk");
      } else {
        /* 失败要让人知道下一步该干什么，所以把错误原话原样显示 */
        this.say("err", d.error || ("HTTP " + status), this.badge(d));
      }
    } catch (e) {
      this.say("err", "连不上预览服务：" + e.message);
    } finally {
      this.busy = false;
      this.note.textContent = "";
      this.host.refresh();
    }
  },

  /* 这句话是谁答的、走没走出这台机器、花了多少。 */
  badge(d) {
    const bits = [];
    if (d.provider) bits.push(d.provider + (d.model ? " · " + d.model : ""));
    bits.push(d.local ? "本地" : (d.provider ? "云端" : "没发出去"));
    if (d.reason) bits.push("因为 " + d.reason);
    if (d.tokens_in || d.tokens_out) bits.push(d.tokens_in + "↑/" + d.tokens_out + "↓ token");
    if (d.cost > 0) bits.push("￥" + Number(d.cost).toFixed(6));
    else if (d.ok) bits.push("不花钱");
    if (d.attempts > 1) bits.push("换了 " + d.attempts + " 家");
    /* 多轮（T61.11）：带了几轮历史要说出来 —— 用户得知道她"记着多少" */
    if (d.history_sent > 0) bits.push("记着前 " + d.history_sent + " 条");
    /* 这一条最要紧：有几轮因为带隐私标记没敢上云。
       不写出来的话，用户只会觉得"她怎么突然失忆了"，而那其实是保护生效了。 */
    if (d.turns_held > 0) bits.push("⚠ " + d.turns_held + " 条带隐私标记，没让它上云");
    return bits.join(" · ");
  },

  showDry(d, status) {
    if (!d.ok) {
      this.say("err", d.error || ("HTTP " + status), this.badge(d));
      return;
    }
    let pretty = d.request_body || "";
    try { pretty = JSON.stringify(JSON.parse(pretty), null, 2); } catch (e) { /* 原样 */ }
    const w = this.say("sys", "下面是**真的会发出去**的东西（这次一个字节都没发）：",
                       this.badge(d));
    const pre = this.host.el("pre", "mono chat-dry");
    pre.textContent = "POST " + (d.url || "(没有地址)") + "\n"
                    + "人设 " + (d.persona_bytes || 0) + " 字节\n\n"
                    + pretty;
    w.appendChild(pre);
    this.log.scrollTop = this.log.scrollHeight;
  },
});
