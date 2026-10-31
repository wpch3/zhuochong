# 小寻 Live2D 目视审查与重制计划（2026-10-31）

## 执行进度

- T67.67 已启动：从设计真值重新生成的隔离 `body_full` 候选比当前 567 基线明显更干净；完整切件/高清化/rig 重建与真实引擎目视仍未完成。当前候选仅作阶段证据，不接入生产。

## 执行顺序

1. **P0 — Q/chibi 全版重生成（用户明确要求）**：当前 Q 版真实 C 引擎帧和用户提供的截图均未通过视觉验收；不得只补现有刘海/发侧碎线。以 `characters/xiaoxun/design/design_sheet_chibi.png` 为设计真值，检查源件后整套重建 Q 版可见素材与组装；再还原/重建所需骨骼、附件和动作绑定。全程先在隔离副本中试产，保留旧版作对照，不覆盖 Teen，也不把机检绿当视觉通过。
2. **P1 — Teen 长发五组重造（T67.7）**：真实引擎 `acc_hair_long` 单件隔离帧的两侧仍能看到黑/青/白条状杂边，完整长发帧也可见。按 `docs/PART_LAYERING.md` 的五组方案从 `sheet_long.png` / 已登记长发母稿重做，不再对旧件做局部洗色或几何擦除。依照 T67.7 既有门槛，候选先单独出图并给用户目视确认，再接生产 rig。
3. **P1 — Teen 袖子/腋下（T67.6、T67.35、T31.15 / AC-32）**：静态三套衣服全身帧没有看到大面积破洞；但 wave 抬臂帧的袖子有明显硬三角形折痕，白夹克—青袖/腋下交界出现细窄浮边与碎色。重造上臂袖、前臂袖、袖口环三件套；以真实 wave/jump/surprised 逐帧查 60°/90° 及最大外展；同时按 AC-32 两个 UI 入口复验口腔下沿与白缝，不复用盲修坐标。
4. **P2 — Teen 动态完整性**：已实看 wave、surprised、tiptoe、heart_hands 代表帧；这些帧均可渲染，当前样本没有整体姿势塌陷或明显脚底穿地。长发 `ParamHairSway=-1/0/+1` 有变化但幅度不大，需在长发重造后重跑完整时间线与物理极值，不先把这项误报为引擎缺陷。
5. **P2 — Teen 骨架复核**：`/api/bones.json` 与 bones-only 帧显示抽查的双臂链存在且关节衔接正常；surprised 第 54 帧左右肘屈曲约 149.84°/147.38°，wave 第 48 帧抬起侧约 133.65°。本次没有发现确证断链，不能据抽帧宣布全骨架通过。待服装件更新后以 bones-only、全动作极值及 `check_skeleton.py` 契约一起复核。
6. **P3 — 组合回归**：Teen 三服装（default/cocoa/midnight）×四发型（none/long/twin/pony）×帽子上下静态矩阵已采集；后续对新长发和袖子做组合回归，检查排序、遮挡与配件切换。静态矩阵在全身尺度未见明显大洞，不代表动态缝线已验收。

## 目视证据与判据

本次截图来自 `http://127.0.0.1:5199` 的真实 C 引擎；透明画布在可读证据中合成白底，避免把透明区误判成黑洞。证据文件及 SHA-256 清单见 `live2d_teen_visual_audit_2026-10-31.json`。关键图：

- `live2d_teen_audit_longhair_full_2026-10-31.png` 与 `live2d_teen_audit_longhair_isolated_2026-10-31.png`：长发全身与 `acc_hair_long` 单件隔离；两侧条纹杂边真实归属于该长发件。
- `live2d_teen_audit_wave_sleeve_detail_2026-10-31.png`：高举手臂的袖管与夹克接缝近景。
- `live2d_teen_audit_outfit_matrix_2026-10-31.png`、`live2d_teen_audit_motion_matrix_2026-10-31.png`：静态三套衣服和四类动作抽帧。
- `live2d_teen_audit_surprised_bones_2026-10-31.png`：真实动作 bones-only 叠图。

每个重制单元仍需亲自检查真实引擎的全身帧和细节帧；数值/静态闸只用于定位与回归，不能替代视觉验收。Q/chibi 首个工作单元执行后，先提交并推送，再继续 Teen 制作。
