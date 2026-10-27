# 短发骨骼/绑定完工审计（2026-10-27）

用户要求：「同步检查短发骨骼是否为完工，是否没有问题。」
范围：xiaoxun **teen 短 bob**（默认发型）与 **chibi** 头发绑定。只审计，不改生产素材与 rig。
方法：rig.json 静态核对 + headless 真实渲染（5200 端口，repo 基线 root）参数驱动抓帧 + 阵风脉冲衰减 + 素材闸。

## 结论

**teen 短发绑定判定为「完工且无阻断问题」，可作为长发六件重造的结构范本。** 另有 3 条非阻断的改进项/边界，列在末尾，不影响当前可用性。chibi 头发绑定健康但覆盖率低于 teen（见末尾）。

## 一、五件结构齐全（rig.json 实测）

| 部件 | layer | 骨链（旋转变形器） | 逐顶点网格 keyform | 旧弹簧物理 |
| --- | --- | --- | --- | --- |
| hair_back 后发 | 170 | hair_back_root→hair_back_mid | 有（back_s, 3×6） | back_x + back_tip 两段 |
| hair_ahoge 呆毛 | 190 | hair_ahoge_root→hair_ahoge_mid | 有（ahoge_s, 2×4） | ahoge_y + physics2 粒子链 ahoge2 |
| hair_front 刘海 | 240 | 无（贴头，设计如此） | 无 | bangs_x（tip 曲线，小幅） |
| hair_side_l 左侧发 | 245 | hair_side_l_root→hair_side_l_mid | 有（side_l_s, 2×4） | side_l_x + side_l_tip 两段 |
| hair_side_r 右侧发 | 246 | hair_side_r_root→hair_side_r_mid | 有（side_r_s, 2×4） | side_r_x + side_r_tip 两段 |

- 发根 pivot 均在头顶/鬓角挂接点，符合「发根钉死、发梢摆」。
- 104 件中 18 件接了逐顶点网格变形器，头发四件（除刘海外）全部在列。
- 呆毛已迁到物理 2.0 粒子摆链 `ahoge2`（混 ParamBreath + ParamAngleZ）；后/侧发仍走旧弹簧链——两套内核各写各通道，不重复叠加（selfcheck 有专闸）。

## 二、八参数全部真实驱动，无死参数（实测像素差）

冻结时钟、短发档，逐参数写 -1/0/+1 抓帧，`|Δ|求和>24` 计差异像素：

| 参数 | -1↔+1 差异 px | 最大通道差 | 目视（4× 放大） |
| --- | --- | --- | --- |
| ParamHairBack | 2196 | 255 | 后发整体左右摆，连续无破洞 |
| ParamHairBackS | 625 | 248 | 后发梢 S 形，根固定 |
| ParamHairSide | 3562 | 255 | 两侧发顺肩摆 |
| ParamHairSideS | 2905 | 251 | 侧发梢反向 S 形 |
| ParamHairAhoge | 561 | 255 | 呆毛整体弯 |
| ParamHairAhogeS | 363 | 255 | 呆毛 S 形镜像 |
| ParamHairFront | 1424 | 193 | 刘海轻摆，不露额头缝 |
| ParamHairFluffy | 1244 | 254 | 轮廓蓬松度自然 |

证据图：`2026-10-27-short-hair-param-zoom.png`（每参数 -1/+1 头部放大对照）。

## 三、动态收敛：阵风脉冲后回到呼吸底噪，无发散/抽搐

逐件隔离（`/api/part?vis=2`，排除尾巴/袖子/裙子等其它物理件污染），吹 1.2g 横风 5 帧后撤成零外力，量 alpha 加权限心的横向偏移包络：

| 部件 | 呼吸底噪 | 撤力 3s 后质心偏移 | 判定 |
| --- | --- | --- | --- |
| hair_back | 0.68px | 0.23px | 回底噪内 |
| hair_ahoge | 1.38px | 0.13px | 回底噪内 |
| hair_front | 2.54px | 0.88px | 回底噪内 |
| hair_side_l | 1.03px | 0.13px | 回底噪内 |
| hair_side_r | 0.73px | 0.46px | 回底噪内 |

关键口径：每条物理链都混了 ParamBreath，静止时本就持续微动，所以「与单一基线帧的像素差」不会归零；正确判据是**阵风包络衰减回呼吸底噪**。3 秒后五件全部回到底噪区间，振荡衰减无发散。证据图：`2026-10-27-short-hair-decay.png`。
低帧率抽搐问题（G113）已由定步长积分器修复，本审计未复现。

## 四、动作接线与素材闸

- 26 个动作中 15 个接了头发通道（breath/idle/sway/nod/head_pat/happy/surprised/hammered/sleep/wave/wave_both/heart_hands/kirara_jump/shift_weight/tiptoe），摸头、惊讶、睡觉、挥手等都有头发跟随。
- `make audit-sprites` teen/chibi 双形态闸通过；`qa_hair_purity` 21 件 0 成块异物违规。
- chibi 帧：`2026-10-27-chibi-short-frame.png`，短发目视健康，ParamHairAhoge 驱动有效（1321px 差异）。

## 五、非阻断改进项 / 边界（不影响「完工」判定，登记备查）

1. **后/侧发仍是旧弹簧内核**，仅呆毛迁到 physics2 粒子链。功能正常、收敛良好，但与长发规划的粒子摆链不是同一套；长发六件接入时统一走 physics2，短发是否回迁列为独立技术债，不在 T67.7 内动。
2. **刘海无独立骨链/网格**，只有 bend_x 小幅摆。贴头设计合理，但做不了发丝级 S 形；当前观感无问题。
3. **chibi 头发覆盖低于 teen**：chibi 无独立 hair_back/hair_front/hair_side 分层（短发烤在 seg_head 内），可动头发只有呆毛与三个挂件（long/twin/pony）；@2x 仅 11 件（teen 100 件）。这是 chibi 整体覆盖率缺口（T67.42），不是短发 bug。
4. 真机帧率/拖拽手感/透明窗内的实际摆动观感仍属 `[需真机]`，本审计只覆盖沙箱渲染与数据层。
