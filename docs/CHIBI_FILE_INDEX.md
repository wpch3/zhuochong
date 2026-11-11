# Chibi 文件索引（新旧标明，防再混）

| 类别 | 路径 | 状态 |
|---|---|---|
| NEW 母图 | `characters/xiaoxun/design/design_sheet_chibi.png` | ✅ 唯一真值源 |
| NEW 桌宠参考 | `characters/xiaoxun/design/chibi/desktop_pet_base_2026-10-31.png` / `desktop_pet_walk_side_2026-10-31.png` | ✅ 干净参考（非拆件源） |
| NEW 生产形态 | `characters/xiaoxun/forms/chibi/`（rig 81部件，见其 README_NEW_新版.md） | ✅ 当前生产，已入库 |
| NEW 预览证据 | `docs/qa/new_chibi_preview_2026-11-10/`（全身/脸/引擎帧/重建日志） | ✅ |
| OLD 生产形态 | 原 `forms/chibi` 49部件旧 rig+旧 sprites | ❌ 2026-11-10 已彻底删除（git 历史可溯，禁止恢复） |
| OLD 候选副本 | `docs/qa/chibi_candidate_2026-11-01/`、`docs/qa/chibi_candidate_2026-11-02/`（含已删的旧模型 sprites 副本） | ⚠️ 仅历史文字/试作证据，内含旧像素，禁止当新模型取用 |
| 隔离构建区 | `build/new-chibi-live/` | 沙箱临时，成果已复制入库，不算交付物 |

## 2026-11-11 新增 / 变更

### 手部（重要）
| 文件 | 说明 |
|---|---|
| `design/hands/hand_study_sheet_v1.png` | **手部唯一有效来源**。四格（并指/略分/开掌/握拳），约 500px 宽，紫红键色底。66px 生产尺寸下指缝仍可读。 |
| `design/hands/hand_relaxed_v2.png` + `_right` | 研究图第 2 格切片（并指放松手），左右各一份，带 alpha。 |
| `design/hands/hand_open_v2.png` / `hand_together_v2.png` / `hand_fist_v2.png` | 其余三格切片 + `_right` 镜像，已入库备用。 |
| `design/hands/hand_finger_raw.png` | 现指向 `hand_relaxed_v2`（旧 v2 生图五指手已废，被"岔开"否决）。 |
| `forms/chibi/sprites/hand_l.png` / `hand_r.png` | 57×58 / 58×59 并指手（旧为 74×50 两叉手）。**@2x 同步更新**。 |
| `forms/chibi/sprites/hand_l_finger.png` / `hand_r_finger.png` | 51×74 手指档，`pivot` 为画布世界坐标。 |
| `sprites/_orig/arm_parts_hand_baseline.json` | 换源基线（枢轴/尺寸）。**不要删**，删了换源会因读污染值把手指到画布外。 |

**层号**：`hand_l` 138 / `hand_r` 139 / `hand_l_finger` 142 / `hand_r_finger` 143。
pose 变体必须高于本体，否则切档看不见（曾用 132 失败）。

**参数**：`ParamHandLFinger` / `ParamHandRFinger`，0=放松并指手，1=手指档。

### 总图
| 文件 | 说明 |
|---|---|
| `design/sheets/chibi_spec_master_2026-11-11.png` | **规格总图（引擎真合成）**：A 放松档整身 / B 手指档整身 / C 手部研究源。零件来源以此为准。 |
| `design/sheets/master_turnaround_v1.png` | AI 三视图 v1（用户认可其形象/服装/耳）。**仅作形象基准**，手与尾巴不达标，不作零件来源。 |
| `design/sheets/master_turnaround_v2.png` | 尝试修正尾巴的 v2，**失败**（锯齿更重、狐尾分叉）。留档对比，禁止复用。 |

### 尾巴
`acc_tail_{relaxed,up,puff,tuck}` 主色已从 `#B8A8B8`（离色卡 80）收敛到头发主色/暗部。
形态沿用参数化贴附件，**禁止再走 AI 生成**（两批均失败，见 `REFERENCE_NOTES.md` 2026-11-11）。
