# 验证素材（非正式模型）

- `editor_underpaint.png` / `editor_rotated.png`：真实 Chromium 测试的工作台截图。
- `example_patch_not_approved.png`：浏览器画笔导出的透明补画层，可复现候选，但**不批准用于正式模型**。
- `example_report.json`：生成候选时的源和补画哈希、变动像素范围；`not evaluated` 表示生成器不作审美判断。后续人工目视拒绝该示例。
- `c_baseline_outward_light.png`、`c_candidate_outward_light.png`、`c_candidate_outward_dark.png`：实际 C 引擎帧合成浅/深底后裁切放大，不是浏览器仿射预览。目视可见小幅动作仍有局部不自然接缝；该补画不满足正式验收。

本次固定步进对照的中立/外摆/内摆分别有 200/532/48 个 C 帧像素不同；原始中立 RGBA 三层合成相同。像素计数只用于定位和复核，不是审美结论或品质评分。

`sampling_example_metrics.json` / `sampling_red_stress_metrics.json` 是多边距、四缩放的真实 C 矩阵。`c_margin6_outward_light.png`、`c_margin6_outward_dark.png` 是边距 6 的 C 袖手极值放大帧；`editor_margin6.png` 是更新后工作台。目视后仍缺真实隐藏画稿，未通过美术验收。
