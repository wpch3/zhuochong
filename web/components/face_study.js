/* 仅用于实验预览：面部差分验证，不伪装成完整模型。 */
"use strict";
ZC.register({
  id: "face_study",
  title: "面部试作",
  mount(host, root, opts = {}) {
    const card = host.card(opts.title || "面部试作", "实验");
    card.body.appendChild(host.el("p", "hint", opts.description || "这是隔离候选：身体与头发仍是整图，只有眼睛和嘴分层；整体摇摆不是独立骨骼动画。"));
    const status = host.el("p", "hint", "自动眨眼已启用。");
    const row = host.el("div", "grid");
    const buttons = [
      ["睁眼", "/api/blink?v=0"],
      ["闭眼", "/api/blink?v=1"],
      ["自动眨眼", "/api/blink?v=auto"],
      ["张嘴", "/api/param?id=ParamMouthOpenY&v=1"],
      ["合嘴", "/api/param?id=ParamMouthOpenY&v=0"],
    ];
    buttons.forEach(([label, url]) => {
      const button = host.el("button", "btn small", label);
      button.addEventListener("click", async () => {
        try {
          await host.api(url);
          status.textContent = "已设置：" + label;
          host.refresh();
        } catch (error) {
          status.textContent = "设置失败：" + error.message;
        }
      });
      row.appendChild(button);
    });
    card.body.appendChild(row);
    card.body.appendChild(status);
    root.appendChild(card.box);
  },
});
