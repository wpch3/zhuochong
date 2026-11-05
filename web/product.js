/* T62.1 产品界面原型：和测试台组件完全分离。可见文案从 product_copy.json 读取。 */
"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const copy = {};
  let busy = false;
  let bubbleTimer = 0;
  const conversation = $("conversation");
  const input = $("message");
  const sendButton = $("send");
  const options = $("options");
  const toast = $("toast");

  async function loadCopy() {
    const r = await fetch("product_copy.json", { cache: "no-store" });
    if (!r.ok) throw new Error("copy");
    Object.assign(copy, await r.json());
    document.title = copy.title;
    $("desktop-pet").setAttribute("aria-label", copy.app_label);
    $("character").alt = copy.character_alt;
    $("talk-toggle").setAttribute("aria-label", copy.talk_label);
    input.setAttribute("aria-label", copy.input_label);
    input.placeholder = copy.placeholder;
    sendButton.setAttribute("aria-label", copy.send);
    $("more").setAttribute("aria-label", copy.more);
    document.querySelectorAll("[data-copy]").forEach((el) => {
      el.textContent = copy[el.dataset.copy] || "";
    });
    showBubble("her", copy.welcome, null, 6500);
  }

  function showToast(text) {
    toast.textContent = text;
    toast.hidden = false;
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => { toast.hidden = true; }, 2600);
  }

  /* 气泡。self=true = 这句是**她自己起头**说的（不是回答你），
     界面上要能看出来 —— 但只是左边一道细线，不许做成"系统通知"。
     pending=true = 占位：她还在想/先说半句。 */
  function showBubble(who, text, meta, lifetime, opts) {
    const o = opts || {};
    clearTimeout(bubbleTimer);
    conversation.replaceChildren();
    const bubble = document.createElement("article");
    bubble.className = "bubble" + (who === "you" ? " user" : "") + (o.self ? " self" : "");
    const body = document.createElement("div");
    body.className = "text" + (o.pending ? " pending" : "");
    body.textContent = text;
    bubble.appendChild(body);
    if (meta) {
      const details = document.createElement("details");
      details.className = "meta";
      const summary = document.createElement("summary");
      const dot = document.createElement("i");
      dot.className = "dot " + meta.dot;
      const label = document.createElement("span");
      label.textContent = meta.label;
      summary.append(dot, label);
      const detail = document.createElement("div");
      detail.className = "meta-body";
      detail.textContent = meta.detail;
      details.append(summary, detail);
      if (meta.extra) {
        const pre = document.createElement("pre");
        pre.textContent = meta.extra;
        detail.appendChild(pre);
      }
      bubble.appendChild(details);
    }
    conversation.appendChild(bubble);
    if (lifetime > 0) bubbleTimer = setTimeout(() => conversation.replaceChildren(), lifetime);
  }

  function metadata(d) {
    const local = !!d.local;
    const label = local ? copy.local : (d.provider ? copy.cloud : copy.not_sent);
    const lines = [];
    if (d.provider) lines.push(d.provider + (d.model ? " · " + d.model : ""));
    lines.push(label);
    if (d.reason) lines.push(copy.reason + "：" + ((copy.route_reasons || {})[d.reason] || copy.unknown_reason));
    if (d.tokens_in || d.tokens_out) {
      lines.push(copy.input_tokens + "：" + (d.tokens_in || 0) + " / " + copy.output_tokens + "：" + (d.tokens_out || 0));
    }
    if (d.cost > 0) lines.push(copy.cost + "：￥" + Number(d.cost).toFixed(6));
    else if (d.ok) lines.push(copy.free);
    if (d.attempts > 1) lines.push(copy.attempts + "：" + d.attempts);
    if (d.history_sent > 0) lines.push(copy.history + "：" + d.history_sent);
    if (d.turns_held > 0) lines.push("⚠ " + d.turns_held + " " + copy.held);
    if (d.persona_bytes > 0) lines.push(copy.persona_bytes + "：" + d.persona_bytes + " " + copy.bytes_unit);
    return { label, dot: d.turns_held > 0 ? "warn" : (local ? "" : (d.provider ? "cloud" : "none")), detail: lines.join("\n") };
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, Math.max(0, ms)));
  /* 最近一次"有人说话"（她说的或你说的）的时刻。她自己起头要等这个够久 ——
     刚陪你说完一句就马上又自己挑话题，那是复读机，不是想说话的人。 */
  let lastTalkAt = Date.now();

  /* 她"多快说"由引擎判（T69.1）。界面只做两件事：按引擎给的停顿等，
     以及想清楚时先把那句"嗯……让我想想"放出来。**没有任何开关** ——
     用户能做的只有说话和沉默。 */
  async function thinkFor(text) {
    try {
      const r = await fetch("/api/think.json?text=" + encodeURIComponent(text), { cache: "no-store" });
      if (r.ok) return await r.json();
    } catch (_) { /* 服务没起来时按"立刻说"处理，不打断说话 */ }
    return { mode: "blurt", delay_ms: 0, preface: "", max_tokens: 0 };
  }

  async function request(text, dry, extra) {
    const params = new URLSearchParams({
      text,
      persona: $("persona").checked ? "1" : "0",
      sensitive: $("sensitive").checked ? "1" : "0",
      tries: "1",
    });
    if (dry) params.set("dry", "1");
    if (extra && extra.self) params.set("self", String(extra.self));
    const response = await fetch("/api/chat?" + params.toString(), { cache: "no-store" });
    let data;
    try { data = await response.json(); }
    catch (_) { data = { ok: false, error: copy.send_failed }; }
    return { status: response.status, data };
  }

  function finishSend(data, status, dry, th, selfIntent) {
    if (dry) {
      const extra = data.ok ? "POST " + (data.url || copy.no_url) + "\n\n" + (data.request_body || "") : "";
      const meta = metadata(data);
      meta.extra = extra;
      showBubble("her", data.ok ? copy.dry_header : (data.error || (copy.http_status + " " + status)), meta, 0);
      const panel = $("dry-output");
      panel.hidden = false;
      panel.textContent = extra || data.error || "";
      $("dry").open = true;
      return;
    }
    if (!data.ok) {
      showBubble("her", copy.failed + (data.error || (copy.http_status + " " + status)), metadata(data), 0);
      return;
    }
    const meta = metadata(data);
    if (selfIntent) {
      /* 她自己起头：代价信息照旧放进去，但标题写清"这一句不是回答你" */
      meta.detail = copy.self_speaking + "（" +
        ((copy.self_intent || {})[selfIntent] || selfIntent) + "）\n" + meta.detail;
      showBubble("her", data.text || copy.empty_reply, meta, 12000, { self: true });
    } else {
      showBubble("her", data.text || copy.empty_reply, meta, 8500);
    }
    lastTalkAt = Date.now();
    fetch("/api/action?id=talk", { cache: "no-store" }).catch(() => {});
  }

  /* 她自己起头（T69.2）：每隔一会儿问一次引擎"她现在想不想说话"。
     ★ 界面上**没有**"让她说话"的按钮 —— 想说就自己说，不想说就安静。
     引擎不给阈值以上的冲动，这里就什么也不做。 */
  async function maybeSpeakOnOwn() {
    if (busy || document.hidden || input.value.trim()) return;
    if (Date.now() - lastTalkAt < 25000) return;
    try {
      const r = await fetch("/api/urge.json", { cache: "no-store" });
      if (!r.ok) return;
      const u = await r.json();
      if (!u.would_speak) return;
      busy = true;
      const intent = u.intent || "chat";
      const res = await request("", false, { self: u.intent_id || 1 });
      const data = res.data;
      finishSend(data, res.status, false, null, intent);
    } catch (_) { /* 服务不在就等下一轮 */ }
    finally { busy = false; }
  }

  setInterval(maybeSpeakOnOwn, 12000);

  async function send(dry) {
    if (busy) return;
    const text = input.value.trim();
    if (!text) { input.focus(); showToast(copy.empty); return; }
    busy = true;
    sendButton.disabled = true;
    $("character").classList.add("thinking");
    if (!dry) {
      showBubble("you", text, null, 0);
      input.value = "";
      input.style.height = "40px";
      fetch("/api/action?id=think", { cache: "no-store" }).catch(() => {});
    }
    try {
      /* 先问节奏（本地、几微秒），再按引擎给的停顿时长把字放出来。
         注意：请求和"等待"是并行的 —— 等的是她说话的节奏，不是网络往返。 */
      const th = dry ? { mode: "blurt", delay_ms: 0, preface: "" } : await thinkFor(text);
      const waitMs = Number(th.delay_ms || 0);
      const pendingText = th.mode === "blurt" ? copy.thinking_short : (th.preface || copy.thinking_long);
      if (!dry) {
        showBubble("her", pendingText, null, 0, { pending: true });
        const job = request(text, dry);
        await sleep(waitMs);
        if (th.preface) {
          showBubble("her", th.preface, null, 0, { pending: true });
          await sleep(650);
        }
        const { status, data } = await job;
        return finishSend(data, status, dry, th);
      }
      const { status, data } = await request(text, dry);
      finishSend(data, status, dry, th);
    } catch (_) {
      showBubble("her", copy.offline, { label: copy.not_sent, dot: "none", detail: copy.send_failed }, 0);
    } finally {
      busy = false;
      sendButton.disabled = false;
      $("character").classList.remove("thinking");
      input.focus();
    }
  }

  sendButton.addEventListener("click", () => send(false));
  $("talk-toggle").addEventListener("click", () => input.focus());
  $("more").addEventListener("click", () => {
    options.hidden = !options.hidden;
    $("more").setAttribute("aria-expanded", options.hidden ? "false" : "true");
  });
  $("reset").addEventListener("click", async () => {
    try {
      const r = await fetch("/api/context.json?reset=1", { cache: "no-store" });
      if (!r.ok) throw new Error("reset");
      showBubble("her", copy.reset_done, null, 4500);
      options.hidden = true;
    } catch (_) { showToast(copy.offline); }
  });
  $("dry").addEventListener("toggle", () => {
    if (!$("dry").open) {
      $("dry-output").hidden = true;
      return;
    }
    if (busy) return;
    if (!input.value.trim()) { showToast(copy.empty); return; }
    return send(true);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send(false);
    }
  });
  input.addEventListener("input", () => {
    input.style.height = "40px";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  });
  $("character").addEventListener("dblclick", () => input.focus());

  /* 产品视图原型用同源帧接口；原生窗口接入留给 T62.2，不触碰测试台舞台组件。 */
  const character = $("character");
  let frameBusy = false;
  let lastObjectUrl = "";
  async function nextFrame() {
    if (!frameBusy && !document.hidden) {
      frameBusy = true;
      try {
        const r = await fetch("/api/frame.png?t=" + Date.now(), { cache: "no-store" });
        if (r.ok) {
          const blob = await r.blob();
          const url = URL.createObjectURL(blob);
          character.src = url;
          if (lastObjectUrl) URL.revokeObjectURL(lastObjectUrl);
          lastObjectUrl = url;
        }
      } catch (_) { /* 页面尚未连到本地预览服务时保留初始帧 */ }
      finally { frameBusy = false; }
    }
    setTimeout(nextFrame, 1000 / 30);
  }

  /* 产品工作区。只接已经存在的接口：状态、记忆、形态、发型、表情、动作。
     任务 / 创作 / 代码 / 技能没有后端，首页只说明还没接，不造假列表。
     测试替身没有这些节点时整段跳过，不碰原来的聊天链路。 */
  const workspace = $("workspace");
  const panes = {
    home: $("pane-home"),
    talk: $("pane-talk"),
    memory: $("pane-memory"),
    look: $("pane-look"),
  };

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  async function getJson(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(url);
    return r.json();
  }

  function showPane(id) {
    Object.keys(panes).forEach((key) => {
      if (panes[key]) panes[key].hidden = key !== id;
    });
    document.querySelectorAll("#workspace-nav button").forEach((button) => {
      button.classList.toggle("active", button.dataset.pane === id);
    });
  }

  function openWorkspace(on) {
    if (!workspace) return;
    workspace.hidden = !on;
    document.body.classList.toggle("workspace-on", on);
    $("desktop-pet").classList.toggle("workspace-on", on);
    if (on) refreshWorkspace();
  }

  async function refreshWorkspace() {
    if (!workspace || workspace.hidden) return;
    let info = {};
    let memory = {};
    try { info = await getJson("/api/info.json"); } catch (_) { info = {}; }
    try { memory = await getJson("/api/memory.json"); } catch (_) { memory = {}; }
    renderHome(info);
    renderTalk();
    renderMemory(memory);
    renderLook(info);
  }

  function renderHome(info) {
    const pane = panes.home;
    if (!pane) return;
    pane.replaceChildren();
    const grid = el("div", "status-grid");
    [
      [copy.mood, info.mood || "—"],
      [copy.affection, (info.tier_name || "—") + " · " + (info.affection != null ? info.affection : "—")],
      [copy.form, info.form_name || info.form || "—"],
      [copy.now_action, info.action || "—"],
    ].forEach(([label, value]) => {
      const card = el("div", "status-card");
      card.append(el("span", "", label), el("b", "", value));
      grid.appendChild(card);
    });
    pane.append(grid, el("p", "note-card", copy.unbuilt || ""));
  }

  function renderTalk() {
    const pane = panes.talk;
    if (!pane) return;
    pane.replaceChildren(el("p", "note-card", copy.talk_hint || ""));
  }

  function renderMemory(memory) {
    const pane = panes.memory;
    if (!pane) return;
    pane.replaceChildren();
    const form = el("div", "remember");
    const hint = el("p", "section-label", copy.remember_label || "");
    const input = document.createElement("input");
    input.maxLength = 240;
    input.placeholder = copy.remember_placeholder || "";
    const save = el("button", "", copy.remember_button || "");
    save.type = "button";
    save.addEventListener("click", async () => {
      const text = input.value.trim();
      if (!text) { showToast(copy.empty); return; }
      try {
        const data = await getJson("/api/memory/add?text=" + encodeURIComponent(text) + "&salience=6");
        if (!data.ok) throw new Error("add");
        input.value = "";
        showToast(copy.saved);
        refreshWorkspace();
      } catch (_) { showToast(copy.offline); }
    });
    form.append(hint, input, save);
    pane.appendChild(form);
    const items = (memory.list && memory.list.items) || [];
    if (!items.length) {
      pane.appendChild(el("p", "note-card", copy.memory_empty || ""));
      return;
    }
    items.forEach((item) => {
      if (item.deleted) return;
      const card = el("article", "mem-card");
      card.append(el("p", "", item.text || ""), el("small", "", item.date || ""));
      const reason = document.createElement("input");
      reason.placeholder = copy.forget_reason_placeholder || "";
      const forget = el("button", "", copy.forget || "");
      forget.type = "button";
      forget.addEventListener("click", async () => {
        if (!reason.value.trim()) { showToast(copy.need_reason); return; }
        try {
          const data = await getJson("/api/memory/del?id=" + encodeURIComponent(item.id) + "&reason=" + encodeURIComponent(reason.value.trim()));
          if (!data.ok) throw new Error("del");
          showToast(copy.deleted);
          refreshWorkspace();
        } catch (_) { showToast(copy.offline); }
      });
      card.append(reason, forget);
      pane.appendChild(card);
    });
  }

  function addPills(parent, label, specs) {
    parent.appendChild(el("p", "section-label", label));
    const row = el("div", "pill-row");
    specs.forEach((spec) => {
      const button = el("button", "pill" + (spec.disabled ? " planned" : ""), spec.label);
      button.type = "button";
      button.disabled = !!spec.disabled;
      if (!spec.disabled && spec.run) button.addEventListener("click", spec.run);
      row.appendChild(button);
    });
    parent.appendChild(row);
  }

  function renderLook(info) {
    const pane = panes.look;
    if (!pane) return;
    pane.replaceChildren();
    const roadmap = info.form_roadmap || [];
    if (roadmap.length) {
      addPills(pane, copy.form, roadmap.map((item) => ({
        label: item.name + (item.status === "ready" ? "" : " · " + (copy.planned || "")),
        disabled: item.status !== "ready",
        run: async () => {
          await getJson("/api/form?id=" + encodeURIComponent(item.id));
          showToast(copy.switched);
          refreshWorkspace();
        },
      })));
    }
    addPills(pane, copy.hair, [
      ["long", copy.hair_long],
      ["twin", copy.hair_twin],
      ["pony", copy.hair_pony],
    ].map(([id, label]) => ({
      label,
      run: async () => {
        await getJson("/api/pose?group=hairstyle&id=" + id);
        showToast(copy.switched);
      },
    })));
    addPills(pane, copy.hood, [
      ["up", copy.hood_up],
      ["down", copy.hood_down],
    ].map(([id, label]) => ({
      label,
      run: async () => {
        await getJson("/api/pose?group=hood_pose&id=" + id);
        showToast(copy.switched);
      },
    })));
    const expressions = info.expressions || [];
    if (expressions.length) {
      addPills(pane, copy.expression, expressions.slice(0, 8).map((item) => ({
        label: item.name || item.id,
        run: async () => {
          await getJson("/api/expression?id=" + encodeURIComponent(item.id));
          showToast(copy.switched);
        },
      })));
    }
    const names = info.action_names || [];
    const ids = info.actions || [];
    const wanted = ["idle", "wave", "wave_both", "surprised", "heart_hands"];
    const actions = wanted.map((id) => {
      const index = ids.indexOf(id);
      return index >= 0 ? { id, label: names[index] || id } : null;
    }).filter(Boolean);
    if (actions.length) {
      addPills(pane, copy.actions, actions.map((item) => ({
        label: item.label,
        run: async () => {
          await getJson("/api/action?id=" + encodeURIComponent(item.id));
          showToast(copy.switched);
          refreshWorkspace();
        },
      })));
    }
  }

  if (workspace && $("workspace-toggle") && $("workspace-close")) {
    $("workspace-toggle").addEventListener("click", () => openWorkspace(workspace.hidden));
    $("workspace-close").addEventListener("click", () => openWorkspace(false));
    document.querySelectorAll("#workspace-nav button").forEach((button) => {
      button.addEventListener("click", () => showPane(button.dataset.pane));
    });
    showPane("home");
  }

  loadCopy().then(nextFrame).catch(() => {
    console.error(copy.copy_load_failed);
  });
})();
