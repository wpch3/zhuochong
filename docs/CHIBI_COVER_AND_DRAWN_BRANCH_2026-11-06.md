# 口袋补片与手绘痛眼支线：隔离失败记录（2026-11-06）

**结论：均未视觉通过，不得替换生产资产。** 交错指根融合、近闭痛眼灰影、袖侧大角问题仍未解决；本轮没有完成 Windows 真机、长期运行或全组合验收，也不请用户真机验收。

## 口袋：保留原图的肩角补片仍错误

`tools/build_chibi_pocket_cover_study.py` 以已分层袖候选为基础，保留原 body 图像，在两侧口袋区域新增小块 inpaint 衣身补片，alpha 仅由对应肩角驱动。中立实测与 `build/chibi-layered-body-expanded/neutral_light.png` RGB 差 0；指定左大角样本 `L_a-1_e-1_w-1_body-1` 不再露青色尖角，见 `qa/occlusion_probe_3/pocket_L_target.png`。**不能据此推广**：`R_a-1_e1_w-1_body1_dark` 中，原样本仍有一段应当露出的右口袋，补片却把它整段抹掉，目视对比 `pocket_R_original.png` 和 `pocket_R_counterexample.png`。单肩参数无法准确表达袖子、肘与身体相对遮挡；inpaint 也不是获批的原画。目标样本改善不是整体解决。

采集了身体 33 姿态（每姿态浅/深背景）及视觉矩阵 48 固定、20 连续混合帧；并非双侧全笛卡尔或连续空间穷举。对身体矩阵做完整重采：66 张 PNG 与首次逐像素一致，重采前 rig/可执行文件哈希在 `body_provenance.json`，姿态在 `body_poses.json`；混合矩阵在 `mixed_poses.json`。原样本 `pocket_R_original.png` 是此前分层袖捕获，**未保存当时采样前哈希**，不能补称已有。哈希仅包含 rig.json 与执行文件，不包含所有纹理、系统库或运行环境，不能据此单独证明完整构建同一。

## 痛眼：手绘次线仍有分离感与灰影

`pain_branch_art_study.svg` 为独立手绘细分支，`tools/build_chibi_drawn_pain_branch_study.py` 把它作为独立部件，复制主眼睫的眨眼网格并在 pain=0 时压向主线；需隔离 C 引擎 `zhuochong_eye_morph_experiment`，不改生产引擎。真实 C 采双侧 smile/pain 取 0/.5/1、blink 取 0/.5/1 共 54 帧；另采 blink .85/.925/1 共 54 帧。目视 `eye_L_close.png`、`eye_R_close.png`：痛眼下支路依然偏灰、与主线分离，看起来像两层线；`eye_L_open.png`、`eye_R_half.png` 是普通矩阵代表，不能仅看睁眼就宣布通过。该分支是手绘新尝试，但仍是两部件叠绘，缺少保证交汇和边缘一致的结构；不应继续只调线宽、压缩量或透明度冒充新机制。

近闭矩阵完整重采：54 图及 6 拼图（60 PNG）均与首次逐像素相同；重采前哈希及姿态分别见 `eye_close_provenance.json`、`eye_close_poses.json`。普通矩阵采样前未记录哈希，不能事后冒称已记录。近闭采样只限白背景、所列单侧表情及共同眨眼；没有连续动画或其他环境验收。引擎哈希不含资源与依赖库。

## 工具与验证

- `capture_chibi_expression_mix.py` 和 `capture_chibi_body_joint_matrix.py` 新增独立的 `provenance.json`，保留原 `poses.json` 结构；修正非有限 blink 值校验。新增测试验证结构、隔离候选包校验、有限/重复值拒绝和真实 C 采集前哈希，不构成外观验收。
- `make test-chibi-pocket-cover-and-pain-branch test-chibi-contour-studies test-chibi-occlusion-diagnostics` 本轮通过；完整核心、Windows、长期运行未跑。
- 复现示例（使用 `build/` 下全新路径，需 Pillow、numpy、OpenCV、resvg-py）：

```sh
make build/zhuochong_preview build/zhuochong_eye_morph_experiment
/home/user/.imgenv/bin/python tools/build_chibi_pocket_cover_study.py build/pocket-cover-repro
/home/user/.imgenv/bin/python tools/capture_chibi_body_joint_matrix.py build/pocket-cover-repro build/pocket-cover-repro-qa
/home/user/.imgenv/bin/python tools/build_chibi_drawn_pain_branch_study.py build/drawn-branch-repro
/home/user/.imgenv/bin/python tools/capture_chibi_expression_mix.py build/drawn-branch-repro build/drawn-branch-repro-qa --preview-executable build/zhuochong_eye_morph_experiment --blink-values .85 .925 1
```

下一步须研究能随实际相对轮廓连续变化的遮挡/美术结构，以及指根共享接缝与独立层序（含补画）和眼线真正连续的交汇结构；先定位可实施方案及相邻帧真实 C 反例，再扩展全部要求的肩肘腕、眼部和手指组合，之后核查编辑器、拆件/绑定/参数/预览/打包/测试及实机链。不是以更多采样或更多相似补片代替修复。
