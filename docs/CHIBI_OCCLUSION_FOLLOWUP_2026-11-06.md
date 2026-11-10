# Chibi 遮挡及连续轮廓续查（2026-11-06，未完成）

本轮按用户续令做新隔离试验与目视；未修改正式模型，三处均未通过视觉验收，不应请求真机验收。`docs/memory/ERROR_INDEX.md` 与铁律 18 用于避免重复无依据的失败路线。官方来源与适用边界记录在 `REFERENCE_NOTES.md`，仅借鉴原则，不宣称 zrig 实现了 Cubism Glue 或官方模型。

## 指根：真实 C 隐藏层探针，根因尚未完全定位

新建 `tools/capture_chibi_hand_occlusion_probe.py`：每侧 neutral、交错、反交错三姿势，每姿势分别正常、隐藏手掌、隐藏五根中的一根，共 42 帧、深浅两底；每帧核对手指参数，另记录被隐藏部件。该 API 只改变是否绘制，不改变遮罩、参数或隐藏区域画稿，故不能把隐藏层画面当作真实剥离/补画完成的素材。

本人看了 `experiments/live2d_chibi_morph_study/qa/occlusion_followup/` 的正常、隐藏手掌和各指样本：隐藏手掌后根部只剩分开的指片，部分重叠轮廓和截面直接暴露；仅有前方手掌覆盖并不等于每根指头在动作时有完整相接的独立根部。单独隐藏不同指改变交错轮廓，但尚不能仅凭画面确定是哪些指片/描边造成全部融合。需要以匹配接缝的独立补画、可变遮挡关系及对应顶点/层序研究替代继续缩角或硬平移；本轮没有宣称该问题已修复。完整姿势/隐藏清单在同目录 `poses.json`。

```sh
make build/zhuochong_preview
/home/user/.imgenv/bin/python tools/build_chibi_extended.py build/occlusion-source
/home/user/.imgenv/bin/python tools/capture_chibi_hand_occlusion_probe.py build/occlusion-source build/occlusion-qa
```

## 眼：不断裂的睫线 + 痛眼分支试验，不通过

查阅官方教程后，新方案不再把移动睫线与不同闭线在末段做交叉透明，而是让移动睫线一直可见、以开度网格从睁到闭。痛眼形态试两个由同源睫线分出来的分支：一版完整重复一笔，另一版从移动睫线计算窄线并重用同一形变和位置；实验引擎仍以 pain 优先，未替换默认二进制。各对左右 pain/smile 0/.5/1 × blink 0/.5/1 与 .85/.925/1 采集各 54 帧，逐帧校验参数。

本人目视：完整复制的双线在 pain=1 很粗、像重叠的两条睫毛；窄线虽减少粗重，仍可见细碎、模糊或脱离的下线，痛眼两笔不像自然的同一眼形（`qa/unified_duplicate_pain.png`、`qa/unified_thin_pain.png`、`qa/unified_thin_transition.png`）。不能把“没有原来灰色交叉淡化”误报为视觉通过；两版均拒绝，不合并进正式模型。下一步需重设计可配准的单线/分叉原画拓扑及连续接缝，而不是继续调整复制笔画透明度或只改相隔数值。

```sh
make build/zhuochong_eye_morph_experiment test-chibi-topology-studies
/home/user/.imgenv/bin/python tools/build_chibi_unified_lid_study.py build/lid-thin --branch thin
/home/user/.imgenv/bin/python tools/build_chibi_unified_lid_study.py build/lid-duplicate --branch duplicate
/home/user/.imgenv/bin/python tools/capture_chibi_expression_mix.py build/lid-thin build/lid-thin-qa --preview-executable build/zhuochong_eye_morph_experiment --blink-values 0.85 0.925 1
```

## 袖：完整背层与前层渐进交接试验，不通过

分层候选上袖/前袖的裁片本身分别只覆盖约 0–99 / 95–177 行。新试验把原两片先按其原局部重叠合成，整片放于旧的背层，再把同一 UV/同一网格的前层从旧裁切附近在 16 行内逐渐显现。它改变了前后遮挡语义、可能产生透明边，只是定位尖角的实验，不是完整蒙皮或正式修复。

真实 C 采 33 身体叠关节和 48 混合固定帧/20 帧往返；比较 `qa/sleeve_backing_compare.png`、`qa/sleeve_backing_spur.png`，内侧青色三角仍然可见，不能通过；图中部分手裁出框，不能判手部完整。新中立浅深采样与原分层候选的 dark 裁图相差 435 个放大后的 RGB 像素，最大通道差 6；这是有限对照，不证明层序正确。不能简单认定渐变过短是唯一原因，下一步要分离衣身前片、袖轮廓和权重变形的实际遮挡，重新补画接缝并核验腕袖及前后关系。

```sh
/home/user/.imgenv/bin/python tools/build_chibi_sleeve_backing_study.py build/sleeve-backing
/home/user/.imgenv/bin/python tools/capture_chibi_body_joint_matrix.py build/sleeve-backing build/sleeve-backing-body
/home/user/.imgenv/bin/python tools/capture_chibi_visual_matrix.py build/sleeve-backing build/sleeve-backing-matrix
make test-chibi-topology-studies
```

定向技术测试覆盖构建路径、分层纹理合成、手部隐藏输出和不可覆盖、真实 C 参数响应、隔离引擎的痛眼优先及工程包往返；它们**不判断**视觉质量、所有连续姿势、Windows 真机或官方 Cubism 兼容性。完整核心和长期运行未因本轮研究重新运行；上一轮核心 2707/0。
