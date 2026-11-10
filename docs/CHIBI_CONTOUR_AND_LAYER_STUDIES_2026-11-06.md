# Chibi 指根、眼线、分层袖与瞳孔同步研究（2026-11-06）

**未通过视觉验收，不是正式模型；不要要求真机验收。** 本文续 `CHIBI_WEIGHTED_STUDIES_2026-11-06.md`，所有候选均为 build 内隔离研究。自动断言、有限矩阵、逐帧参数校验、包往返和哈希等都不能代替视觉检查或覆盖连续空间；现有 zrig 不等同官方 Cubism。

## 独立有效闭合 keyform

默认引擎新增部件标签 `eye_keyform_effective_blink`，仅显式标记的部件上、以内建 `ParamEyeLOpen` 或 `ParamEyeROpen` 驱动的网格 keyform 改为读取对应帧最终闭合量的补数。其他参数 keyform、没有该标签的部件、公共参数读回和老模型保持原口径。最终闭合量与绘制使用相同的左右眼 blink：由手动/自动眨眼与单眼通路合成后，再取对应 smile、pain 的最大值；不改变 smile/pain 的画稿或透明度算法。每次 tick 先计算绘制闭合量再计算 keyform，不使用上一帧；物理之后额外改变参数时，使用的是绘制本身当帧计算的闭合快照。首次计算需要 tick。两内建开度 keyform 必须匹配部件 `eye_side`，且不支持正 `lag`；违反时拒载。其他参数的 keyform 不受此标签影响。旧引擎会忽略未知标签，不能保证新候选在旧引擎里呈现相同效果。

`tests/test_core.c` 覆盖显式眨眼、左右表情隔离、单眼、未标记旧行为、内建参数读回、左右不匹配及 lag 拒载；`make test` 本轮 2707/0。试验候选 `tools/build_chibi_pupil_hold_study.py` 对瞳孔细节与运动眼睑使用此标签，瞳孔位移最大 12 画布像素、开度关键帧 0/.2/.3/.5/1；在采样的普通 0.5、0.65 半眨有可见瞳孔，0.7 左右仍基本消失，不代表连续范围成功。左右 smile/pain/wink 的 0.5、0.65 等闭合值，以及一次双眼混合闭合测试在真实 C 逐像素等价；正常张眼帧与原扩展候选一致，打包还原一致。强痛眼、近闭眼线仍存在灰色重影：见 `experiments/live2d_chibi_morph_study/qa/pupil_effective_pain085.png`；`pupil_effective_blink065.png` 和 `pupil_effective_gaze_neg_half.png` 是代表帧。有限 gaze X / 自动眨眼采样不代表全部轨迹或 gaze Y 已测。

```sh
make build/zhuochong_preview test-chibi-pupil-hold-study
/home/user/.imgenv/bin/python tools/build_chibi_pupil_hold_study.py build/pupil-study
/home/user/.imgenv/bin/python tools/capture_chibi_art_review.py build/pupil-study build/pupil-art-qa --auto
/home/user/.imgenv/bin/python tools/capture_chibi_expression_mix.py build/pupil-study build/pupil-mix
/home/user/.imgenv/bin/python tools/capture_chibi_expression_mix.py build/pupil-study build/pupil-close-mix --blink-values 0.85 0.925 1
```

两组表情矩阵各 54 帧：单侧 smile/pain 各 0/.5/1 × blink 分别为 0/.5/1 或 .85/.925/1。全眼双侧同时表情、连续变化、所有 gaze 和头部动作仍需扩测。

## 闭眼线：两笔连续轮廓、痛眼优先仍失败

`tools/build_chibi_morph_eye_study.py` 以同源闭线和两组网格试图连续改变笑/痛形状；实验补丁 `experiments/live2d_chibi_morph_study/engine_experimental.patch` 只用于另编二进制，使痛眼抑制笑眼并保留闭线。54 表情帧与 54 近闭帧已逐参数采样，但 blink .925、pain .5 有灰影（`qa/morph_transition_ghost.png`），全痛眼与头发靠近，不能采用。`make test-chibi-contour-studies` 验证优先级与包往返，不是视觉结论。

另试把变形量按闭合 0.85–1 的 smoothstep 推迟到交接末端：54 近闭组合中仍见模糊多线，尤其 `qa/handoff_ghost.png`；被拒绝，不进入默认引擎。复现补丁为 `rejected/handoff/engine.patch`，建立独立 C 副本后 `patch -p1` 再按上文历史编译方式编译；不得覆盖正式二进制。两补丁和旧 aligned-eye 补丁均已以当前源代码为基准分别生成，彼此不能叠加应用。

```sh
make build/zhuochong_eye_morph_experiment test-chibi-contour-studies
/home/user/.imgenv/bin/python tools/build_chibi_morph_eye_study.py build/morph-study
/home/user/.imgenv/bin/python tools/capture_chibi_expression_mix.py build/morph-study build/morph-close-qa --preview-executable build/zhuochong_eye_morph_experiment --blink-values 0.85 0.925 1
```

## 手与遮挡

原扩展候选真实 C 渲染 1,024 个双手五指二值端点，Gray code 相邻只改一参，每帧校验十参。按自身 32 种姿势分组，另一手变化的 32 个裁图哈希均不变；仅证明该次采样设置和裁图内的双手独立，不能证明画面正确、手指间遮挡正确或连续姿势正确。完整报告 `qa/two_hand_endpoint_report.json` 是当时生成的，**不包含 rig 或二进制哈希**；采集脚本现已增加两者，不能将现在的哈希冒充旧报告元数据。

固定根分指网格、原掌指合纹理高斯场、手绘连续指蹼 v2 分别采了每手 32 端点和 48 混合帧；指线悬浮/指缝融合、梳齿轮廓、三角拇指和交错姿势融合仍然存在。单层手绘掌指没有独立前后深度，无法实现真实指间遮挡；这些方案均不通过。代表 `qa/anchored_L_01010.png`、`qa/whole_hand_L_01010.png`、`qa/webbed_L_01010.png` 和左右原手端点表。下一步需要重新拆分并补画被遮挡的指根/手掌，在各姿势设计明确层序或遮罩；不能只缩小角度或挤压纹理。

```sh
/home/user/.imgenv/bin/python tools/build_chibi_extended.py build/hand-base
/home/user/.imgenv/bin/python tools/capture_chibi_two_hand_endpoints.py build/hand-base build/two-hand-qa
/home/user/.imgenv/bin/python tools/build_chibi_webbed_hand_study.py build/webbed-study
/home/user/.imgenv/bin/python tools/capture_chibi_finger_endpoints.py build/webbed-study build/webbed-endpoints
/home/user/.imgenv/bin/python tools/capture_chibi_visual_matrix.py build/webbed-study build/webbed-matrix
```

## 两层连续袖与父子组

`tools/build_chibi_layered_sleeve_study.py` 将上下袖保留原来 12/21 两层，分别裁为同边界、使用相同 8×16 权重网格；镜像 body→shoulder→elbow 的固定 rig 参数绑定到形变器。根组必须静态，构建器拒绝不受支持的 look、直接袖动作/参数和部分物理等，不能推断这对任意 rig 成立。`make test-chibi-layered-sleeve-study` 使用真实 C 顶点探针，在左右、多尺度、权重 0/.5/1 的采样中原组与镜像链最大误差 0，非平凡肘差 36.070，另检拒绝路径及包往返。只证明这些数值样例而非通用 skinning。

肩 ±12°、肘 ±20°、腕 ±15° 是压力测试，不是批准动作范围。身体矩阵已扩为中立 + 每侧肩肘腕二值 8 种 × body ±1 = 33 帧；`qa/layered_L_body_matrix.png` / `qa/layered_R_body_matrix.png` 缩图部分手在裁框外，不能据此判断完整手部。尽管父子和层序采样比旧单层更合理，袖侧尖角、手部模糊等仍可见，不可宣称修复。双侧同时运动、连续扫动与腕袖遮挡仍待重新设计及目视检查。

```sh
make test-chibi-layered-sleeve-study test-chibi-weighted-sleeve-study
/home/user/.imgenv/bin/python tools/build_chibi_layered_sleeve_study.py build/layered-study
/home/user/.imgenv/bin/python tools/capture_chibi_visual_matrix.py build/layered-study build/layered-matrix
/home/user/.imgenv/bin/python tools/capture_chibi_body_joint_matrix.py build/layered-study build/layered-body
```

## 工具链与剩余工作

编辑器模拟 DOM、真实 Chromium 与导出 rig 的 C 参数驱动测试本轮通过；`.zproj` rig+PNG 工程包验证和还原通过。它不是完整作者工程，编辑器尚缺动态 C 主画布、权重绘制和通用多骨蒙皮等；资料库、拆件、绑定、参数、预览、打包、测试与部署任务流的缺口仍按 `EXTENDED_AUTHORING_WORKFLOW_2026-11-06.md` 跟踪。Windows 实机、用户验收和长期运行未完成。优先修手指分层/遮挡、单轮廓闭眼交接、袖侧与腕口；修后重做两手连续混合、双侧肩肘腕、表情交叠及不同背景/尺度，并在自己确认视觉无问题后才安排真机验收。
