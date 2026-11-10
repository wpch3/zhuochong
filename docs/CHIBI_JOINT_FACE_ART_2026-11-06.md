# Chibi 肩、肘、腕及眼口隐藏画稿：隔离试验记录

## 目标与范围

接上轮 `CHIBI_WRIST_ART_WORKFLOW_2026-11-06.md`。只派生独立 Chibi 候选，不覆盖桌宠、少女、正式形态和旧试装。目标是逐项补全肩肘手指与眼口的可编辑隐藏画稿；**本轮只完成局部画稿和实验绑定，距离完整可用模型还有明显差距**。本项目使用自研 C/zrig，不是官方 Cubism。

参考：Live2D [素材拆分教程](https://docs.live2d.com/4.2/en/cubism-editor-tutorials/psd/) 建议上臂、前臂、手分开，眼白补足眼球后方、眼球和睫毛分开，口腔及上下唇分开；[关节形状参考](https://en.esotericsoftware.com/blog/How-to-cut-your-assets-for-animation) 提醒圆形重叠和隐藏区需手绘。参考不意味着本候选已符合官方制作标准。

## 本轮实际制作和目视结果

1. **手腕**：`wrist_cleanup.svg` 是局部肤色修补；只作用于切线邻近、左右指定范围内、已有手的像素，alpha 不变。左/右分别修改 45/53 像素，因此不再承诺与旧手中立逐像素相同。`wrist_contours.svg` 新增独立腕部和侧面描边，按原袖不透明区域裁剪放在袖后。对比上一轮袖子隐藏图，切线上的散落灰点明显减少；但裁切后的轮廓仍有断开和硬边（`qa/joint-contours-l.png`、`...-r.png`）。小幅动作的 C 帧看起来比初版平顺，不等于大幅自然、也不等于验收。
2. **肘部**：原袖按 `y=137` 划成上臂与前臂；新绘 `elbow_underpaint.svg` 圆润布料在上袖后方。父子层级为肩 → 肘 → 腕，肘 ±4°，`elbow_test` 让肘腕小幅联动。第一版无重叠，在 0.55 的中立帧和动作帧有横穿两袖的亮色线（`qa/elbow_without_overlap_rejected.png`），故在前臂加入仅限完全不透明像素的 4px 上沿重叠。源分辨率重新合成仍与旧袖分片逐像素一致，真实 C 目视 `qa/neutral_light.png`、`elbows_min_light.png`、`elbows_max_dark.png`、`combined_dark.png` 和循环帧，横线明显减轻，但该机械直切和小旋转仍不是完整自然肘弯。两侧轮廓、颜色与大动作须继续手工精修。
3. **肩部**：`shoulder_underpaint.svg` 绘制左右袖肩向衣身内延伸的布料，位于身体与袖子之下，源分辨率裁切在二者完全不透明区内。新候选只测试了原肩 ±2°及部分组合；仍有原衣身侧片的不自然边缘，没有完成大幅抬臂所需的整片肩/躯干隐藏原画。
4. **眼部**：直接从平面眼图椭圆切出虹膜尝试留下固定旧黑边，视线移动时产生白/黑重影（`qa/eye_cut_rejected.png`），已拒绝。另画 `eye_apertures.svg` 和 `iris_redraw.svg`，建立眼白、眼球、固定遮罩及共享横向参数，作为独立眼试验；C 确实能移动，但眼睛变得平、顶部仍有旧蓝黑残留，睫毛和头发仍在同一旧图，静止面貌也改变（`qa/center_light.png`、`left_light.png`、`right_light.png`）。不能晋升。
5. **眨眼问题**：眼候选保留旧开闭眼图透明度切换，而没有绑定完整可变形眼睑。C 在手动闭合 0.5 时与同视线睁眼帧**完全相同**；0.92 时出现两套睫毛/眉线的灰色重影（`half_blink_light.png`、`late_blink_light.png`）。全闭帧存在不证明过渡自然；下一步必须单独绘制眼睑并绑定闭合关键形态/遮罩。
6. **手指、口腔草稿**：`finger_draft.svg` 包含手掌和五根带隐藏根部的独立路径，右手目前只是镜像引用；`mouth_draft.svg` 包含口腔、舌头和上下唇线。这两张只作为可编辑构造草图，目视放大后手指重叠条纹明显、拇指连接突兀、比例不可靠，嘴的阴影较平且上下唇没有皮肤遮盖；均**未放入候选 rig、未绑定或验收**。现预览中的手仍是整体手，嘴仍是旧两张图片的淡入淡出。不能说手指和口型已完成。

## 对照与复现

依赖 Python Pillow、numpy、`resvg-py==0.5.0`、C 构建工具，测试另需 Node。所有输出路径必须不存在并在 `build/` 下；报告中的 SHA 记录具体 SVG 来源。构建器不会改写已存在目录或写到仓库其他地方。

```sh
make build/zhuochong_preview
python tools/build_chibi_joint_art.py build/joint-candidate
python tools/capture_chibi_joint_art.py build/joint-candidate build/joint-qa
python tools/preview_live2d_chibi.py --dynamic --dynamic-study build/joint-candidate --preview-root build/joint-preview 5227
python tools/build_chibi_eye_art.py build/eye-candidate
python tools/capture_chibi_eye_art.py build/eye-candidate build/eye-qa
python tools/preview_live2d_chibi.py --dynamic --dynamic-study build/eye-candidate --preview-root build/eye-preview 5228
make test-chibi-joint-art
```

预览无认证，默认绑定 `0.0.0.0`；只在隔离环境使用，不放真实私密数据。`wrist_report.json` 沿用上轮以启用腕控，已标记 `superseded_by_joint_report`，本轮精修以 `joint_report.json` 为准。`.zproj` v1 只含 rig 和 PNG，SVG 源在仓库另存，不能从项目包单独恢复。

关节候选与上轮腕候选各用独立 C 进程，先检查两份基线在四比例 × 中立/双袖极值的 12 帧完全相等，再比较候选；变化像素为：

| 比例 | 中立 | 双袖外摆 | 双袖内摆 |
|---|---:|---:|---:|
| 0.35 | 180 | 220 | 219 |
| 0.55 | 276 | 363 | 355 |
| 0.8 | 398 | 489 | 487 |
| 1.0 | 98 | 381 | 392 |

中立 1× 的 98 个变化像素与 45+53 个手部修色像素相符，但统计只是 RGBA 差异，不是完整效果保证。更小比例还受逐层采样影响。`qa/metrics.json` 记录单肘、双肘、中间值、身体袖腕组合及 9 个动作通道样本；仅这些状态被测，数字不替代目视。

眼候选相对关节基线，四比例中立差异依次为 696、1621、3154、4613 像素，说明确实改变了静止外观；两份基线在对应中立帧一致。`qa/eye_metrics.json` 明记半闭无变化；切勿把“眼球可以移动”误写成“眼睛完整”。QA 的 C 帧先合成背景再放大，浏览器截图中文方框是测试环境缺字，不代表每个用户的浏览器都缺字。

本轮 `test-chibi-joint-art` 验证安全路径、源不变、手部 alpha 和修改范围、袖分片重组、肩底遮挡区域、真实 C 多姿态及循环、眼球遮罩/运动、22 文件关节包和 28 文件眼包的验证解包以及 C 帧逐像素往返。真实 Chromium 检查肘腕与视线滑块、复位、动作按钮；原选项默认不变。关节/手腕/衣身/旧动态/底稿/隐藏图/绑定器/项目包/预览动作回归通过。`make -s test` 2646 通过、0 失败，示例模块未构建因此热加载冒烟跳过；旧正式 Chibi 加载 3 条警告，Windows 真机本轮未测。

## 接下来必须继续

- 为真实活动范围画完整的肩侧躯干与上臂，并手绘肘弯外缘和布褶关键形态；测试大角度、组合姿态、深浅底和多比例。
- 清理腕部黑线断点，重画单手五指及遮挡根部、关节轴和分层，不能把镜像/未绑定草稿当成完成。
- 分离睫毛、上下眼睑、眼白、虹膜与高光，重绘使风格贴近原图，并以网格/关键形态驱动闭合与遮罩，消除眨眼重影。
- 口腔上下唇、皮肤遮盖、舌和牙齿须真正分层，设计闭合与张口中间关键形态，并验证说话动作。
