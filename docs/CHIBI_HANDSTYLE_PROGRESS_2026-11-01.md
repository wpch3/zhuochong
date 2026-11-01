# Chibi 双手型：早期隔离原型补充记录（2026-11-01）

> **本文件是补充记录，不是当前全版 QA 的权威交接，也不是验收报告。** 当前活动任务和最新版全链候选以 `docs/qa/chibi_candidate_2026-11-01/isolated_rebuild_status.md`、`README.md`、`docs/memory/TASKS.md` T67.67–T67.69 及 `docs/memory/GAPS.md` G66.52–G66.53 为准。该候选的当前已归档状态是 85 部件 / 26 动作、1410 项中 40 项失败；Chibi 双手型仍未完成生产素材、切换和实际引擎视觉验收。

本文件只补记上一轮外部隔离目录 `/home/user/zc_chibi_eye_clean_20261101_v6/` 中做过的**较早 sleeve 原型试验**，以免其运行结果丢失或被误认为当前任务已经完成。该目录不属于仓库，也没有把其中的 sprite、rig、脚本或原始图复制到生产资产。

## 1. 用户要求与不可越过的门槛

- Chibi 同时保留此前选定的小巧手，并新增红圈参考所指的手套感/连袖感手型；两套是独立可切换形态。
- `hand_style` 默认 small，并与腕部运动和手势动作分离；左右件必须来自合规 Chibi 来源。
- 截图只作形状指导，不得直接裁成贴图；不得以 Teen 手件或 Teen 生成器输出代替 Chibi 素材。
- 遵守 `docs/memory/WORKFLOW.md` 铁律 0–14，尤其用户优先、真值源、隔离制作、本人目视实际结果、QA 不代替视觉验收、未通过和未获用户确认前不接生产。
- “Read head only”范围继续有效；对手部工作只检查明确授权的手/袖口参考，不扩展目视无关身体部件图。

## 2. 较早 v6 原型做过什么

- 候选 `tools/make_hand_parts.py` 在重建手势件时保留了既有 `hand_*_sleeve` 部件和 `styles` 元数据；随后修正打印时对可选 `wrist_w` 的处理，重跑退出码为 0。
- 候选 `tools/make_rig.py --character xiaoxun --form chibi` 成功生成 65 部件 / 25 动作的 rig。
- 用候选 C 源编译的探针通过 `zrig_load` 加载这份旧候选 rig，并验证透明度：默认 small=1 / sleeve=0；切至 sleeve 后 small=0 / sleeve=1；保持 sleeve 选择触发 open 手势后，small 和 sleeve relaxed 手均隐藏、open 手显示。旧候选 C 核心测试为 1412 通过 / 0 失败。
- 这些只证明旧候选的 rig 参数与可见性切换可运行；`sleeve` 命名、部件与位置尚未按当前 T67.69 `small` / `mitten` 合约复核，也没有通过用户视觉验收，不可据此标记 T67.69 完成。

## 3. 旧候选 QA 失败与和当前候选的区别

旧 v6 报告仍可在隔离目录找到：`/home/user/zc_chibi_eye_clean_20261101_v6/logs/asset_qa/chibi_handstyle_report2.json`，708 项中 20 项失败。手部失败包括：heart 面积约 39–40%（门槛 55%）；heart 腕口 6px、open 腕口 5px（原画腕宽 43px）。另有裙摆 mask 格式、鞋口抬高、上臂袖片边缘、张嘴牙像素、裙摆接缝、嘴越过下巴、摸头区域和键色残留等未通过项。旧候选静止像素比较差 1768px。

该结果**不可与当前** `docs/qa/chibi_candidate_2026-11-01/asset_qa_clean_failure_summary_2026-11-01.md` 混算：后者来自另一份 85 部件 / 26 动作 clean rebuild，1410 项中 40 项失败，是当前全链重建的权威失败摘要。旧候选的 65/25、708/20 和 1768px 只用于历史参考，不覆盖新候选数值，也不证明当前候选已具备双手型。

## 4. 未纳入的旧手势源图

- 旧 v6 的 `characters/xiaoxun/forms/chibi/design/hands/hand_open_raw_v2.png` 已查看但未接入；当时检测腕口宽度 32px，不能据此认定满足 43px 基准。
- `hand_heart_raw_v2.png` 当时因生图额度耗尽未生成；不重复同一失败请求。
- 后续只从通过目视的 Chibi 原设 / 用户批准的 Chibi 来源派生素材，按 T67.69 交付 `hand_l/r_small` 与 `hand_l/r_mitten`；不要把旧 `sleeve` 原型直接改名当作完成件。

## 5. 接续原则

1. 当前全链重建以 T67.67 / G66.52 的 clean candidate 与失败摘要为基线；手型设计以 T67.69 / A62 / G66.53 的契约为准。
2. 先确认 Chibi 原画的腕根、袖口、袖条和左右比例，再为两种手型制作独立左右件；参考图只指导形状，不能直接裁片。
3. 每次制作都留在隔离候选；验证手型互斥、腕转、gesture 独立、袖口连续后，再跑全版严格 QA 与 C 引擎状态矩阵。
4. QA 零失败、无缺件警告、静止重组通过、真实引擎视觉检查通过且用户确认之前，不接入生产。

更多当前状态与门禁见：
- `docs/qa/chibi_candidate_2026-11-01/isolated_rebuild_status.md`
- `docs/qa/chibi_candidate_2026-11-01/README.md`
- `docs/qa/chibi_candidate_2026-11-01/hand_style_variants_2026-11-01.json`
- `docs/memory/WORKFLOW.md` 铁律 0–14
