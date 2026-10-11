/* web/app.js —— 基础软件的交互逻辑
 *
 * 与引擎的约定：所有请求都走相对路径（/api/*、/media/*），
 * 由 C 预览服务（同一个端口）提供，因此不存在跨域，也不写死 localhost 端口。
 *
 * 命名：/api/poke 的 x,y 是**帧（窗口）坐标**，服务端会换算成画布坐标；
 * 界面按立绘显示尺寸等比换算后提交。
 */
"use strict";

const $ = (id) => document.getElementById(id);
const state = { info: null, speech: "", usage: { calls: 0, tokens: 0 }, group: "all", lastSpeechAt: 0 };

/* ------------------------------------------------------------ 立绘帧循环 */
const petImg = $("pet");
let frameTimer = null;
let interval = 1000 / 12;   // 12 fps：预览足够流畅，也不至于把沙箱压满
let failures = 0;

/* 远程预览是**按帧传 PNG** 的：原始尺寸一帧约 190KB，12fps 就要 2.2MB/s，
   公网上必然卡。所以这里按实测的单帧耗时自动降档（服务端 ?s= 按百分比缩小，
   浏览器再拉回原尺寸显示）。本地运行的桌面版不走网络，没有这个问题。 */
const QUALITY_STEPS = [50, 60, 75, 100];
let qualityMode = "auto";       // auto | 固定百分比
let qualityIdx = 1;             // 自动模式下的当前档位
let frameMs = 0;                // 单帧耗时的滑动平均
let fpsCount = 0, fpsAt = performance.now(), lastBytes = 0;

function currentQuality() {
  return qualityMode === "auto" ? QUALITY_STEPS[qualityIdx] : parseInt(qualityMode, 10);
}

function tuneQuality() {
  if (qualityMode !== "auto") return;
  if (frameMs > 220 && qualityIdx > 0) qualityIdx--;             // 太慢：降档
  else if (frameMs < 90 && qualityIdx < QUALITY_STEPS.length - 1) qualityIdx++;
}

function showFps(bytes) {
  fpsCount++;
  const now = performance.now();
  if (now - fpsAt >= 1000) {
    const el = $("fps");
    if (el) {
      el.textContent = fpsCount + " fps · " + Math.round(lastBytes / 1024) + " KB/帧 · "
                     + currentQuality() + "%";
    }
    fpsCount = 0;
    fpsAt = now;
  }
  if (bytes) lastBytes = bytes;
}

function scheduleFrame() {
  frameTimer = setTimeout(async () => {
    if (!document.hidden) {
      const t0 = performance.now();
      try {
        const url = "/api/frame.png?s=" + currentQuality() + "&t=" + Date.now();
        const resp = await fetch(url, { cache: "no-store" });
        const blob = await resp.blob();
        const next = URL.createObjectURL(blob);
        const old = petImg.dataset.blob;
        petImg.src = next;
        if (old) URL.revokeObjectURL(old);
        petImg.dataset.blob = next;
        const dt = performance.now() - t0;
        frameMs = frameMs ? frameMs * 0.7 + dt * 0.3 : dt;
        tuneQuality();
        showFps(blob.size);
        failures = 0;
        /* 上一帧还没到就不要再排队，否则请求会堆成雪球 */
        interval = Math.max(1000 / 12, frameMs * 0.2);
      } catch (e) {
        failures++;
        interval = Math.min(2000, 500 * failures);   // 出错退避，避免刷爆
        setConn(false);
      }
    }
    scheduleFrame();
  }, interval);
}

function setConn(ok) {
  const el = $("conn");
  el.textContent = ok ? "已连接引擎" : "引擎无响应，重试中…";
  el.style.color = ok ? "#4b93c4" : "#e0679a";
}

/* ------------------------------------------------------------ 状态轮询 */
async function pollInfo() {
  try {
    const r = await fetch("/api/info.json");
    const d = await r.json();
    state.info = d;
    setConn(true);
    $("chip-action").textContent = "动作 " + (d.action || "—");
    $("chip-mood").textContent = "情绪 " + (d.mood || "—");
    $("chip-aff").textContent = "好感 " + (d.affection ?? "—") + (d.tier_name ? ` · ${d.tier_name}` : "");
    $("chip-form").textContent = "形态 " + (d.form_name || d.form || "—");
    $("chip-scale").textContent = "缩放 " + (d.scale ?? "—");
    if (d.scale && Math.abs(Number($("scale").value) - d.scale) > 0.001) {
      $("scale").value = d.scale;
      $("scale-val").textContent = Number(d.scale).toFixed(2);
    }
    applyOptions(d);   // 形态/服装/动作列表由引擎提供，引擎新增内容界面自动出现
  } catch (e) {
    setConn(false);
  }
}

async function pollSpeech() {
  try {
    const r = await fetch("/api/speech.json");
    const d = await r.json();
    if (d.line && d.line !== state.speech) {
      state.speech = d.line;
      state.lastSpeechAt = Date.now();
      showBubble(d.line);
      state.usage.calls += 1;                 // 演示：一次台词算一次本地“调用”
      renderUsage();
    } else if (state.speech && Date.now() - state.lastSpeechAt > 4000) {
      state.speech = "";
      showBubble("");
    }
  } catch (e) { /* 静默：轮询失败不打扰用户 */ }
}

let bubbleTimer = null;
function showBubble(text) {
  const b = $("bubble");
  if (!text) { b.hidden = true; return; }
  $("bubble-text").textContent = "「" + text + "」";
  b.hidden = false;
  clearTimeout(bubbleTimer);
  bubbleTimer = setTimeout(() => { b.hidden = true; }, 4500);
}

/* ------------------------------------------------------------ 互动 */
async function poke(kind, ev) {
  const w = petImg.naturalWidth || 445, h = petImg.naturalHeight || 1292;
  let x = w * 0.5, y = h * 0.25, tool = 0;
  if (kind === "hammer") { tool = 1; y = h * 0.3; }
  else if (kind === "body") y = h * 0.45;
  else if (kind === "feet") y = h * 0.9;
  if (ev) {   // 立绘上的点击：按显示比例换算成帧坐标
    const rect = petImg.getBoundingClientRect();
    x = (ev.clientX - rect.left) / rect.width * w;
    y = (ev.clientY - rect.top) / rect.height * h;
  }
  await fetch(`/api/poke?x=${Math.round(x)}&y=${Math.round(y)}&tool=${tool}`);
  pollInfo();
}

petImg.addEventListener("click", (ev) => poke("auto", ev));

document.querySelectorAll("[data-poke]").forEach((btn) => {
  btn.addEventListener("click", () => poke(btn.dataset.poke));
});

$("btn-wake").addEventListener("click", async () => {
  await fetch("/api/action?id=idle");
  await fetch("/api/idle?s=0");
  pollInfo();
});

/* 动作与情绪按钮 */
/* 动作名（引擎给的 id → 中文显示）；引擎里新增动作会自动出现在界面里 */
const ACTION_NAMES = {
  idle: "待机", focus: "专注", happy: "开心", sad: "难过", surprised: "惊讶",
  think: "思考", talk: "说话", sleep: "睡觉", head_pat: "摸头", stroke: "抚摸",
  hammered: "被锤", clicked: "被点", dragged: "被拖", wake: "叫醒",
  breath: "呼吸", sway: "摇摆", wave: "挥手",
};
function actionName(id) { return ACTION_NAMES[id] || id; }
const MOODS = [["joy", "开心"], ["sad", "难过"], ["surprise", "惊讶"], ["think", "思考"], ["sleepy", "困倦"]];

function buildActionButtons(ids) {
  const a = $("actions");
  const list = ["idle", ...ids.filter((x) => x !== "idle")];
  a.innerHTML = "";
  list.forEach((id) => {
    const b = document.createElement("button");
    b.className = "btn small";
    b.textContent = actionName(id);
    b.addEventListener("click", async () => {
      await fetch("/api/action?id=" + id);
      markActive(a, b);
      pollInfo();
    });
    a.appendChild(b);
  });
}

function buildMoodButtons() {
  const m = $("moods");
  m.innerHTML = "";
  MOODS.forEach(([id, name]) => {
    const b = document.createElement("button");
    b.className = "btn small";
    b.textContent = name;
    b.addEventListener("click", async () => {
      await fetch("/api/express?mood=" + id);
      markActive(m, b);
      pollInfo();
    });
    m.appendChild(b);
  });
}

function markActive(parent, btn) {
  parent.querySelectorAll(".btn").forEach((x) => x.classList.remove("active"));
  btn.classList.add("active");
}

/* ------------------------------------------------------------ 形态 / 服装 / 缩放 */
/* 形态与服装：列表由引擎扫描角色包给出（新增形态/服装会自动出现在这里） */
/* 兜底名字表：引擎没给名字时才用（新增形态应在 character.json 里写 name，不改这里） */
const FORM_NAMES = { teen: "少女", loli: "萝莉", adult: "青年女性", chibi: "Q 版" };
let optionsLoaded = false;

function applyOptions(d) {
  const formSel = $("form");
  const outfits = d.outfits || [];
  const forms = d.forms || [];
  if (!optionsLoaded) {
    formSel.innerHTML = "";
    const formNames = d.form_names || [];
    forms.forEach((id, i) => {
      const o = document.createElement("option");
      /* 名字优先用角色包里写的（引擎导出 form_names），这样新增形态不用改前端 */
      const name = formNames[i] || FORM_NAMES[id] || id;
      o.value = id; o.textContent = name + "（" + id + "）";
      formSel.appendChild(o);
    });
    formSel.addEventListener("change", async () => {
      await fetch("/api/form?id=" + formSel.value);
      pollInfo();
    });

    const outfitSel = $("outfit");
    outfitSel.innerHTML = "";
    const outfitNames = d.outfit_names || [];
    outfits.forEach((id, i) => {
      const o = document.createElement("option");
      const name = outfitNames[i] || (id === "default" ? "常服" : id);
      o.value = id; o.textContent = name + "（" + id + "）";
      outfitSel.appendChild(o);
    });
    outfitSel.addEventListener("change", async () => {
      await fetch("/api/outfit?id=" + outfitSel.value);
      pollInfo();
    });

    if (d.actions) buildActionButtons(d.actions);
    optionsLoaded = true;
  }
  if (d.form) formSel.value = d.form;
  if (d.outfit) $("outfit").value = d.outfit;
  if (d.actions) {
    const a = $("actions");
    if (a.children.length === 0) buildActionButtons(d.actions);
  }
}

$("scale").addEventListener("input", (e) => { $("scale-val").textContent = Number(e.target.value).toFixed(2); });
$("scale").addEventListener("change", async (e) => {
  await fetch("/api/scale?s=" + e.target.value);
  pollInfo();
});

/* ------------------------------------------------------------ 语音清单 */
const GROUP_NAMES = {
  all: "全部", greet: "问候", pat: "摸头 / 抚摸", click: "点击 / 拖动", mood: "情绪",
  call: "语音通话", aff: "好感", sleep: "睡醒", other: "其他",
};

function groupOf(id) {
  if (id.startsWith("pat_") || id.startsWith("stroke_") || id.startsWith("feet_")) return "pat";
  if (id.startsWith("click_") || id.startsWith("drag_") || id.startsWith("drop_")) return "click";
  if (id.startsWith("mood_")) return "mood";
  if (id.startsWith("call_")) return "call";
  if (id.startsWith("tier_")) return "aff";
  if (id.startsWith("wake_") || id.startsWith("hammer_")) return "sleep";
  return "other";
}

let voiceData = [];

async function loadVoices() {
  try {
    const r = await fetch("/voice_manifest.json");
    const d = await r.json();
    voiceData = d.lines || [];
    const engine = d.engine || "未知";
    $("voice-engine").textContent = engine;
    $("voice-note").textContent = d.note || "";
  } catch (e) {
    $("voice-engine").textContent = "清单缺失";
    return;
  }
  const groups = new Set(voiceData.map((v) => groupOf(v.id)));
  const sel = $("voice-group");
  sel.innerHTML = "";
  const all = document.createElement("option");
  all.value = "all"; all.textContent = GROUP_NAMES.all;
  sel.appendChild(all);
  [...groups].sort().forEach((g) => {
    const o = document.createElement("option");
    o.value = g; o.textContent = GROUP_NAMES[g] || g;
    sel.appendChild(o);
  });
  sel.addEventListener("change", () => { state.group = sel.value; renderVoices(); });
  renderVoices();
}

function renderVoices() {
  const box = $("voice-list");
  box.innerHTML = "";
  voiceData
    .filter((v) => state.group === "all" || groupOf(v.id) === state.group)
    .forEach((v) => {
      const row = document.createElement("div");
      row.className = "voice-item";
      row.innerHTML = `<span class="id">${v.id}</span><span class="text"></span>`;
      row.querySelector(".text").textContent = v.text;
      row.addEventListener("click", () => playVoice(v));
      box.appendChild(row);
    });
}

async function playVoice(v) {
  const player = $("player");
  player.src = "/media/" + v.file;
  try { await player.play(); } catch (e) { /* 浏览器自动播放限制，由用户点击触发即可 */ }
  await fetch("/api/action?id=talk");                 // 说话动作
  state.usage.calls += 1;
  state.usage.tokens += Math.ceil((v.text || "").length / 2);   // 演示用估算
  renderUsage();
  showBubble(v.text);
}

function renderUsage() {
  const el = $("usage");
  el.textContent = `本次会话：${state.usage.calls} 次调用 · ${state.usage.tokens} token（演示估算）`;
  const pct = Math.min(100, (state.usage.tokens / 2000) * 100);
  $("meter-fill").style.width = pct.toFixed(1) + "%";
}

/* ------------------------------------------------------------ 设置区 */
$("btn-passthrough").addEventListener("click", () => {
  alert("整窗穿透（Ctrl+Alt+T）与托盘菜单只在 Windows 真机生效；沙箱预览用于演示引擎与交互。");
});
$("btn-log").addEventListener("click", async () => {
  const pre = $("log");
  if (!pre.hidden) { pre.hidden = true; return; }
  try {
    const r = await fetch("/media/logs/preview.log");
    const t = await r.text();
    pre.textContent = t.slice(-3000);
  } catch (e) {
    pre.textContent = "日志读取失败（logs/ 可能尚未生成）";
  }
  pre.hidden = false;
});

/* ------------------------------------------------------------ 启动 */
buildMoodButtons();
loadVoices();
renderUsage();
pollInfo();
pollSpeech();
scheduleFrame();
{
  const q = $("quality");
  if (q) q.addEventListener("change", () => { qualityMode = q.value; frameMs = 0; });
}
setInterval(pollInfo, 600);    // 状态：0.6 秒
setInterval(pollSpeech, 400);  // 台词：0.4 秒
document.addEventListener("visibilitychange", () => setConn(!document.hidden));
