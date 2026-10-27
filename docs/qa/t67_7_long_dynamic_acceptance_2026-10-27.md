# T67.7 长发 · 去噪修复与 ParamHairSway 三帧动态验收（隔离 testroot，待用户批准生产接入）

日期：2026-10-27 ｜ 环境：`/tmp/zc-t677-KA7rCb` 隔离副本 + 端口 5201 ｜ 生产 `rig.json`/`sprites` 全程未改。
配套静态记录：`t67_7_long_static_registration_2026-10-27.md`。可复现脚本：`tools/t67_7_build_long_hair.py`（对 testroot 现用件逐字节复现，平均差 0.0000）。

## 1. 用户反馈与修复目标

用户在产品实机截图指出：长发最左、最右两块外侧发区有黑点状瑕疵与空缺，并授权按 Live2D 惯例自行决定 `hair_side_l/r`、修好后直接做动态。
说明：实机当时仍是旧长发（新件从未接入生产），但像素扫描确认**黑点在获批母稿纹理本身**，新件如实继承，必须从母稿层面修掉。

## 2. 黑点根因与去噪（铁律：先取真值再动手）

- 量化：母稿真赛璐璐线稿（贴 alpha 外轮廓的描边）亮度集中在 lum 78~107（深藏青/灰）；lum<45 是一族与线稿断开的纯黑 `(0,0,0)`/暗绿噪点，原分辨率约 380 个、左右外侧各约 1000 画布像素，形态为 1~7px 孤立紧凑颗粒（非连贯线）。
- 判据：lum 35~60 之间几乎无像素，证明纯黑点是独立噪点群体而非抗锯齿线稿；母稿仅含头发、无眼眉，可安全按亮度清除而不伤线。
- 做法：原 1x 母稿上迭代「选 lum<45 不透明像素 → 最近邻有效发色填色（alpha 不变）」至收敛，并补内部 alpha 空洞；随后羽化去呆毛。结果：画布实心区（alpha>200）仅 1 像素 lum<45、最低亮度 43.7，内部黑颗粒实质消除，描边线与发丝分隔线完好（见去噪前后放大图）。

## 3. 全帧裁紧：让 bend 按头发真实高度归一化

- 现象：全帧 848×1360、anchor[0,0] 时，引擎 bend 按整图高度归一化（`zimg_bend_factor`，TIP 曲线 t²，t=源 y/图高）。头发只占 t∈[0.085,0.71]，梯度被压扁，三帧实测近似整体刚移、发梢不甩。
- 修法（零像素改动）：每件按自身 alpha 包围盒裁紧，pos=包围盒左上角、anchor[0,0]、scale 0.5。裁掉的只是透明边，头发像素与配色完全不变；后发件高 853，与旧 `acc_hair_long`（851）几乎一致，根 t=0 固定、梢 t=1 最大。
- 四件裁紧后接线（隔离 rig）：
  - back `acc_hair_long` bbox x[159,687] y[112,965]（528×853）pos[159,112]
  - crown `acc_hair_crown_long` x[299,546] y[116,373] pos[299,116]
  - sidelong_l x[159,406] y[267,909] pos[159,267]；sidelong_r x[462,687] y[267,918] pos[462,267]
- 画布四件 alpha 并集对母稿平均差 0.0。

## 4. ParamHairSway 负/中/正三帧动态验收

方法：`/api/ambient?on=0` 关环境漂移 → pause → param 复位 → 设 ParamHairSway=-1/0/+1 → `step?n=200&dt=0.0167` 让物理摆子收敛 → 抓帧。部件 id 未变，生产物理链 `physics2.longhair2`（3 段摆子，吃 ParamHairSway wx3.2，输出 bend_x + longhair_mid/tip 两张 2×6 网格）原样作用于新件，未新增/改写任何形变参数。

隔离渲染（vis=2 仅 acc_hair_long）逐段 x 重心位移（+1 减 -1，帧坐标 px）：

| 分段 | 新长发 | 生产旧长发（同法对照） |
| --- | --- | --- |
| 发根 | -0.4 | -1.0 |
| 上段 | -3.1 | +2.4 |
| 中段 | -4.4 | +4.0 |
| 发梢 | -6.4 | （梢超测量带，2.4 为带内值） |

- 形态：发根近似固定、越靠发梢位移越大，标准「根定梢甩」摆子，无扭曲/撕裂/露缝/黑点（隔离三帧图）。
- 幅度：中段新 -4.4px 与旧 +4.0px 同量级；符号相反只是 ±1 的左右约定，参数本就双向振荡。幅度克制，符合参考口径「长发摆幅忌过大」。
- 结构与生产一致：仅后发有独立物理；`acc_hair_sidelong_l/r`、`acc_hair_crown_long` 无独立 physics/physics2 条目，随 head 组转动（生产旧件同为如此），三帧中身体/腿/裙固定、头不漂移。
- 中帧（v=0）静态造型与去噪后静态稿一致，零回退。

## 5. hair_side_l/r 裁决（用户授权「Live2D 是哪种就选哪种」）

母稿是完整独立发型（自带脸侧缕与头顶），与常驻短发 `hair_side_l/r`（齐腮蓝梢 bob）叠成双层。Live2D 惯例是整套发型接管、不并存两簇侧发。隔离 rig 的 long 档 `hide` 在原有 `hair_back` 基础上增加 `hair_side_l`、`hair_side_r`，双层消失、脸颈干净（静态图已验证）。建议生产接入沿用此 hide 方案。

## 6. 证据图（本目录）

- `t67_7_long_speck_before_zoom_L_2026-10-27.png` 去噪前外侧发区（红标黑颗粒，蓝/绿为保留线稿）
- `t67_7_long_despeckled_zoom_L/R_2026-10-27.png` 去噪后引擎实拍外侧发区（黑点消失、线稿完好）
- `t67_7_long_static_v5_white_2026-10-27.png` 裁紧去噪后最终静态（白底全身）
- `t67_7_long_sway_iso_back_three_2026-10-27.png` 隔离后发件 -1/0/+1 三帧（根定梢甩）
- `t67_7_long_sway_full_three_2026-10-27.png` 全身三帧（灰底，身体固定、后发轻摆）
- 源资产：`characters/xiaoxun/source/t67_7_master_haironly_v2_final.png`（获批母稿）、`t67_7_master_clean_dropahoge.png`（去噪去呆毛生产源）

## 7. 生产接入清单（未执行，待用户批准）

1. 用 `tools/t67_7_build_long_hair.py --out-sprites characters/xiaoxun/forms/teen/sprites` 生成正式贴图并改为生产文件名（替换旧 `hair_long_back@2x.png` 等，或新增 t677 命名后改 rig 指向）。
2. rig 四件 pos/anchor/scale 按本记录第 3 节写入；crown 的 `socket_head_top` 与全帧/裁紧 pos 冲突，需重新决策定位（socket+dpos 或去 socket 用绝对 pos）。
3. long 档 hide 增加 `hair_side_l/r`（第 5 节）。
4. 物理链 longhair2、longhair_mid/tip 按部件 id 自动生效，接入后回归 ParamHairSway 与转头/呼吸。
5. 真机表现始终标 `[需真机]`，不在沙箱代宣布完成。
