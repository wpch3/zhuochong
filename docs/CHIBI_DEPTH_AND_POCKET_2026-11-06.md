# Chibi 指部层序、单网格眼线与口袋遮挡（2026-11-06，进行中）

**三处均未完成视觉验收；不接入正式模型、不请求用户真机验收。** 本文续 `CHIBI_OCCLUSION_FOLLOWUP_2026-11-06.md`，所有结果只适用于所述固定候选和采样；C 程序与素材试验、技术测试、真实外观和 Windows 实机是独立门禁。原图证据均在 `experiments/live2d_chibi_morph_study/qa/occlusion_probe_2/`。

## 袖边“尖角”至少有一个是口袋被部分遮挡

真实 C 在 `ParamArmL=-1, ParamElbowL=-1, ParamWristL=-1, ParamMotionDrive=-1, ParamBreath=1` 下切换部件可见性：正常图有青色小三角；隐藏 body 时它不见，只显示 body 时可见完整的青色口袋；隐藏 arm/forearm 的对照和 `only_forearm` 协助区分袖与衣身。**该具体样本**的尖角是口袋被袖子大部分挡住后的露出，不可从此推断所有角度的尖角都是口袋或所有袖形正确。新工具 `capture_chibi_sleeve_occlusion_probe.py` 左右各固定一个姿势、正常/单件隐藏/单件隔离共 14 帧，核对参数，保存背景和清单；可见性开关不改变蒙版或几何，不等于美术分层已完成。

试验一：用粗四边形提取原图口袋并各向内移 8px，留下明显碎点与修补边，拒绝；见 `pocket_shift_bad_neutral.png`。试验二：用色块连通域和局部拓展提取口袋、修补下层、移至更靠内的位置；真实 C 的该姿势中剩余部分较像可辨认的口袋边，而非小三角，另一侧及中立见 `pocket_split_*`；33 帧 body×joint、48 固定混合姿势与 20 帧往返已采集，目视左右 16 例缩图。此方案改变静止原设计和底层像素，依赖 OpenCV 自动提取与 inpaint，局部画稿、两侧对称、所有遮挡和袖纹理仍须严格审视；**仅是有希望的隔离试验，不是最终修复**。它不能解决手指模糊或其余袖侧/腕口问题。中立放大裁图与原分层候选有 16,773 个 RGB 像素不同（裁剪 `(290,450,730,720)` 放大 3 倍后的像素，不是原始画布像素），绝非中立等价。

```sh
make test-chibi-pocket-split-study test-chibi-occlusion-diagnostics
/home/user/.imgenv/bin/python tools/build_chibi_layered_sleeve_study.py build/layered-source
/home/user/.imgenv/bin/python tools/capture_chibi_sleeve_occlusion_probe.py build/layered-source build/sleeve-parts
# 须安装 OpenCV Python：这两个构建器只产生独立 build 目录
/home/user/.imgenv/bin/python tools/build_chibi_pocket_shift_study.py build/pocket-bad
/home/user/.imgenv/bin/python tools/build_chibi_pocket_split_study.py build/pocket-trial
/home/user/.imgenv/bin/python tools/capture_chibi_body_joint_matrix.py build/pocket-trial build/pocket-body
/home/user/.imgenv/bin/python tools/capture_chibi_visual_matrix.py build/pocket-trial build/pocket-matrix
```

第二方案重建 body.png 的 SHA-256 与首次提取逐字节一致（`eabcf061b09aa5c97997da3c30398835532c1b2d4fd3445ec34551f08fa1f1fa`，特定 OpenCV/依赖环境）；测试检查修改区域、原 alpha、C 参数响应和工程包往返，不验证提取美术正确。后续需要独立口袋源与真实未遮挡衣身、合理的前后层序，并检查近距离动画/全身尺度，不得把自动 inpaint 当作已批准源画。

## 指：动态层序诊断导致跳变和缺指，不采用

实验引擎仅用于该试验，按五根手指参数对原分件重新排序，正常中立排序不变，但参数相邻交叉时层序可瞬时跳变。真实 C 左右单手 64 二值端点与 48 混合固定姿势/20 帧扫动已采，逐帧核参；`L_10101_light.png` 显示部分手指被压掉、轮廓不自然，不能接受。固定左手无名指从 0.0660 到 0.0673 的样本跨越实验排序阈值，左手 85×85 画布裁框的 RGBA 不同像素数：原 C **15**，实验 C **85**；证明该样本排序切换增加了变化，不能将差异全部当作纯视觉跳变幅度的普遍度量。两张放大图 `zhuochong_finger_depth_experiment0.066.png` / `...0.0673.png` 可见指线发生骤变。**排序不能替代根部补画、独立前后关系和接缝处理**；实验代码按部件名称硬编码，影响所有同名部件，不可当通用 API，不进入默认引擎。后续重新采集的 64 端点清单 `qa/occlusion_probe_2/finger_depth_poses.json` 含采集前 rig 和实验二进制哈希，并与首次三张代表帧逐像素一致；采集前哈希不证明捕获期间文件未被外部修改。

```sh
make build/zhuochong_finger_depth_experiment test-chibi-occlusion-diagnostics
/home/user/.imgenv/bin/python tools/build_chibi_extended.py build/depth-source
/home/user/.imgenv/bin/python tools/capture_chibi_finger_endpoints.py build/depth-source build/depth-endpoints --preview-executable build/zhuochong_finger_depth_experiment
/home/user/.imgenv/bin/python tools/capture_chibi_visual_matrix.py build/depth-source build/depth-matrix --preview-executable build/zhuochong_finger_depth_experiment
```

补丁归档在 `rejected/finger_depth/engine.patch`，Makefile 只把它应用于 build 内 C 副本，默认 `src/core/zrig.c` 未改。

## 眼：痛眼分叉压入一张网格仍失败

`build_chibi_singlemesh_lid_study.py` 把临时下分支放进原移动睫线贴图，在同一 16×16 网格内令 pain=0 压回、pain=1 分开；闭眼和笑眼分别再加同分辨率网格，使用独立形变实验二进制的痛眼优先。左右、smile/pain 各 0/.5/1，blink 0/.5/1 和 .85/.925/1 共 108 帧。本人看真实 C 图后否决：睁眼时下方仍残留灰/黑细线，全痛时分叉断续、形态发散，且存在网格挤压导致模糊的风险（`singlemesh_open.png`、`singlemesh_pain.png`）。它验证了一张纹理并不自然消除相交，不可拿“单网格”称已修；应改为有独立艺术结构的闭合线/痛眼形态及可控变形，而不是继续堆算法抽线。

```sh
make build/zhuochong_eye_morph_experiment test-chibi-occlusion-diagnostics
/home/user/.imgenv/bin/python tools/build_chibi_singlemesh_lid_study.py build/singlemesh-eye
/home/user/.imgenv/bin/python tools/capture_chibi_expression_mix.py build/singlemesh-eye build/singlemesh-eye-close --preview-executable build/zhuochong_eye_morph_experiment --blink-values 0.85 0.925 1
```

## 记录与边界

本轮 `make test-chibi-occlusion-diagnostics test-chibi-pocket-split-study` 及既有 topology/contour/layered/pupil 定向测试通过。未重跑完整核心、Windows 真机和长期运行；前轮核心 2707/0 不能冒称本轮全链通过。当前目视仍能看到交错手指问题、眼线异常、手部模糊及未穷尽的袖形问题。下一步优先：可拼合的多层指根补画与局部遮挡；重新设计痛眼分叉而非重复 alpha/抽线；取得独立口袋与衣身画稿并评估前后层序；然后扩大双侧/连续/视线/尺度组合验证。
