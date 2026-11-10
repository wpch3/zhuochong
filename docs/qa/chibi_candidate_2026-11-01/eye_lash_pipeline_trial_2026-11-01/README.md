# Chibi 眼睫依赖链修复试验（WIP，不接生产）

日期：2026-11-01
活动分支：`arena/aaf1408c-zhuochong`
状态：**有可见改善，但眼角残留仍未通过目视；仅隔离候选；不是完整构建验收。**

## 真值源与范围

- 用户全身参考：`../reference_generated/chibi_fullbody_live2d_user_image_29_2026-11-01.png`，SHA-256 `0d337f8cc4790f9297209774f652e6677f90f2b986248d244e70167e1e72c4f0`。它用于角色身份、整体比例/画风和脸部观感对照，**不是可直接裁切的生产贴图源**。
- Chibi 设定稿：`characters/xiaoxun/design/design_sheet_chibi.png`，SHA-256 `496dc41f935d35619da35f6a3a2b8408aeb2646847ac0807334c5a466be5097c`。眼部试验仍从 Chibi 自己的源件/工具产生，不借用 Teen 贴图。
- 目标限定为当前 Chibi 眼睫/眼角拆件依赖链；未改变 Teen，也未重写或替代整个 Chibi 原画。

## 查明的实际根因

前几次 1× 形态学试验没有改变真实 C 引擎画面，原因不是“C 引擎没有读图”，而是我没有完整重跑素材依赖链：

1. `tools/make_eye_parts.py` 输出 1× `eye_l_lash.png` / `eye_r_lash.png`。
2. `tools/make_eyeline_parts.py` 从 1× lash 派生上眼线 `eye_*_lash_up.png`，并修复 `seg_head`。
3. `tools/make_hires_sprites.py` 派生 `eye_*_lash_up@2x.png`。
4. `tools/make_rig.py` 检测高清件并把 rig 指向 `eye_*_lash_up@2x.png`（`scale=0.5`）。

我此前只重生 1× 件，C rig 实际继续载入旧 `@2x`；未重启/未更新完整依赖时的对比不能用来判断 1× 美术改动。此因果由候选 `rig.json` 的部件文件路径核实。隔离试验脚本差异保存在 `make_eye_parts_trial.patch`，没有把该 patch 应用到正式工具或正式贴图。

## 本次真实实施

- 只在隔离 Chibi 候选中收紧 upper-lash 的几何 ROI，避免暗像素提取器把虹膜下缘和眼角周围的暗碎片一并当作上睫毛。
- 按依赖顺序重跑：
  - `python3 tools/make_eye_parts.py --character xiaoxun --form chibi --root .`
  - `python3 tools/make_eyeline_parts.py --character xiaoxun --form chibi --root .`
  - `python3 tools/make_hires_sprites.py --character xiaoxun --form chibi --root .`
  - `python3 tools/make_rig.py --character xiaoxun --form chibi --root .`
- 重新启动候选 C 预览后，切到 Chibi、冻结时钟并抓取完整帧；另用 `/api/part?vis=2` 分别隔离 `seg_head` 和 `eye_l_lash` 观察。相关实拍在本目录。
- 左右候选 `@2x` 睫毛图、`eye_parts.json`、`eyeline_parts.json` 与完整定向 QA JSON 均在本目录，可离开会话后复核；`SHA256SUMS.txt` 给出每个文件哈希。

## 本人用眼观察

对照图 `engine_face_before_after_4x.png` 将先前 C 引擎脸部实拍与本轮实拍缩放到相同预览帧尺寸后，以相同 ROI 放大并排：先前眼角上方有明显不规则的深紫色大块/毛刺；依赖链完整重生成后，眼睫主弧更连续、角部大块显著收敛。隔离 `eye_l_lash` 可见它是单独的上眼线弧；隔离 `seg_head` 仍能看见脸/发交界处的细小源图碎边。

**尚未通过**：全脸实拍在左右外眼角仍见小的黑/白碎边或切口状细节，与 `seg_head`/头发交界残留有关；目前没有确认其全部来自 lash mask，也没有证据证明已经达到 image-29 的干净观感。不得把“主弧更平滑”表述成“眼角修复完成”。下一步需要在实际原画 ROI 与头发遮挡层级中进一步定位这些残留，必要时分别隔离发件/脸件/眼件，再做局部候选；不得盲目扩大形态学半径。

## QA 口径

`asset_qa_focused_rerun.json`：退出码 1，**1310 项、32 项失败**，`design_iou=0.9934918477598998`。这是本轮眼部依赖链更新后的定向/当前候选快照，不是 27 步全链；项目范围与条目数也不同于历史完整来源锁定候选 **1342/34 fail** 与摸头定向候选 **1342/33 fail**，不可直接相减或声称整体 QA 改善。错误清单仍含身体洞、切分差额、鞋、闭眼接缝、嘴、腮红、发型接管、手垫片等旧缺口。

## 生产门禁与后续

- 没有改正式 `characters/xiaoxun/forms/chibi/sprites/` 或正式 `rig.json`；候选贴图/rig 仅作为隔离试验和本目录的审计证据。
- 没有用户确认；没通过本人目视；没通过全链零失败与 C 引擎组合矩阵；不得接生产。
- 下一步优先解决仍可见的两个眼角细碎边及其根因，逐次保存 C 引擎整图/放大/隔离层；之后仍须按 `G66.52` 逐项处理 32 项/既有全链失败、缺件及 `T67.69` 双手型，不可把眼部局部进展当作整个 Chibi 已完成。
