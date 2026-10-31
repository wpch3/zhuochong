# docs/qa —— **验收证据**（入库）

## 为什么要有这个目录

`logs/` 在 `.gitignore` 里（第 11 行：`logs/`），所以放在 `logs/asset_qa/` 下的证据图
**从来没有进过库**。2026-10-26 工作区被还原、本地未跟踪文件全部丢失，才发现
"我在 JOURNAL 里写了『证据图已随提交入库』"是**假的** —— 那些图一张都没提交。

于是定一条规矩：

| 目录 | 用途 | 入不入库 |
|---|---|---|
| `logs/` | **一次性草稿**：调参中间产物、随手截图、试跑输出 | 不入（可随时丢） |
| `docs/qa/` | **验收证据**：任何"已修 / 已达标"的结论所依赖的图与数据 | **必须入** |

判据很简单：**如果删掉它，某个结论就无法复核** → 它就属于 `docs/qa/`。

## 现在这里有什么

- `sprite_audit_teen.json` —— 素材体检基线（T67.2）。`selfcheck` 与 `make audit-sprites`
  都以它为基准；它是"重画前后只许降不许升"的那个"前"。
- `live2d_mask_intersection_2026-10-31.png` —— 引擎用两个错位矩形遮罩真实渲染的像素图；只露出交叠区，作为 T67.8 多遮罩交集证据。
- `live2d_teen_eye_clipping_2026-10-31.png` —— teen 真实 rig 睁眼 / 半闭 / 闭眼渲染；核对眼眶 mask 继续贴合，不出界。
- `live2d_teen_hairstyle_hood_matrix_2026-10-31.png` —— teen 真实 rig 四种发型（短发 / 长发 / 双马尾 / 高马尾）× 兜帽戴/不戴静帧回归。
- `live2d_teen_cheek_paramcheek_ab_2026-10-31.png` —— Teen 真实渲染 ParamCheek=0/1 放大对照；用于确认降峰值、去斜线后腮红随参数平滑出现。
- `live2d_teen_cheek_paramcheek_on_2026-10-31.png` —— ParamCheek=1 全身静帧；核对腮红在整身尺度不过浓、不像贴纸。
- `live2d_teen_mouthform_corner_full_abc_2026-10-31.png` —— teen 真实引擎全身 ParamMouthForm −1/0/+1；检查整身状态无副作用。
- `live2d_teen_mouthform_corner_closed_detail_abc_2026-10-31.png` —— 同一真实帧的闭口嘴部放大；检查笑形抬角、怒形压角、中心不漂。
- `live2d_teen_mouthform_corner_open_detail_abc_2026-10-31.png` —— ParamMouthOpenY=0.65 下 Form −1/0/+1；检查口内与开口遮罩同步、不露接缝。
- `t67_*.png` —— 2026-10-26 这一轮各条结论的对照图（长发换源头前后、两腿间薄片归属、
  尾巴四档可见性、体检误报现场……）。文件名里的 `t67_NN` 对应 `docs/memory/TASKS.md` 的任务号。
