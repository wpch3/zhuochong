/* Isolated Chibi motion study controls. Sliders explicitly switch to neutral:
   animation channels otherwise overwrite manually assigned parameters. */
"use strict";
ZC.register({
  id: "dynamic_study",
  title: "动态试装控制",
  mount(host, root, options = {}) {
    const card = host.card("动态试装控制", "实验");
    card.body.appendChild(host.el("p", "hint", options.eyes === true
      ? "拖动滑块会切到静止检查并固定自动眨眼；眼开度 1 为睁眼、0 为闭眼。要恢复自动眨眼，先静止并复位，再点自动眨眼。"
      : "拖动滑块会切到静止检查；动作按钮可恢复循环。袖手摆幅受限，遮挡底稿仍需重画。"));
    const state = host.el("p", "hint", "就绪");
    const sliders = [];
    const pending = new Map();
    let running = false, reset = false;
    const pump = async () => {
      if (running) return;
      running = true;
      try {
        while (reset || pending.size) {
          if (reset) {
            reset = false;
            await host.api("/api/action", {id: "neutral"});
            await host.api("/api/param", {all: 1});
            if (options.eyes === true) await host.api("/api/blink", {v: 0});
          }
          if (pending.size) {
            await host.api("/api/action", {id: "neutral"});
            if (options.eyes === true) await host.api("/api/blink", {v: 0});
            // A reset may have arrived while the action request was in flight.
            // Do not drain newer slider values until that reset has completed.
            if (reset) continue;
            const batch = Array.from(pending.entries());
            pending.clear();
            for (const [id, value] of batch) {
              /* A later reset supersedes unsent values from this batch. */
              if (reset) break;
              await host.api("/api/param", {id, v: value});
            }
          }
        }
        state.textContent = "静止检查模式";
        host.refresh();
      } catch (e) {
        pending.clear(); reset = false;
        state.textContent = "控制失败：" + e.message;
      } finally { running = false; }
    };
    const resetButton = host.el("button", "btn small", "静止并复位");
    resetButton.addEventListener("click", () => {
      pending.clear(); reset = true;
      sliders.forEach(({input, output, initial}) => { input.value = String(initial); output.textContent = initial.toFixed(2); });
      state.textContent = "复位中…"; pump();
    });
    card.body.appendChild(resetButton);
    const specs = [
      ["ParamArmL", "左侧袖手", -1, 1, 0], ["ParamArmR", "右侧袖手", -1, 1, 0],
      ["ParamHeadTilt", "头部倾斜", -1, 1, 0], ["ParamHeadShiftX", "头部平移 X", -1, 1, 0],
      ["ParamHeadShiftY", "头部平移 Y", -1, 1, 0], ["ParamBreath", "呼吸", 0, 1, 0],
      ["ParamMotionDrive", "身体摆动 / 物理输入", -1, 1, 0],
    ];
    if (options.wrists === true) {
      specs.push(["ParamWristL", "左手腕（试验）", -1, 1, 0], ["ParamWristR", "右手腕（试验）", -1, 1, 0]);
    }
    if (options.elbows === true) {
      specs.push(["ParamElbowL", "左肘（试验）", -1, 1, 0], ["ParamElbowR", "右肘（试验）", -1, 1, 0]);
    }
    if (options.gaze === true) {
      specs.push(["ParamGazeX", "眼球横向（试验）", -1, 1, 0]);
    }
    if (options.eyes === true) {
      specs.push(["ParamEyeLOpen", "左眼开度（试验）", 0, 1, 1], ["ParamEyeROpen", "右眼开度（试验）", 0, 1, 1],
                 ["ParamEyeLSmile", "左笑眼（试验）", 0, 1, 0], ["ParamEyeRSmile", "右笑眼（试验）", 0, 1, 0]);
    }
    if (options.fingers === true) {
      for (const [side, label] of [["L", "左"], ["R", "右"]]) {
        for (const [name, finger] of [["Little", "小指"], ["Ring", "无名指"], ["Middle", "中指"], ["Index", "食指"], ["Thumb", "拇指"]]) {
          specs.push(["ParamFinger" + side + name, label + finger + "（试验）", -1, 1, 0]);
        }
      }
    }
    specs.forEach(([id, label, min, max, initial]) => {
      const row = host.el("label", "voice-item");
      row.appendChild(host.el("span", "id", label));
      const input = host.el("input"); input.type = "range";
      input.min = String(min); input.max = String(max); input.step = "0.01"; input.value = String(initial);
      input.setAttribute("aria-label", label);
      const output = host.el("span", "text", initial.toFixed(2));
      input.addEventListener("input", () => {
        const v = Number(input.value);
        output.textContent = v.toFixed(2);
        pending.set(id, v);
        state.textContent = "发送中…"; pump();
      });
      sliders.push({input, output, initial});
      row.appendChild(input); row.appendChild(output); card.body.appendChild(row);
    });
    card.body.appendChild(state);
    root.appendChild(card.box);
  },
});
