/* 小寻 · 动态立绘测试台
 *
 * 这个页面只干三件事：
 *   1. 把引擎的每个互动/动作端点都做成一个按钮，手上能点；
 *   2. 把手动参数（眨眼、视线、缩放）做成滑杆，能连续扫一遍看动画；
 *   3. 「自动测试」按顺序打一串请求，并且**用画面本身当断言**——
 *      抓 /api/frame.png 的字节做哈希，比较两个状态的画面是否真的变了。
 *      纯看 HTTP 200 没意义，引擎可能收了参数却没动。
 *
 * 页面是从 /media/web/test.html 提供的，所以 fetch 一律用绝对路径 /api/...、
 * /media/...，不要用相对路径（相对路径会落到 /media/web/ 下面去）。
 */

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let info = null;          /* 最近一次 /api/info.json */
let framesShown = 0;      /* 用来算刷新率 */
let fpsMark = performance.now();
let suiteRunning = false;

/* ---------- 日志 ---------- */
function log(msg, cls) {
  const el = $("log");
  const t = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  el.innerHTML += `<span class="dim">${t}</span> <span class="${cls || ""}">${msg}</span>\n`;
  el.scrollTop = el.scrollHeight;
}

/* ---------- 带计时的请求 ---------- */
async function api(path) {
  const t0 = performance.now();
  try {
    const r = await fetch(path, { cache: "no-store" });
    const ms = (performance.now() - t0).toFixed(0);
    const txt = await r.text();
    let data = null;
    try { data = JSON.parse(txt); } catch (e) { /* 不是 JSON 就算了 */ }
    log(`${r.ok ? "✓" : "✗"} ${path} → ${r.status} ${ms}ms`, r.ok ? "ok" : "bad");
    return { ok: r.ok, status: r.status, data, text: txt, ms: +ms };
  } catch (e) {
    log(`✗ ${path} → ${e}`, "bad");
    return { ok: false, status: 0, data: null, text: String(e), ms: -1 };
  }
}

/* 抓一帧 PNG，算个 32 位哈希（FNV-1a）。同一状态哈希稳定，画面变了哈希就变。 */
async function frameHash() {
  const r = await fetch("/api/frame.png?t=" + Date.now(), { cache: "no-store" });
  const buf = new Uint8Array(await r.arrayBuffer());
  let h = 0x811c9dc5;
  for (let i = 0; i < buf.length; i++) {
    h ^= buf[i];
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return { hash: h >>> 0, bytes: buf.length };
}

/* ---------- 画面刷新：在途保护 + 丢弃迟到帧 + 按显示尺寸要图 ----------
   逻辑在 web/frameloop.js（纯函数，tests/test_web.js 里有单测）。
   动机见那个文件的文件头：满尺寸一帧 190 KB，10fps 要 1.86 MB/s，
   云端预览撑不住就会"一卡一跳"。 */
const frameLoop = ZFrameLoop.makeFrameLoop({
  now: () => performance.now(),
  url: (s) => `/api/frame.png?s=${s}&t=${Date.now()}`,
  load: (url, ok, fail) => {
    const im = new Image();
    im.onload = ok; im.onerror = fail; im.src = url;
  },
  show: (url) => { $("pet").src = url; framesShown++; },
});

function refresh() {
  const img = $("pet");
  const w = img && img.clientWidth ? img.clientWidth : 0;
  const dpr = (typeof devicePixelRatio === "number" && devicePixelRatio > 0)
            ? devicePixelRatio : 1;
  frameLoop.tick(ZFrameLoop.frameScale(w, info ? info.frame_w : 0, dpr));
}

/* ---------- 状态条 ---------- */
async function loadInfo() {
  const r = await fetch("/api/info.json", { cache: "no-store" }).catch(() => null);
  if (!r || !r.ok) { $("hdr").textContent = "引擎没连上（预览进程没起？）"; return; }
  info = await r.json();
  $("hdr").innerHTML = `引擎 <code>${info.engine}</code> · 角色 <code>${info.character}</code>
     · 形态 <code>${info.form_name || info.form}</code> · 帧 ${info.frame_w}×${info.frame_h}`;
  $("p-act").textContent = "动作 " + info.action;
  $("p-expr").textContent = "表情 " + (info.expression || "无");
  $("p-expr").className = "pill" + (info.expression ? " on" : "");
  $("p-blink").textContent = "眨眼 " + info.blink.toFixed(2) +
      (info.blink_manual >= 0 ? "（手动）" : "（自动）");
  $("p-scale").textContent = "缩放 " + info.scale.toFixed(2);
  $("p-sleep").textContent = info.sleeping ? "睡眠中" : "清醒";
  $("p-sleep").className = "pill" + (info.sleeping ? " on" : "");
  if (!$("acts").dataset.ready) buildButtons();
}

/* ---------- 按钮 ---------- */
function buildButtons() {
  if (!info) return;
  $("acts").dataset.ready = "1";

  /* 互动：对应 zpet 的几种输入 */
  const inter = [
    ["摸头", () => pokeAt("head", 0), "pri"],
    ["抚摸身体", () => pokeAt("body", 0), ""],
    ["戳脚", () => pokeAt("feet", 0), ""],
    ["锤一下", () => pokeAt("head", 1), "warn"],
    ["接电话", () => "/api/call?kind=call_start", ""],
    ["对面说话", () => "/api/call?kind=call_user_speaking", ""],
    ["她回话", () => "/api/call?kind=call_reply&text=" + encodeURIComponent("我在听着呢") + "&mood=happy", ""],
    ["挂断", () => "/api/call?kind=call_end", ""],
    ["开心", () => "/api/express?mood=happy", ""],
    ["难过", () => "/api/express?mood=sad", ""],
    ["惊讶", () => "/api/express?mood=surprised", ""],
    ["平静", () => "/api/express?mood=calm", ""],
    ["放空 10 分钟", () => "/api/idle?s=600", ""],
    ["唤醒", () => "/api/idle?s=0", ""],
  ];
  $("inter").innerHTML = inter.map(([t, , c], i) =>
    `<button class="${c}" data-i="${i}">${t}</button>`).join("") +
    `<div class="muted" style="font-size:12px;margin-top:4px">
       摸头/抚摸/戳脚走的是 <code>/api/poke?x=&y=&tool=</code>，引擎按 rig.json 的
       <code>regions</code> 判断摸到了哪儿；通话走 <code>/api/call?kind=</code>。
     </div>`;
  $("inter").dataset.n = inter.length;
  window.__inter = inter;
  $("inter").querySelectorAll("button").forEach((b) => {
    b.onclick = async () => { await api(window.__inter[+b.dataset.i][1]()); await pulse(); };
  });

  /* 动作：直接来自 rig.json */
  $("acts").innerHTML = info.actions.map((a) =>
    `<button class="sm" data-a="${a}">${a}</button>`).join("");
  $("acts").querySelectorAll("button").forEach((b) => {
    b.onclick = async () => { await api("/api/action?id=" + encodeURIComponent(b.dataset.a)); await pulse(); };
  });

  /* 表情：叠在动作之上，和动作按钮是两条轨 */
  $("exprs").innerHTML =
    (info.expressions || []).map((e) =>
      `<button class="sm" data-e="${e.id}" title="${e.id}">${e.name || e.id}</button>`).join("") +
    `<button class="sm" data-e="">取消表情</button>` +
    `<div class="muted" style="font-size:12px;margin-top:4px">
       走 <code>/api/expression?id=</code>（取消是 <code>off=1</code>）。表情只写
       <code>params</code> 里的参数，带淡入淡出，动作该怎么跑还怎么跑。
     </div>`;
  $("exprs").querySelectorAll("button").forEach((b) => {
    b.onclick = async () => {
      await api(b.dataset.e ? "/api/expression?id=" + encodeURIComponent(b.dataset.e)
                            : "/api/expression?off=1");
      await pulse(); loadInfo();
    };
  });

  /* 差分（Pose 互斥组）：同组只有一个档位可见，切换带淡化 */
  if ($("poses")) {
    const gs = info.poses || [];
    $("poses").innerHTML = gs.length
      ? gs.map((g) =>
          `<div style="margin-bottom:6px"><b>${g.id}</b>　` +
          g.entries.map((e) =>
            `<button class="sm${e === g.current ? " on" : ""}" data-pg="${g.id}" data-pe="${e}">${e}</button>`
          ).join("") +
          `<button class="sm${g.current === "" ? " on" : ""}" data-pg="${g.id}" data-pe="none">none</button></div>`
        ).join("") +
        `<div class="muted" style="font-size:12px">走 <code>/api/pose?group=&id=</code>，
          <code>none</code> 把整组关掉。等价 Live2D 的 <code>pose3.json</code>。</div>`
      : `<div class="muted" style="font-size:12px">这个角色没有互斥差分组</div>`;
    $("poses").querySelectorAll("button").forEach((b) => {
      b.onclick = async () => {
        await api(`/api/pose?group=${encodeURIComponent(b.dataset.pg)}&id=${encodeURIComponent(b.dataset.pe)}`);
        await pulse(); loadInfo();
      };
    });
  }

  /* 形态与服装 */
  let h = "";
  info.forms.forEach((f, i) => {
    h += `<button class="sm" data-f="${f}">${(info.form_names && info.form_names[i]) || f}</button>`;
  });
  h += "<br>";
  (info.outfits || []).forEach((o, i) => {
    h += `<button class="sm" data-o="${o}">${(info.outfit_names && info.outfit_names[i]) || o}</button>`;
  });
  $("forms").innerHTML = h || "<span class='muted'>这个角色只有一种形态</span>";
  $("forms").querySelectorAll("button").forEach((b) => {
    b.onclick = async () => {
      await api(b.dataset.f ? "/api/form?id=" + b.dataset.f : "/api/outfit?id=" + b.dataset.o);
      await pulse(); loadParts();
    };
  });
}

/* 区域中心的帧坐标：区域定义在画布坐标里，但 /api/poke 收的是帧坐标，
   引擎内部 zrig_frame_to_canvas 再换回去，所以这里按比例给就行。 */
const REGION_FX = { head: 0.50, body: 0.50, feet: 0.45 };   /* 脚不能取正中：两腿之间是透明的 */
const REGION_FY = { head: 0.11, body: 0.40, feet: 0.84 };   /* 脚也别取 0.9：区域矩形比人物长 */

function regionXY(region) {
  const fw = info ? info.frame_w : 848, fh = info ? info.frame_h : 1360;
  return [Math.round(fw * (REGION_FX[region] || 0.5)), Math.round(fh * (REGION_FY[region] || 0.4))];
}
function pokeAt(region, tool) {
  const [x, y] = regionXY(region);
  return `/api/poke?x=${x}&y=${y}&tool=${tool || 0}`;
}
/* 等当前动作演完：动作没演完时新请求会被状态机按优先级挡掉 */
async function settle(ms) {
  const t0 = performance.now();
  while (performance.now() - t0 < (ms || 3000)) {
    const d = await fetch("/api/info.json", { cache: "no-store" }).then((x) => x.json());
    if (["idle", "breath", "sway"].includes(d.action)) return true;
    await sleep(120);
  }
  return false;
}

/* 点完按钮连抓几帧，动作起手的那一下能看见 */
async function pulse() {
  for (let i = 0; i < 6; i++) { refresh(); await sleep(70); }
  loadInfo(); loadSpeech();
}

async function loadSpeech() {
  const r = await fetch("/api/speech.json", { cache: "no-store" }).catch(() => null);
  if (!r || !r.ok) return;
  const d = await r.json();
  if (d && d.line) {
    $("speech").innerHTML = "「" + d.line + "」" +
      `<span class="muted" style="font-size:12px"> · 好感 ${d.affection} ${d.tier || ""}</span>`;
  }
}

/* ---------- 口型同步（A4） ---------- */
let lsTimer = null;
async function loadLipsync() {
  const info = await fetch("/api/info.json").then((x) => x.json()).catch(() => null);
  if (!info) return;
  const url = `/media/characters/${info.character}/voice/lipsync/index.json`;
  const idx = await fetch(url).then((x) => (x.ok ? x.json() : null)).catch(() => null);
  const sel = $("ls-line");
  if (!idx || !idx.items || !idx.items.length) {
    sel.innerHTML = "<option>（没有包络，先跑 tools/make_lipsync.py）</option>";
    return;
  }
  sel.innerHTML = idx.items
    .map((it) => `<option value="${it.id}">${it.text || it.id}（${it.dur}s）</option>`)
    .join("");
}
/* ---------- 口型音素（母音識別）----------
   音素给嘴形、强度给音量 —— 和 airi 的 wlipsync vowel driver 一个路子：
   每帧只认一个“赢家”母音 + 当前响度，而不是五个口型一起加权糊在一起。 */
async function loadVisemes() {
  const d = await fetch("/api/params.json").then((x) => x.json()).catch(() => null);
  const box = $("visemes");
  if (!d || !d.visemes || !d.visemes.length) {
    box.textContent = "（这个角色没有音素表）";
    return;
  }
  const label = { SIL: "闭嘴", A: "a / あ", I: "i / い", U: "u / う",
                  E: "e / え", O: "o / お", N: "n / ん" };
  box.innerHTML = d.visemes
    .map((v) => `<button class="sm" data-v="${v}">${label[v] || v}</button>`).join("");
  box.querySelectorAll("button").forEach((b) => {
    b.onclick = async () => {
      const w = +$("s-visw").value;
      const r = await api(`/api/viseme?v=${encodeURIComponent(b.dataset.v)}&w=${w.toFixed(2)}`);
      mixRefresh();
      $("vis-info").textContent = r && r.ok
        ? `音素 ${r.viseme || "—"} · 强度 ${(+r.weight).toFixed(2)} · ` +
          `OpenY ${(+r.open).toFixed(2)} / Form ${(+r.form).toFixed(2)}`
        : "设置失败";
      refresh();
    };
  });
}
/* ---------- 表情 × 口型：分层求值看板 ----------
   参考 Cubism 的 ICubismUpdater 执行序（Expression 300 在 LipSync 700 之前）、
   airi devtools 的分层显示、BongoCat expression.rs 的三累加器求值。 */
const MIX_PARAMS = ["ParamMouthOpenY", "ParamMouthForm"];
async function loadMixPanel() {
  const d = await fetch("/api/params.json").then((x) => x.json()).catch(() => null);
  const es = (info && info.expressions) || [];
  const se = $("mx-expr"), sv = $("mx-vis");
  if (!se || !sv) return;
  se.innerHTML = `<option value="">（无表情）</option>` +
    es.map((e) => `<option value="${e.id}">${e.name || e.id}</option>`).join("");
  sv.innerHTML = `<option value="">（不说话）</option>` +
    ((d && d.visemes) || []).map((v) => `<option value="${v}">${v}</option>`).join("");
  mixRefresh();
}
async function mixApply() {
  const e = $("mx-expr").value, v = $("mx-vis").value;
  await api(e ? "/api/expression?id=" + encodeURIComponent(e) : "/api/expression?off=1");
  await api(v ? `/api/viseme?v=${v}&w=${(+$("s-visw").value).toFixed(2)}` : "/api/viseme?v=off");
  await sleep(320);                 /* 等表情淡入和口型平滑走完 */
  refresh(); mixRefresh();
}
async function mixPreset(e, v) {
  $("mx-expr").value = e; $("mx-vis").value = v;
  await mixApply();
}
async function mixRefresh() {
  const body = $("mx-body");
  if (!body) return;
  const d = await fetch("/api/params.json", { cache: "no-store" })
    .then((x) => x.json()).catch(() => null);
  if (!d || !d.params) return;
  const rows = MIX_PARAMS.map((id) => d.params.find((p) => p.id === id)).filter(Boolean);
  body.innerHTML = rows.map((p) => {
    const moved = Math.abs((p.effective ?? 0) - (p.expr ?? 0)) > 0.005;
    return `<tr>
      <td><code>${p.id}</code></td>
      <td>${(+p.value).toFixed(3)}</td>
      <td>${(+(p.expr ?? 0)).toFixed(3)}</td>
      <td style="color:${moved ? "#6cb4c0" : "#cfd4e0"}">
        <b>${(+(p.effective ?? 0)).toFixed(3)}</b></td></tr>`;
  }).join("");
  const vi = d.viseme || {};
  $("mx-info").textContent =
    `当前表情 ${(d.expression || "—")} · 口型 ${vi.id || "—"}` +
    (vi.id ? ` 强度 ${(+vi.weight).toFixed(2)}` : "") +
    ` · 口型权重 ${(d.viseme_weight ?? 0.8)}（官方 LipSync 用 0.8）`;
}

async function playVowels() {
  const seq = ["A", "I", "U", "E", "O", "SIL"];
  for (const v of seq) {
    await api(`/api/viseme?v=${v}&w=${v === "SIL" ? 0 : (+$("s-visw").value).toFixed(2)}`);
    $("vis-info").textContent = "念：" + v;
    refresh();
    await sleep(260);
  }
  await api("/api/viseme?v=off");
  refresh();
}

async function speakLine() {
  const id = $("ls-line").value;
  if (!id) return;
  const r = await fetch("/api/speak?id=" + encodeURIComponent(id)).then((x) => x.json())
    .catch(() => null);
  if (!r || !r.ok) { log("口型包络读不到：" + id, "bad"); return; }
  log(`说：「${r.text}」（${r.remain.toFixed(2)}s）`, "ok");
  if (lsTimer) clearInterval(lsTimer);
  lsTimer = setInterval(async () => {
    const d = await fetch("/api/speech.json", { cache: "no-store" })
      .then((x) => x.json()).catch(() => null);
    if (!d) return;
    const ls = d.lipsync || { active: false, level: 0, remain: 0 };
    $("ls-bar").style.width = Math.round(ls.level * 100) + "%";
    $("ls-info").textContent = ls.active
      ? `开口度 ${ls.level.toFixed(2)} · 还剩 ${ls.remain.toFixed(1)}s`
      : "播完";
    refresh();
    if (!ls.active) { clearInterval(lsTimer); lsTimer = null; }
  }, 60);
}

/* ---------- 滑杆 ---------- */
function setBlink(v) {
  if (v === "auto") { $("v-blink").textContent = "auto"; $("s-blink").value = 0; api("/api/blink?v=auto"); }
  else { $("v-blink").textContent = (+v).toFixed(2); api("/api/blink?v=" + v); }
}
function bindVisemeSlider() {
  const s = $("s-visw");
  if (s) s.addEventListener("input", (e) => { $("v-visw").textContent = (+e.target.value).toFixed(2); });
}
function bindSliders() {
  let gaze = { x: 0, y: 0 };
  const sendGaze = () => api(`/api/gaze?x=${gaze.x.toFixed(2)}&y=${gaze.y.toFixed(2)}`);
  $("s-blink").oninput = (e) => setBlink(e.target.value);
  $("s-gx").oninput = (e) => { gaze.x = +e.target.value; $("v-gx").textContent = gaze.x.toFixed(2); sendGaze(); };
  $("s-gy").oninput = (e) => { gaze.y = +e.target.value; $("v-gy").textContent = gaze.y.toFixed(2); sendGaze(); };
  $("s-scale").oninput = (e) => {
    $("v-scale").textContent = (+e.target.value).toFixed(2);
    api("/api/scale?s=" + e.target.value);
  };
}
function resetParams() {
  $("s-blink").value = 0; $("s-gx").value = 0; $("s-gy").value = 0; $("s-scale").value = 1;
  $("v-blink").textContent = "auto"; $("v-gx").textContent = "0.00";
  $("v-gy").textContent = "0.00"; $("v-scale").textContent = "1.00";
  api("/api/blink?v=auto"); api("/api/gaze?off=1"); api("/api/scale?s=1");
}

/* ---------- 命名参数层：按 /api/params.json 自动长滑条 ---------- */
let paramTimer = null;
async function loadParams() {
  const r = await fetch("/api/params.json").then((x) => x.json()).catch(() => null);
  if (!r || !r.params) return;
  const box = $("params");
  $("paramcount").textContent = `${r.params.length} 个`;
  box.innerHTML = "";
  r.params.forEach((p) => {
    const row = document.createElement("label");
    row.className = "row";
    const step = (p.max - p.min) / 200;
    row.innerHTML =
      `<span title="${p.id}">${p.label || p.id}${p.builtin ? " ·内建" : ""}</span>` +
      `<input type="range" min="${p.min}" max="${p.max}" step="${step}" value="${p.value}" data-id="${p.id}">` +
      `<code id="pv-${p.id}">${(+p.value).toFixed(2)}</code>`;
    const sl = row.querySelector("input");
    sl.oninput = (e) => {
      $("pv-" + p.id).textContent = (+e.target.value).toFixed(2);
      api(`/api/param?id=${encodeURIComponent(p.id)}&v=${(+e.target.value).toFixed(4)}`);
    };
    box.appendChild(row);
  });
  /* 内建参数（自动眨眼、视线）会自己动，低频回读一下让数字是活的 */
  if (paramTimer) clearInterval(paramTimer);
  paramTimer = setInterval(refreshParamValues, 700);
}
async function refreshParamValues() {
  if (document.hidden) return;
  const r = await fetch("/api/params.json").then((x) => x.json()).catch(() => null);
  if (!r || !r.params) return;
  r.params.forEach((p) => {
    const el = document.getElementById("pv-" + p.id);
    if (!el || !p.builtin) return;          /* 手拖的那些不要被覆盖 */
    el.textContent = (+p.value).toFixed(2);
    const sl = document.querySelector(`#params input[data-id="${p.id}"]`);
    if (sl && document.activeElement !== sl) sl.value = p.value;
  });
}
function resetAllParams() { api("/api/param?all=1").then(loadParams); }

/* ---------- 画面上的鼠标：悬停＝视线，点击＝摸头 ---------- */
function bindStage() {
  const img = $("pet");
  let last = 0, lastRegion = 0;
  img.addEventListener("mousemove", (e) => {
    const now = performance.now();
    /* hover 驱动视线跟随，要跟手 → 60ms；
       region 只刷新"鼠标下：xxx"那行字，250ms 足够，省下的带宽留给帧。
       （两条原来都是 90ms，等于每秒 22 个请求在和帧抢链路） */
    if (now - last < 60) return;
    last = now;
    const b = img.getBoundingClientRect();
    const x = Math.round((e.clientX - b.left) / b.width * (info ? info.frame_w : b.width));
    const y = Math.round((e.clientY - b.top) / b.height * (info ? info.frame_h : b.height));
    fetch(`/api/hover?x=${x}&y=${y}&in=1`, { cache: "no-store" });
    if (now - lastRegion < 250) return;
    lastRegion = now;
    fetch(`/api/region?x=${x}&y=${y}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((q) => {
        const el = $("p-region");
        if (el) {
          el.textContent = "鼠标下：" + (q.region ? `${q.region} → ${q.action}` : "没碰到人");
          el.className = "pill" + (q.region ? " on" : "");
        }
      });
  });
  img.addEventListener("mouseleave", () => fetch("/api/hover?x=0&y=0&in=0", { cache: "no-store" }));
  img.addEventListener("click", async (e) => {
    const b = img.getBoundingClientRect();
    const fw = info ? info.frame_w : b.width, fh = info ? info.frame_h : b.height;
    const x = Math.round((e.clientX - b.left) / b.width * fw);
    const y = Math.round((e.clientY - b.top) / b.height * fh);
    await api(`/api/poke?x=${x}&y=${y}&tool=0`);
    await pulse();
  });
}

/* ---------- 零件表 ---------- */
async function loadParts() {
  const form = info ? info.form : "teen";
  const chr = info ? info.character : "xiaoxun";
  const url = `/media/characters/${chr}/forms/${form}/rig.json`;
  const r = await fetch(url, { cache: "no-store" }).catch(() => null);
  if (!r || !r.ok) { log("✗ 读不到 " + url, "bad"); return; }
  const rig = await r.json();
  const rows = rig.parts.slice().sort((a, b) => a.layer - b.layer).map((p) => {
    const tags = (p.tags || []).map((t) => `<span class="tag">${t}</span>`).join("");
    const extra = p.eyelid_travel ? `<span class="tag">行程${p.eyelid_travel}</span>` : "";
    return `<tr><td>${p.layer}</td><td>${p.id}</td>
            <td class="muted">${p.pos[0]},${p.pos[1]}</td>
            <td>${tags}${extra}</td>
            <td class="muted">${p.mask || (p.mask_only ? "（遮罩源）" : "")}</td></tr>`;
  }).join("");
  $("parts").querySelector("tbody").innerHTML = rows;
  $("partcount").textContent = `共 ${rig.parts.length} 件 · 动作 ${rig.actions.length} 个`;
}

/* ---------- 自动测试 ---------- */
function addResult(name, pass, detail) {
  $("results").innerHTML +=
    `<div class="res"><b class="${pass ? "pass" : "fail"}">${pass ? "通过" : "失败"}</b>
     <span>${name}</span><span class="muted" style="margin-left:auto">${detail || ""}</span></div>`;
}

async function runSuite() {
  if (suiteRunning) return;
  suiteRunning = true;
  const btn = $("btn-run"); btn.disabled = true; btn.textContent = "跑着呢…";
  $("results").innerHTML = ""; $("summary").textContent = "";
  let pass = 0, fail = 0;
  const check = (name, ok, detail) => { ok ? pass++ : fail++; addResult(name, ok, detail); };

  /* 1. 基本端点 */
  const inf = await api("/api/info.json");
  check("info.json 能读", inf.ok && inf.data && !!inf.data.engine,
        inf.data ? "引擎 " + inf.data.engine : "");
  const f0 = await frameHash();
  check("frame.png 是张真图", f0.bytes > 2000, f0.bytes + " 字节");

  /* 2. 眨眼：睁 / 闭 两帧画面必须不一样 */
  await api("/api/blink?v=0"); await sleep(260);
  const open = await frameHash();
  await api("/api/blink?v=1"); await sleep(260);
  const shut = await frameHash();
  check("眨眼 0 → 1 画面有变化", open.hash !== shut.hash,
        `哈希 ${open.hash.toString(16)} → ${shut.hash.toString(16)}`);
  await api("/api/blink?v=0.5"); await sleep(260);
  const half = await frameHash();
  check("眨眼 0.5 是第三种画面", half.hash !== open.hash && half.hash !== shut.hash,
        half.hash.toString(16));
  const bi = await api("/api/info.json");
  check("info 里能读回手动眨眼值", bi.data && Math.abs(bi.data.blink_manual - 0.5) < 0.01,
        bi.data ? "blink_manual=" + bi.data.blink_manual : "");
  await api("/api/blink?v=auto");
  const ba = await api("/api/info.json");
  check("切回自动眨眼", ba.data && ba.data.blink_manual < 0, "blink_manual<0");

  /* 2.5 命名参数层：写一个参数画面必须变，复位必须回去 */
  {
    const r = await fetch("/api/params.json").then((x) => x.json()).catch(() => null);
    const n = r && r.params ? r.params.length : 0;
    check("参数表能读出来（/api/params.json）", n >= 5, `${n} 个参数`);
    if (n) {
      await api("/api/action?id=sleep&force=1"); await sleep(260);   /* 先停下来，免得呼吸干扰 */
      const base = await frameHash();
      await api("/api/param?id=ParamMouthOpenY&v=1"); await sleep(260);
      const open = await frameHash();
      check("写 ParamMouthOpenY 画面有变化（参数层真的接到渲染上）",
            base.hash !== open.hash,
            `${base.hash.toString(16)} → ${open.hash.toString(16)}`);
      await api("/api/param?id=ParamMouthOpenY&reset=1"); await sleep(120);
      const after = await fetch("/api/params.json").then((x) => x.json());
      const mo = after.params.find((p) => p.id === "ParamMouthOpenY");
      check("参数复位后值回默认", mo && Math.abs(mo.value - mo.default) < 1e-6,
            mo ? `value=${mo.value}` : "读不到");
      const bad = await fetch("/api/param?id=ParamNope&v=1").then((x) => x.status);
      check("不存在的参数要报 404（不能假装成功）", bad === 404, `HTTP ${bad}`);
      await api("/api/action?id=idle&force=1");
    }
  }

  /* 2.6 表情层：叠加后画面要变，动作不能被顶掉 */
  {
    const list = (info && info.expressions) || [];
    check("表情表能读出来", list.length > 0, list.map((e) => e.id).join(" "));
    if (list.length) {
      await api("/api/action?id=sleep&force=1"); await sleep(260);
      const before = await frameHash();
      const actBefore = (await api("/api/info.json")).data.action;
      await api("/api/expression?id=" + list[0].id); await sleep(500);
      const after = await frameHash();
      const inf = (await api("/api/info.json")).data;
      check("叠表情后画面有变化", before.hash !== after.hash,
            `${before.hash.toString(16)} → ${after.hash.toString(16)}`);
      check("表情不会顶掉当前动作", inf.action === actBefore,
            `${actBefore} → ${inf.action}`);
      check("info 里能读回当前表情", inf.expression === list[0].id, inf.expression);
      const bad = await fetch("/api/expression?id=__nope__").then((x) => x.status);
      check("不存在的表情要报 404", bad === 404, `HTTP ${bad}`);
      await api("/api/expression?off=1"); await sleep(400);
      await api("/api/action?id=idle&force=1");
    }
  }

  /* 3. 视线：左看 / 右看 两帧必须不一样 */
  await api("/api/blink?v=0");           /* 闭着眼看不出眼球动，先睁开 */
  await api("/api/gaze?x=-1&y=0"); await sleep(300);
  const gl = await frameHash();
  await api("/api/gaze?x=1&y=0"); await sleep(300);
  const gr = await frameHash();
  check("视线左 / 右画面有变化", gl.hash !== gr.hash,
        `${gl.hash.toString(16)} → ${gr.hash.toString(16)}`);
  await api("/api/gaze?off=1"); await api("/api/blink?v=auto");

  /* 4. 动作：每个动作都能切过去，并且确实在动 */
  const acts = (info && info.actions) || [];
  let actOk = 0, moving = 0;
  for (const a of acts) {
    const r = await api("/api/action?id=" + encodeURIComponent(a));
    /* 马上读：clicked 只演 0.55 秒，慢一拍读到的是演完之后的 idle */
    const got = await fetch("/api/info.json", { cache: "no-store" }).then((x) => x.json());
    if (r.ok && got.action === a) actOk++;
    const s1 = await frameHash();
    await sleep(220);
    const s2 = await frameHash();
    if (s1.hash !== s2.hash) moving++;
  }
  check("每个动作都能切过去", actOk === acts.length, `${actOk}/${acts.length}`);
  check("动作期间画面在动（逐帧有差别）", moving >= Math.ceil(acts.length * 0.6),
        `${moving}/${acts.length} 个动作两帧不同`);

  /* 5. 互动区命中：点下去到底算摸到了哪儿 */
  for (const rg of ["head", "body", "feet"]) {
    const [x, y] = regionXY(rg);
    const q = await fetch(`/api/region?x=${x}&y=${y}`, { cache: "no-store" }).then((z) => z.json());
    check(`区域判定 ${rg}`, q.region === rg, `命中 ${q.region || "（空）"} → 动作 ${q.action || "—"}`);
  }

  /* 6. 互动：每种互动都要落到配置里写死的那个动作上 */
  const cases = [["摸头", pokeAt("head", 0), "head_pat"],
                 ["抚摸身体", pokeAt("body", 0), "stroke"],
                 ["戳脚", pokeAt("feet", 0), "surprised"],
                 ["锤一下", pokeAt("head", 1), "hammered"],
                 ["来电话", "/api/call?kind=call_start", "talk"],
                 ["对面说话", "/api/call?kind=call_user_speaking", "focus"]];
  for (const [name, url, want] of cases) {
    await settle();
    const before = await fetch("/api/info.json", { cache: "no-store" }).then((x) => x.json());
    const r = await api(url);
    await sleep(250);
    const after = await fetch("/api/info.json", { cache: "no-store" }).then((x) => x.json());
    const sp = await fetch("/api/speech.json", { cache: "no-store" }).then((x) => x.json()).catch(() => null);
    check(`互动「${name}」→ ${want}`, r.ok && after.action === want,
          `${before.action} → ${after.action}（规则 ${after.reason}）` +
          (sp && sp.line ? ` ·「${sp.line}」` : ""));
  }
  await api("/api/call?kind=call_end");

  /* 7. 连击：0.8 秒内连摸三次升级成 happy（zpet.c 的连击窗口） */
  await settle();
  let combo = false;
  for (let i = 0; i < 4 && !combo; i++) {
    await api(pokeAt("head", 0));
    await sleep(200);
    const d = await fetch("/api/info.json", { cache: "no-store" }).then((x) => x.json());
    if (d.reason === "pat_head_combo") combo = true;
  }
  check("连摸三次触发连击（pat_head_combo）", combo);

  /* 6. 情绪 */
  for (const m of ["happy", "sad", "surprised", "calm"]) {
    const r = await api("/api/express?mood=" + m);
    await sleep(120);
    const got = await fetch("/api/info.json", { cache: "no-store" }).then((x) => x.json());
    check(`情绪 ${m} 记进状态`, r.ok && got.mood === m, "mood=" + got.mood);
  }

  /* 7. 缩放：画面尺寸要跟着变 */
  await api("/api/scale?s=0.6"); await sleep(200);
  const small = await fetch("/api/info.json", { cache: "no-store" }).then((x) => x.json());
  await api("/api/scale?s=1.2"); await sleep(200);
  const big = await fetch("/api/info.json", { cache: "no-store" }).then((x) => x.json());
  check("缩放改变画面尺寸", big.frame_w > small.frame_w,
        `${small.frame_w}×${small.frame_h} → ${big.frame_w}×${big.frame_h}`);
  await api("/api/scale?s=1");

  /* 8. 睡眠 / 唤醒 */
  await api("/api/idle?s=600"); await sleep(400);
  const slept = await fetch("/api/info.json", { cache: "no-store" }).then((x) => x.json());
  check("放空够久会睡着", slept.sleeping === true, "sleeping=" + slept.sleeping);
  await api("/api/idle?s=0"); await api("/api/call"); await sleep(300);
  const woke = await fetch("/api/info.json", { cache: "no-store" }).then((x) => x.json());
  check("叫一声会醒", woke.sleeping === false, "sleeping=" + woke.sleeping);

  /* 9. 零件表 */
  const chr = info ? info.character : "xiaoxun", form = info ? info.form : "teen";
  const rr = await api(`/media/characters/${chr}/forms/${form}/rig.json`);
  const rig = rr.data;
  check("rig.json 能读", !!(rig && rig.parts), rig ? rig.parts.length + " 件" : "");
  if (rig) {
    const lids = rig.parts.filter((p) => (p.tags || []).includes("eyelid"));
    check("眼睑部件带行程", lids.length === 2 && lids.every((p) => p.eyelid_travel > 0),
          lids.map((p) => p.id + ":" + p.eyelid_travel).join(" "));
    const gz = rig.parts.filter((p) => (p.tags || []).includes("gaze"));
    check("眼球部件带 gaze 标签", gz.length === 2, gz.map((p) => p.id).join(" "));
    const layers = rig.parts.map((p) => p.layer);
    check("层号不重复", new Set(layers).size === layers.length, layers.length + " 层");
    const lidL = rig.parts.find((p) => p.id === "eye_l_lid");
    const browL = rig.parts.find((p) => p.id === "brow_l");
    const bangs = rig.parts.find((p) => p.id === "hair_front");
    check("眉毛和刘海压在眼皮上面",
          !!(lidL && browL && bangs) && browL.layer > lidL.layer && bangs.layer > browL.layer,
          lidL ? `眼皮${lidL.layer} < 眉${browL.layer} < 刘海${bangs.layer}` : "");
  }

  $("summary").innerHTML = `<b>${pass} 项通过 / ${fail} 项失败</b>` +
      (fail ? ` <span style="color:var(--bad)">有问题，看下面</span>`
            : ` <span style="color:var(--ok)">全部通过</span>`);
  log(`自动测试结束：通过 ${pass}，失败 ${fail}`, fail ? "bad" : "ok");
  btn.disabled = false; btn.textContent = "▶ 再跑一遍";
  suiteRunning = false;
  loadInfo();
}

/* ---------- 启动 ---------- */
(async function start() {
  bindSliders();
  bindVisemeSlider();
  bindStage();
  await loadInfo();
  await loadParts();
  await loadParams();
  await loadLipsync();
  await loadVisemes();
  await loadMixPanel();
  /* 33ms = 最高 30fps 的试探节奏。真正的节流靠 frameLoop 的在途保护：
     链路快就接近 30fps，链路慢就自动退到链路能给的速度，而不是照着
     固定间隔往队列里堆请求（那才是"一拥而上然后卡一下"的来源）。 */
  setInterval(() => { if (!suiteRunning) refresh(); }, 33);
  setInterval(loadInfo, 1000);
  setInterval(() => {
    const now = performance.now();
    $("p-fps").textContent = (framesShown / ((now - fpsMark) / 1000)).toFixed(1) + " fps";
    framesShown = 0; fpsMark = now;
  }, 2000);
})();
