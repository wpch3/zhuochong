# Chibi `small` / `mitten` 手型研究（阶段 WIP）

**状态：隔离视觉候选，不是生产贴图、拆件或引擎验收。** 当前只推进 T70.2 的 Chibi 来源、手型几何和袖口拟合；生产 `sprites/`、`rig.json`、生成器和 C 引擎均未修改。

## 来源与既有真值

- `characters/xiaoxun/design/design_sheet_chibi.png` 注册几何为 `[628,101,1416,1891] → 567×1292`；来源 SHA-256：`496dc41f935d35619da35f6a3a2b8408aeb2646847ac0807334c5a466be5097c`。
- `small_left_source.png` / `small_right_source.png` 是 Chibi `body_full.png` 腕口 ROI 原像素裁片，仅作参考；左 ROI `[43,846,132,938]`，右 ROI `[435,846,524,938]`。
- `mitten_left_concept.png` / `mitten_right_concept.png` 是脚本绘制的平涂几何示意，违反“手必须用原画件做部件，禁程序化画手”铁律，明确拒绝为手部美术。仅留档说明早期错误尝试；不得作为正式参考、生产贴图或 rig 输入。

## 本轮 AI 画稿探索（均未通过生产门禁）

- `mitten_left_art_trial_02.png` 直接编辑腕口裁片，改大袖口/手部比例，拒绝。
- `mitten_hand_only_left_trial_03.png` 只生成手部，但腕根过长、比例和阴影风格偏离 Chibi，背景也不是可靠透明，拒绝。
- `mitten_left_art_trial_04.png` 与 `mitten_right_art_trial_05.png` 分别以 Chibi 左/右腕口原画作画风/尺度来源、用户红圈截图仅作形状提示，分别生成左右圆掌候选。**没有复制或裁切截图像素。** 两张输出都改动了袖口几何/条纹，背景亦不适合作为贴图。
- `fit_mitten_ai_trial.py` 仅对 04/05 的手掌做区域分割、按 Chibi 小手占位缩放、映射到小寻色卡，再用 Chibi `body_full` 的源袖口像素复盖原 AI 袖口。右手是独立生成的 trial 05，不是左手镜像。生成 `mitten_left_ai_fit_wip.png`、`mitten_right_ai_fit_wip.png`、`body_full_ai_mitten_preview_wip.png` 与 `hand_style_ai_candidate_board_wip.png`。
- 已目视检查新板：两只手都比 small 圆钝、分指更弱；缩略全身底图未改。但袖口腕根仍见疑似边缘/阴影接缝，线稿与源画的细节密度也未完全一致；左右尺寸和动作方向未做 C 引擎检查。故它只是未批准的 AI 拟合候选，不是合规完成稿，不能进 rig 或生产。

## 不能越过的门槛与下一步

1. 用户红圈截图仅作形状提示；不得复制或裁切其中像素。不得用 Teen 手件，也不得把脚本几何示意改名后当生产素材。
2. 需审阅并修整 trial 04/05 的左右腕根、线稿、色阶/暖影、袖口条纹遮挡与 1×/@2× 接缝；若风格不能通过，就拒绝该 AI 候选，不能为了进度硬接生产。
3. 美术门禁通过后，才在隔离 rig 拆 `hand_l/r_small` 与 `hand_l/r_mitten`，以独立 `hand_style` 切换；腕角与 open/heart 手势保持正交。之后用真实 C 引擎检查接缝、无重影/空洞/跳尺寸，以及动作/衣物组合。
4. 当前 full-body Chibi、眼口、发型/兜帽、服装遮挡及动作矩阵仍未通过；本目录任何图均不能关闭 A64 / T70.2–T70.4。

## 文件

- `build_hand_style_study.py`：生成 Chibi 原像素观察窗与已拒绝的几何示意。
- `fit_mitten_ai_trial.py`：只对 AI 试稿做隔离的 alpha 分割/配色/套准，不绘制手、不写生产路径。
- `source_crop_manifest.json`、`study_metrics.json`、`mitten_ai_fit_metrics.json`：来源、坐标、产物 SHA 与门槛说明。
- `SHA256SUMS.txt`、`mitten_ai_fit_SHA256SUMS.txt`：两组 WIP 文件校验清单。
