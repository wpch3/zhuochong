# T67.71 — Teen 长发动态遮挡：源像素 / 部件 / C 动作追踪

**状态：诊断有进展，未修复。** 本包新增了源图到生产贴图的坐标追踪、部件层级核对，以及真实 C 引擎的控制渲染。没有改生产 PNG、`rig.json`、生成器或 C 引擎。T67.71 仍开放；这里的图板和数字不等于美术批准或动态验收通过。

## 核心发现

1. **素材来源链已找到。** Teen 长发兜帽件来自扁平的 `characters/xiaoxun/design/sheets/sheet_long_hood.png`，切片输出 `characters/xiaoxun/design/redraw/sheetcut_hair_hood_long.png`，再经 `make_attach_parts.py` 生成 `sprites/hair_hood_long@2x.png`。切片框与生产 PNG 的坐标换算见 `capture_metrics.json`。
2. **`sheetcut` 的“hair”掩膜中肉眼可辨地包含袖口和手。** 这是实际像素来源证据；生产 PNG 中也仍看得到这些旧位置的袖口/手形。当前纯度分类器对生产长发件**没有报出**阈值内的成块皮肤/青布，但这不推翻图上可见的残留：分类器的颜色阈值不等于来源/语义分层真值，且挂件经过配色迁移。
3. **挖除区是分开的缺陷。** `qa_hair_purity.py --strict-occlusion --fail` 在 `hair_hood_long@2x.png` 内部报告 11,336 个透明像素，并找到 3 个 ≥200px 的封闭透明块：3,418px、2,970px、982px。它们约映回扁平源表的双手/袖口附近 ROI。严格透明检查另在 pony 件报 373px 封闭块；整项命令 exit 1。注意原始汇总行的通用“皮肤/衣服成块像素”提示并不等于 long 件分类器发现异物：`hair_hood_long@2x.png` 的分类列明确为“干净”，目标件的明确命中是透明块。逐项原始输出在 `hair_purity_strict.txt`。
4. **真实 C rig 把不同运动放在不同层/组。** `acc_hair_hood_long` 属于 `group=head`、`layer=258`、`pos=[422,152]`、`anchor=[0.5,0]`、`scale=0.5`；没有该部件专属的 `physics`、`physics2` 或 mesh deformer 记录。正常手/臂在 layer 138–151，惊讶动作替换件在 319–322。C 引擎按 layer 升序绘制，因此 258 会压在正常手臂上、但先于惊讶动作的高层替换件绘制。
5. **arm 动作与 sway 分开控制。** 848×1360、scale 1 的 C 样本中，arms-down idle 的腕点约为左 `(255.87,734.86)` / 右 `(592.13,734.97)`；同一 `surprised` 抬臂样本约为左 `(248.06,444.95)` / 右 `(595.75,445.42)`，两腕分别上移约 289.9px / 289.6px。对目标头发部件作只看该件与隐藏该件两种 C 观测后，旧手/袖口残留随头部所属的发片出现；隐藏它后这些残留不再出现，露出的是动作中的身体/手臂底层。新矩阵再固定 arm action 与步长，仅扫 `ParamHairSway`。
6. **区分目标附件运动与整套长发摆动。** `acc_hair_hood_long` 跟随 `head` 组动作变换，但它自己没有 `physics`/`physics2`/deformer。早先同一帧序 `ParamHairSway=0/+1` 的目标件隔离差仅 370 个像素值、最大通道差 1；本轮在五种动作与 sway 两端复测，目标件隔离图在共同底色合成后，idle/wave_both/heart_hands/wave 最大通道差为 0，surprised 最大差为 2；五种动作均没有通道差 >4 的可见像素，未证明该附件存在有意义的独立摆动。**但整套可见头发确实随 sway 变化**：rig 将 `ParamHairSway` 直接绑定到 `hair_front` 与左右 `hair_side`；本矩阵的 long + hood-up 组合仍显示这些头发件。在全身同姿势 -1/+1 对比中，显示图像约有 3,894–4,106px 的 RGB 通道差 >4（各动作 max channel delta 156–180）。rig 另有 `longhair2` physics2 挂在 `acc_hair_long`，但 hood-up pose 会隐藏 `acc_hair_long`，不能把这次画面差归因于该链。这些是合成帧差，不是逐源像素运动场，也不能算成目标附件自身的摆动。

结论不是“只有 alpha 洞”，也不是“只有层序”：**源贴图在头发层里带有不属于头发的可见袖口/手形，挖除又留下透明区；长发件由 head 组承载，而真实手臂由各自 arm 组驱动；两者的 Z 顺序在静止和动作替换层之间不同。** 这些因素共同解释了动态样本，但还没有完成对每个残留像素的逐像素因果标注，也没有修复。

## 源像素与坐标

- 输入画布：`sheet_long_hood.png`，1024×1536 RGB（洋红底）；`sheet_long_hood_raw.png` 也是合并图。`manifest.json` 登记的 sha16 为 `32f38c1006d04f4d`。
- `tools/cut_hood_from_sheets.py` 将 long 档的 `sheet_long_hood.png` 作为输入，`PLAN["long"]` 输出 `hair_hood_long`。`hood_geometry.json` 的切片框为 `[212,156,799,1020]`（含边界），即 588×865；成品 `sheetcut_hair_hood_long.png` 同尺寸、仍以洋红表示背景。该 cutout 画面内可见两侧袖口与手。
- `make_attach_parts.py` 对该源切片做洋红键色、4% 边距和配色处理，再按 `566×832` 产 1×、`1132×1664` 产 @2x。4% padding 的工作画布为 636×935，故下列是反算到输入表的**近似边界**（LANCZOS/高清化之后不能声称逐像素同一）：
  - 生产 PNG `[x=915..989,y=1193..1311]`，3,418px → 源表约 `[702.08,791.35]–[744.22,858.21]`。
  - 生产 PNG `[x=147..220,y=1192..1311]`，2,970px → 源表约 `[270.59,790.78]–[312.17,858.21]`。
  - 生产 PNG `[x=878..929,y=1159..1208]`，982px → 源表约 `[681.29,772.24]–[711.07,800.34]`。
- `source_trace_board.png` 按同一近似换算，将封闭透明块框回扁平全身输入、切片输出和当前生产 PNG。颜色框顺序和精确阈值 bbox 在 `capture_metrics.json` 与 `hair_purity_strict.txt` 中。

## C 引擎控制方式

- 重新启动 `make preview`；本轮实际服务绑定 `0.0.0.0:5173`，`/api/info.json` 和 `/api/frame.png` 返回 200，当前预览已恢复为 long + hood-up 的完整可见状态。
- 固定 `scale=1.0`、关闭 ambient、选择 `hairstyle=long` / `hood_pose=up`。静止帧设 `ParamHairSway=0` 并在固定步长后抓图。
- 两个惊讶分支从同一起始时刻触发 `surprised`，先 step 12×0.05s，再分别设 `ParamHairSway=0` 或 `+1`，再 step 10×0.05s；动作端点 effective 参数：`ParamArmLA/RA=0.6`、`ParamArmLB=8.35`、`ParamArmRB=8.1`、`ParamSurpriseArmSwap=1`。
- 使用 `/api/part?id=acc_hair_hood_long&vis=2` 隔离目标发片；用 `/api/part?all=1` 后再 `vis=0` 隐藏目标发片并检查底层。抓完已恢复正常可见性。
- 原始 C 帧：`idle_sway0_c_engine.png`、`surprised_sway0_c_engine.png`、`surprised_sway1_c_engine.png`、`idle_sway0_hair_isolated_c_engine.png`、`surprised_sway0_hair_isolated_c_engine.png`、`surprised_sway1_hair_isolated_c_engine.png`、`surprised_sway1_hair_hidden_underlay_c_engine.png`。综合图板：`c_engine_action_isolation_board.png` 与 `c_engine_head_group_isolation.png`。

### 扩展真实 C 动态矩阵（2026-11-04）

- 以 `capture_pose_matrix.py` 固定 848×1360、scale 1、ambient off、physics on；每个分支先在同一虚拟 t=2 关物理复位，再设置 long + hood-up 与 `ParamHairSway=-1/0/+1`。五个动作/姿势样本：arms-down idle（3s 固定步）、surprised（1.1s）、wave_both（1.0s，靠近双臂高位段）、heart_hands（0.6s，双手姿势 pulse 到位）、wave（1.0s，单臂高位）。共 15 张全身 C 帧；每个 sway 端点还抓目标件 only/hidden 控制，动作状态与物理时间冻结。
- C bones 腕点（每个 sway 档相同，左 / 右）：idle `(255.67,735.75)/(591.92,734.02)`；surprised `(248.06,444.95)/(595.75,445.42)`；wave_both `(189.26,461.28)/(641.89,457.80)`；heart_hands `(375.42,571.61)/(474.39,572.13)`；wave `(238.83,735.95)/(630.03,451.04)`。矩阵的 `params.json` 也保存动作端点通道和实际 effective `ParamHairSway`。
- 在相同动作、时刻和已复位物理下对比 `ParamHairSway=-1/+1`，共同深灰底合成的全身图约有 3,900–4,100 个可见像素通道差 >4，max channel delta 156–180；arms wrist 坐标不随 sway 变。这说明其他可见头发/物理部分响应了 sway，不能把这些全画面差归给 hoodie 附件。
- 对 `acc_hair_hood_long` 作 target-only 两端控制：idle、wave_both、heart_hands、wave 的显示帧 max RGB 差 0；surprised 的 max 差 2；五种状态皆无通道差 >4 的可见像素。它与全身长发 sway 的明显变化分开。全身/局部板：`c_engine_sway_pose_matrix_fullbody.png`、`c_engine_sway_pose_matrix_detail.png`；两端 full/target-only/target-hidden 控制板：`c_engine_sway_pose_matrix_visibility_controls.png`。`pose_matrix_metrics.json` 与每状态 info/params/bones 快照记录数值，原帧命名为 `matrix_<action>_sway_<minus1|plus0|plus1>_c_engine.png`。
- 本人目视三张新板：惊讶、双手挥、比心、单臂挥手样本中，动作手臂运动到不同位置，但发片隔离图始终可见其烘入的旧袖口/手形；隐藏 `acc_hair_hood_long` 后这些碎片消失，实际动作手/袖仍保留。它是覆盖/残留的诊断证据，不是美术动作通过。姿势覆盖仍只有五个代表动作，未穷尽所有 arm angle/transition/sway timing。
- 另用 `capture_action_sweep.py` 对 neutral sway 的 `surprised` 与单臂 `wave` 做 13 个真实 C 时间点：surprised t=0.15/0.30/0.60/0.90/1.10/1.30s；wave t=0.15/0.30/0.60/0.90/1.10/1.80/2.30s。surprised wrist y 从约661→506→445（0.60–1.10s）→658；`ParamSurpriseArmSwap` effective 对应 0.337→0.75→1.0→0.345，说明 0.3s 正在交叉替换，不把半透明过渡帧冒称稳定端点。wave 右腕 y≈716→651→491→455→448，随后保持并在2.30s回落至610，左腕保持 y≈732–738。旧手/袖口碎片沿动作过程仍留在目标发件。时序全身帧、逐时刻 params/bones 与板 `c_engine_surprised_timing_sweep.png`、`c_engine_wave_timing_sweep.png` 已保存；板为上身局部裁切，坐标和判定用原始帧/JSON。

## 来源门禁 / 未完成项

- 扁平 `sheet_long_hood.png` 与 `_raw.png` 都只有合成后的可见像素；全仓没有 `.psd`、`.psb`、`.kra`、`.xcf` 分层作者文件。袖口/手覆盖处被遮住的发丝像素不在此扁平图里；非兜帽 `sheet_long.png` 是不同造型，不能冒充此造型的隐藏发丝真值。
- 因而尚无获批的隐藏头发原稿或可靠的逐缕复原像素来源。当前不可直接把手/袖口整体挖空后留洞，也不可用随意邻域涂色、任意位移或全贴图 `alpha=255` 规则掩盖问题。合理下一步是拿到获批的分层/补画源，或在隔离 WIP 中提出可审阅的头发连续性重建并先通过视觉与动态门禁；本轮没有启动未经批准的重建，更没有写入生产贴图。
- 当前 C 证据新增覆盖 arms-down idle、surprised、wave_both、heart_hands、wave 五个代表动作各自的 ParamHairSway -1/0/+1，以及端点时隔离/隐藏目标件。它仍不是穷尽的动态矩阵：动作过渡逐帧、其他手臂角度/单臂姿势、完整摆动时间相位与其他兜帽/发型组合仍待验证。
- `make test`（C-only）实跑 **2,638 项通过 / 0 失败**；保留既知 `_zperf_probe` unused-function warning 和负向测试预期诊断。`selfcheck_all.sh` 本轮未运行。图像 QA 是独立 `qa_hair_purity.py`，明确 exit 1 如上；不与 C 单测混计。预览运行状态由后台 `make preview` 进程单独确认。

## Evidence integrity

- `capture_metrics.json` 保存坐标换算、C 参数/腕点、层级及输入工具/生产资产的 SHA-256。
- `hair_purity_strict.txt` 保存图像 QA 的实际 stdout 与 exit code。
- `IMAGE_SHA256.json` 保存本目录 PNG 的 SHA-256/字节数；目录级 `SHA256SUMS.txt` 在本文件落盘后生成。
