# IK / 关节校准 · T31.19 进行中

## 当前实际渲染（不是验收通过）

- `t31_19_alpha_clear_surprised.png`：teen `surprised` 冻结在 0.65s，已清理袖下灰色矩形后的正面合成。
- `t31_19_alpha_clear_underarms.png`：腋下放大图；原有两块灰矩形消失，侧边不再被方形补片扩出轮廓。来源与修复见 `tools/armpit_patch.py`。
- `t31_19_shoulder_bound_probe.png` 与 JSON：肩限制到 +25°、肘 flex 左 141.28°/右 143.45° 的实渲探针；腕在 y=461.29/462.06，远低于嘴角—下巴目标。这是说明几何冲突的证据，不是生产姿势。
- `t31_ik_stage1_surprised_angles.png` / `t31_ik_stage1_measurement.json` 是未改生产动作前的骨线/测量：左 flex 95.41°、右 97.58°，两肘仍向外。它们是问题基线，不是新姿势结果。
- `/api/frame.png?debug=bones` 和 `/api/bones.json` 使用同一套动作变换后的世界 pivot；不可用静态 bind pivot 代替动作测量。

## 用户已确认的目标

1. 肩角以当前自然下垂 bind pose 为 0°，惊讶姿势目标 **+10° 至 +25°**。
2. 双腕目标以脸中心为原点、头宽为单位：左/右约 **−0.75…−0.60 / +0.60…+0.75 个头宽**；高度落在嘴角至下巴之间。最终仍需与 `surprised_pose_reference.png` 目视对齐。
3. 惊讶肘 flex 目标 **120°–150°**（伸直=0°），肘/前臂朝内向上收，不能沿用旧 60°–90°目标。
4. 膝保留连续网格弯曲，允许轻微髋外展、膝微弯；不切开裸露膝皮肤，鞋底贴地。

对应关节合同：`characters/xiaoxun/design/joint_constraints.json`。全局肘范围不再把旧 130°上限当成惊讶目标；该动作目标依用户最新要求更新为 120°–150°。

## 已测几何冲突，需用户选优先级

当前 teen 上臂长约 162–167px、前臂约 113–116px。目标脸部高度由当前 466×748 渲染映射到 848×1360 rig canvas 后约 y=324–353；肩 pivot 在 y≈460–464。

为避免猜值，直接把肩参数推到目标上限 +25°（`ParamArmL/R A = 25/18`），并逐步实测肘参数。flex 实测 132.08°–146.48° 时，肘仍约 y=577、腕只到 y=462–465，低于脸部目标约 110px；保持 +10°–25° 肩角无法把手腕送到脸颊。要到嘴角/下巴高度，肩必须大幅高于 +25°，或改变上臂几何/长度。

因此目前**未把猜出的数值写进 `surprised` 生产动作，也未把 IK solver 接入动作管线**。请先确认优先级：保留肩 +10°–25°（腕目标需下降到上胸附近），或保留脸颊目标（允许肩大幅抬起）。此外，“肘向内向上”应明确是肘 pivot 本身靠近中线/上移，还是前臂折向脸颊；两种分支对同一腕目标会给出不同肘位。

## 双连杆 IK 与腿部限制

- 纯 C 求解器：`src/core/zik.h`、`src/core/zik.c`，测试 `tests/test_core.c::test_ik_two_link`。限制冲突返回 `ZIK_CONSTRAINT_UNSAT`，不写回 rig；另报目标可达环 clamp 与误差。
- 当前 solver 仍是原型，不读脸部 landmark，也未消除上述肩—手目标冲突。
- 膝无刚体 hinge pivot；生产继续使用 `ParamKneeL/R → seg_leg_* bend_y` 连续网格，不制造裸露切口。

## 灰色矩形修复

根因是旧 `armpit_patch.py` 将肩附近整片旧手臂包围区用逐行侧缘颜色填实，超出了无臂重绘图的真实衣服剪影。现在对有 no-arms redraw 的形态，以重绘图 alpha 为唯一剪影来源：zone 内重绘 alpha 之外清成透明；仅拷入重绘图确有的不透明像素，不再挤出灰色矩形。teen 0.65s normal 与放大图已目视复核；尚需在最终新姿势下再检查肩缝和腋下遮罩。

## 验证

第一阶段已有 `make test` 2617/0、`make selfcheck` 751/0、`git diff --check` 通过。改动后的最终测试及姿势九宫格/normal/wireframe/bones 复核仍待本轮完成；未完成验收前 T31.19 保持进行中。
