
## 第六十七批（第五十八问：帧率标准与灵动感口径，2026-10-24）

**帧率标准**
- <https://docs.live2d.com/en/cubism-editor-manual/physics-operation/> ⇒ 物理「Calculate FPS」
  可选 15/30/60/120；*"the default value of 60 fps is recommended"*；
  **自 Cubism 5.0 beta1 起默认值由 30 改为 60**。改这个值会改变物理输出结果。
- <https://github.com/DenchiSoft/VTubeStudio/wiki/Lag-Troubleshooting> ⇒
  *"Generally, it's recommended to always run VTS at 60 FPS."*
- <https://github.com/DenchiSoft/VTubeStudio/wiki/Record-Animations> ⇒
  VTS 动画一律按 **60-FPS-based curves** 导出。
- <https://github.com/DenchiSoft/VTubeStudio/wiki/NVIDIA-Webcam-Tracker> ⇒ ★
  VTS 把 tracking 数据**插值到 60fps**，30fps 与 60fps 的摄像头看不出差别。
  **输入帧率 ≠ 渲染帧率**，低速输入靠插值也能很顺 —— T63.4 的依据。
- <https://live2d.pavostudio.com/doc/en-us/pc/optimization/> ⇒ Live2DViewerEX 默认 60fps，
  降到 30 省约一半 CPU。
- <https://www.reddit.com/r/Live2D/comments/1atccb3/> ⇒ ⚠ 物理按 30fps 调好的模型
  跑在"跟随 App 帧率"下，动作和编辑器里**不一致**。物理帧率要和创作时一致。

**灵动感口径（★ 最重要的一篇）**
- <https://sites.google.com/cybernoids.jp/cubism2/editor/animator/technic/quality-up> ⇒
  Live2D 官方《クオリティアップのヒント》。四条原话：
  ①「顔の動きを単体でつけるのではなく、体のX・Zも顔の動きに合わせてつける
     —— 顔だけ振り向くとロボットのように見えます」
  ②「顔XYZと体XYZを**慣性を意識してタイミングをずらす**
     —— 顔と体がまったく同じタイミングで動くと、やはりロボットのように見えます」
  ③「顔を振り向くことで体が後からついてくる」
  ④「**反動、ブレーキを付ける** —— 人間はピタッと瞬時に動きをとめることができません」
  ⇒ T63.1 直接照这两条做，验收口径也抄它。
- <https://d-gear.biz/column/8573> ⇒「動きが単調に見える場合は、**呼吸、髪、目線、
  まばたきの周期を少しずつずらします**。全部が同じ周期で動くと、機械的な印象に」；
  又「表情と体の動きが同じタイミングで動きすぎると落ち着かないため、少しずらして」
  ⇒ T63.2 / T63.3 的依据。
- <https://note.com/hatyati/n/n00534a9ff2f5> ⇒「呼吸のように毎回同じ動きを
  アイドリングモーションで動かしていては、**すぐに目が慣れてしまい魅力を感じなくなる**」；
  该作者把翅膀全交给物理演算而非固定动作，并与口角/眨眼联动。
- <https://shiroikarasu.net/live2d-blink-lipsync-setting-guide-2026> ⇒ 自动眨眼
  **间隔要有随机性**，否则机械；不自然的两个原因＝间隔太固定、闭合速度不对。
- <https://cgbox.jp/2019/07/25/live2d-memoto/> ⇒「**人の眼球は静止していることはありません**」
  ⇒ 瞳要常微动（saccade），但过头会显得慌张；视线移动时**睫毛要一起动**。
- <https://note.com/ryodist/n/nd15bac2226d3> ⇒ 待機モーションは**複数作ってランダム再生**。
- <https://juku.live2dcs.jp/en/course/course-45/> ⇒ Live2D 官方塾《物理演算テクニック》：
  プルプル瞳の揺れ / 腕の揺れ / **呼吸に合わせたアイドリングの揺れ** / 全身を richer にする裏技。
- <https://cgbox.jp/2020/12/18/live2d-breath-react/> ⇒ 把**呼吸当物理演算的输入**，
  输出到想摇的部件：「手付だと付けにくい微量の揺れが出せる」。
- <https://ugoiraman.com/live2dkokyuu/>、<https://surume1ka.com/archives/2242> ⇒
  呼吸＝胸上抬并横向扩张、肩背微动；**大きくしすぎると不自然、少しだけ**。

## T67.9 兜帽内侧投影（2026-10-31）

- 夏水かなた，《Supplementary Guide for Live2D Part Separation (For Illustrators)》：
  <https://note.com/kanata_natsumi/n/n7f96b96b6e26?hl=en>。已阅读全文。与本任务相关的分层原则：
  发丝阴影应独立拆件；阴影素材可超出最终剪影以便遮罩裁切；被帽兜遮挡的头发背面需补齐，
  否则运动时会露空。它关于 Multiply 的说明针对发旋层，不是兜帽投影的规范，故本项目不把它
  当作“兜帽必须乘算”的外部规定。
- 参考路径：Live2D Creative Studio 官方账号 X 的搜索摘要提及反转遮罩可构造投影：
  <https://x.com/iyosuke_114/status/1601113044351754240>；尚未打开原帖，记作后续线索，
  不作为已核实的技术要求。kawase 的帽兜拆件漫画搜索摘要提及帽下发可遮罩裁切、内衬可作遮罩：
  <https://twiman.net/user/1554022262030073856/1707235392003645704>；同样未核读原文。
- 本项目实施是设计选择：从已登记的短发兜帽切片按内沿追踪柔化投影，独立成柔 alpha 附件，
  只在 teen `hood_pose=up` 显示，以 `multiply` 混合，挂 `socket_head_top` 随帽与头部运动；
  参考切片及真实渲染证据见 `docs/qa/live2d_teen_hood_inner_shadow_detail_2026-10-31.png`。
  状态切换验收必须先查 `/api/info.json`，再抓帧；曾出现文件名标为 up/down、实际两张都戴帽的误存，
  已废弃该批截图并重拍。

## 第六十八批（第六十六问：Chibi 资料充分性与缺口检索，2026-11-02）

**结论**：引擎/网格/遮罩/动作方法资料够继续自研；Chibi 专属视觉真值不足，特别是独立 `small/mitten` 手件稿、全身差分板及跨“手型×手势×腕角×服装”验收。完整报告：`docs/memory/CHIBI_LIVE2D_REFERENCE_AUDIT_2026-11-02.md`。

- <https://github.com/Live2D/CubismNativeSamples>：用于对照 model3/moc3/physics3/pose3/motion3 装配；LICENSE 区分 Open Software、Cubism Core proprietary 和模型各自条款，样例图不自动可复用。
- <https://github.com/Inochi2D/inochi-creator> / <https://github.com/Inochi2D/inochi2d>：BSD-2-Clause；PSD、自动网格、网格编辑工作流可比较，不迁移实现/格式。
- <https://github.com/zeikar/iki>：MIT、检索时 early-stage；读 `packages/editor/AUTO-RIG.md`、README、插件说明。可借鉴 rig-plan/report、测量、越界 clamp/refusal、artist/critic 复核；不复制代码、提示词或角色图。
- <https://github.com/umamoorg/umamo>：GPL-3.0、alpha；仅在备份副本学习 UI 工作流，不并入项目或作为稳定依赖。

检索词为 `live2d`、`Live2D SDK`、`2D puppet animation/rigging`、`chibi Live2D`。未找到许可清晰且风格匹配、可直接作为小寻 Chibi 手件的素材。落实：以 Chibi 自有 design sheet/body_full/anchors 为真值，先画整身与手型差分板，拆件后将 `hand_style` 与 wrist angle、open/heart gesture 分轴；按状态矩阵在真实 C 引擎验收。

## 第六十九批（T70.2 腕口接缝拟合方法复核，2026-11-02）

**本次查到的方法不是“手画一条 cuff 边”，而是按领域分工：** Chibi `body_full` 是视觉真值；Live2D 分层/切件资料提供“手腕插入袖口、上层遮住接缝”的结构原则；最后在源图像素和放大预览中核对。没有把外部角色图或教材示例直接当小寻手稿。

- **Live2D 官方：Create Motion with Pose Switching**，<https://docs.live2d.com/en/cubism-editor-manual/change-pose/>。官方说明切换用的手臂/部件必须分层；对交叠纹理先减少显眼交叠区、软化交叠边，并可把部件设为约 50% 不透明度检查突出接缝。适用于后续 `small ↔ mitten` 切换与层级检查；该页不规定 Chibi 手型，也不证明当前 WIP 已适用于动作。
- **社区插画/建模教程：ミミシーム《How to Make a Kemono Live2D Model… Part 4 – Arms and Hands》**，<https://note.com/mikischine/n/nd7dc931e4c4b?hl=en>（2026-08-28，本文自述是个人示例）。文中分层顺序包含 hand / forearm / sleeve / upper arm / sleeve inside，腕处用前臂圆端与相应手件切口组织连接；这只作为“前后层与腕端应配套”的结构思路，不采用其兽耳角色画稿/PSD/形状，不等同小寻 Chibi 的视觉真值或授权生产资产。
- **补充社区分层说明：夏水かなた《Supplementary Guide for Live2D Part Separation (For Illustrators)》**，<https://note.com/kanata_natsumi/n/n7f96b96b6e26?hl=en>。本文明确是作者个人偏好，且引用官方分层手册；适用原则是被遮住的部件仍补足填色与线稿，以免运动露洞。这里只用于遮挡完整性，不把其示例图作 Chibi 手型素材。
- **本项目落地与边界**：旧拟合脚本的硬编码 8 点边在放大图中与左右源 cuff 轮廓不一致，已在隔离研究中改为由 Chibi `body_full` teal + 中性乳白条纹连通区域取 sleeve/cuff mask，保存原袖口像素；从实际 `small` 手部肤色区域量 bbox 作等比缩放/位置拟合；AI 手在 cuff 下重叠，仅清理 cuff 邻域里的重复 AI 腕线。脚本 `docs/qa/chibi_candidate_2026-11-02/hand_style_study_2026-11-02/fit_mitten_source_cuff_trial.py`，证据 `mitten_cuff_seam_detail_wip.png` 与 `source_cuff_mask_diagnostic_wip.png`。
- **观察/判定**：本人已看 8× seam detail 和全身板：源袖口条纹/轮廓连续，旧重复腕线减少，静止图未见明显透明缺口；仍有轻微暖色腕影与线稿细节密度差异。候选仍是未批准的 AI 来源手型，动态/C 引擎 seam 未测，未接生产。任何后续认可都须先过艺术风格/左右形状复核，再做独立手件与真实 C 渲染。
