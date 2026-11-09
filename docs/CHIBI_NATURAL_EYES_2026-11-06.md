# Chibi 自然眼形试验（未验收）

> 本文记录 5254 / v7 的上轮状态；当前脚本已继续调整，最新方案和验证见 [闭眼交接继续试验](CHIBI_EYE_TRANSITION_2026-11-06.md)。原版画稿和脚本可在提交 `d64a88c` 查看，`qa/` 是上轮快照。

针对 5247 反馈的「睁眼像瞪着、闭眼有问题」，以手口关节整合候选为基础，另建眼形试验，**没有覆盖正式桌宠、少女或原始画稿**。本轮只供比对，不是修复完成或美术验收。

## 修改和观察

- `experiments/live2d_chibi_eye_natural/` 有可编辑 SVG：较浅的眼白开口、活动上睑、单独闭眼线，以及临时笑眼/痛苦眼。虹膜上移 2 像素、上睑行程和网格调整；保留独立眼白遮罩和视线。
- v1 睁眼圆且全闭边缘模糊；v2 睁眼过困、闭眼呈 M；v3 睁眼相对放松、半眨连贯，但变形闭眼线锯齿模糊；v4/v5 用单独闭眼线改善终态，调整位置后近闭仍有灰影。v6/v7 补了临时笑眼和痛苦眼线，避免相应内建参数全开时整条眼线消失。v7 与 v6 图像一致，仅补充报告的来源标记。
- 实际 C 引擎截图见 `qa/`：开眼、半眨、0.85、0.92、全闭、单眼、转头半眨和笑眼。`controlled_blink.gif` 是每次手动改变闭合量、单步 C 渲染，共 41 帧的慢速闭合/打开，**不是自动眨眼实时节奏**。截图灰影不是 GIF 压缩造成的。完整密集采样由采集脚本生成。
- **仍未解决**：0.85–1 的两条睑线淡化会透底、灰影及眼角重叠；0.92 可见细瞳/亮边。眼线仍偏平，动态流畅度、与原角色相似度均需人工判断。笑眼、痛苦眼只是简化占位曲线，过渡和画风未验收。前轮手指连接、嘴角、肩腕衣侧等问题仍在。本版不应替换正式模型。

## 重现

依赖 Pillow、numpy、resvg-py 和已编译的 `build/zhuochong_preview`（如需先运行 `make build/zhuochong_preview`）。输出路径必须是 `build/` 下**尚不存在的目录**：

```sh
/home/user/.imgenv/bin/python tools/build_chibi_eye_natural.py build/my-natural-eye
/home/user/.imgenv/bin/python tools/capture_chibi_eye_natural.py build/my-natural-eye build/my-natural-eye-qa
/home/user/.imgenv/bin/python tools/preview_live2d_chibi.py --dynamic --dynamic-study build/my-natural-eye --preview-root build/my-natural-eye-preview 5254
```

端口已占用时选其他端口；预览绑定 0.0.0.0、没有认证，不要放私人数据。`eye_natural_report.json` 记录本轮画稿哈希和局限，`refinement_report.json` 仅代表上游构建状态。采集会暂停模型，复位参数后再显式固定 `blink=0`；避免 `/api/param?all=1` 释放手动眨眼影响抓帧。

## 技术检查（不等于美术验收）

- `make test-chibi-eye-natural`：安全路径、46 个唯一部件、左右单眼、半眨/闭眼、视线、笑眼/痛苦眼端点、转头组合和 47 文件 `.zproj` 往返真实 C 帧一致。另在临时副本加入合成表情，闭眼开度 0、0.08、0.5 时与同值手动参数及共同眨眼逐像素一致；**不代表所有真实表情与叠加情形都已验证**。
- 采样中半眨 3921、全闭 5714、左/右单眼 2828/2886、视线两端 2379 像素变化，只证明有响应。
- 真实 Chromium 验证新标题、手指/肘/视线控件、复位及手指动作；`make test-chibi-refinement test-chibi-binding-art` 通过，`make test` 快闸 2646 通过、0 失败（测试负例会打印错误日志）。未做 Windows 真机验证。
- 下一步应重画或重新设计近闭交接，逐帧确认线条不叠灰、不露虹膜；再细化笑/痛苦眼、单眼及真实动作/表情组合。若修改 C 的淡化规则，须保持旧 rig 默认行为并补独立回归。
