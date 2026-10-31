
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
