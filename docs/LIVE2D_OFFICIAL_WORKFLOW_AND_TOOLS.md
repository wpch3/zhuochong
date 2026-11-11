# Live2D 官方工序与自制工具清单（2026-11-10 查证）

## 官方标准工序（Cubism Editor 口径）
来源：Live2D 官方教程/手册（docs.live2d.com）与 Cubism Cookbook 基本工作流。

1. **分层原画（PSD）**：全身设定先行，各部件独立图层、遮挡区补画完整（对应铁律 7/9）。
2. **导入与 ArtMesh**：PSD 导入 → 每部件生成/手修网格（三角剖分，睫毛/眉/嘴等小件手修）。
3. **纹理图集（Texture Atlas）**：合并贴图、重建图集。
4. **剪贴蒙版**：虹膜裁进眼白等 clipping。
5. **变形器层级**：Warp Deformer（形变）+ Rotation Deformer（旋转）父子层级，先建层级后绑参数；Skinning 处理发束等连续体。
6. **参数与关键帧（Keyforms）**：标准参数（角度 XYZ、眼开闭/笑、眉、口开闭/形、身体、呼吸等）在 -1/0/1 等键位做形。
7. **物理（Physics）**：摆链输入参数→输出参数，头发/耳/尾/裙摆。
8. **动作与表情**：Animation 工作区做 motion、口型同步（唇形从音频）、表情 exp3；随机动作压力测试。
9. **导出嵌入数据**：`.moc3` + `.model3.json` + 纹理 png + `.physics3.json` + `.motion3.json` + `.exp3.json`（Viewer 里再配 pose/命中区）。真 Cubism 身份门见铁律 16——自研 `zrig/rig.json` 只是类比实现，不冒称 Cubism。
参考：官方 Deformer 教程 https://docs.live2d.com/en/cubism-editor-tutorials/deformer/ ；Toolbar https://docs.live2d.com/4.2/en/cubism-editor-manual/toolbar/ ；Skinning https://docs.live2d.com/en/cubism-editor-manual/skinning/ ；导出 https://docs.live2d.com/en/cubism-editor-manual/export-moc3-motion3-files/ ；Viewer https://docs.live2d.com/en/cubism-editor-manual/cubism3-viewer-for-ow/

## 本次复习后的原画/建模门禁（纠正首轮误区）

### 学习来源与界限

- 官方 [Cubism PSD illustration preparation / PSD import tutorial](https://docs.live2d.com/en/cubism-editor-tutorials/psd/)：要先准备语义正确、层级清晰的分层原画与遮挡区域，再导入 Cubism；不能把扁平图的任意多边形抠片当作完整的 Live2D source art。需要逐件在编辑器中核对导入结果和图层顺序。
- 官方 [Deformer tutorial](https://docs.live2d.com/en/cubism-editor-tutorials/deformer/)：变形器和参数建在可用、完整的部件原画上；变形器不是修复缺失像素或替代隐藏区补画的方法。
- 官方 [FREE vs PRO comparison](https://www.live2d.com/en/cubism/comparison/) 与 [SDK release license](https://www.live2d.com/en/sdk/license/)：编辑器能力/商业使用及 SDK/Core 的授权需分别查，不把 Cubism 泛称开源或默认免费。
- 官方 GitHub [`Live2D/CubismNativeSamples`](https://github.com/Live2D/CubismNativeSamples) README 明确它是**显示由 Cubism Editor 输出模型的应用样例**，依赖 Native Framework 和不包含在该仓库的专有 Cubism Core；它不是原画教程，也不能用来伪造 Editor 工程或 `.moc3`。其 LICENSE 也分别列出 Components、Core 与样例模型授权边界。

### 变成实际制作前的逐项检查

1. **来源定位**：所有新件从选定 v1.1 的已注册坐标截取或手绘；对照带坐标的原图近景，不能靠猜中心点/多边形后只看整张拼合图。
2. **部件归属**：每个可动件都先定义语义和遮挡顺序（例如刘海/眼睛/眼睑/虹膜/高光），逐像素近看选区；跨在部件上的头发等须明确所有者，不能混入眼睛片里就当拆好了。
3. **隐藏内容**：扁平参考没有提供遮住的像素；会露出的皮肤、头发、衣物、肢体必须由人工绘制完整 underdraw，不能把 OpenCV inpaint 当成成品。
4. **拼合与边缘**：分层可见/隐藏对照，检查 100% 与放大视图、浅/深棋盘底和代表性偏移；静态拼合像素差只是诊断，不是视觉验收。眉眼/嘴这类细小件需要专门的局部检查板。
5. **文件格式边界**：ORA 可供阶段编辑和审查，但不是 Cubism 可导入 PSD/PSB 的替代证明。最终源稿要在官方 Editor 实际导入并检查，然后才可开始 ArtMesh、Warp/Rotation hierarchy、keyforms、physics 和 expressions/motions。
6. **正式验收边界**：保存 `.cmo3` 项目，按官方导出流程输出并在 Viewer/授权 SDK 中运行；只有真实 Editor、导出文件和动态目视记录齐全后才称 Cubism 交付。

### 对 pass 01 的复盘与修正

第一次切脸失败的关键原因不是 Live2D 工具本身，而是制作流程不符合上述门禁：坐标是粗猜、没有先检查切出的透明 PNG，眼眉偏到发束区域，鼻嘴切成大块皮肤，并将重建指标误当作足够的结构检查。本次新建 pass 02 而保留且标记 pass 01 为 superseded；对照原图坐标放大图重新放置眉眼，并将鼻/嘴收紧为暗色笔画。第二版仍只是源像素 cutout + 插值底图，不是手绘完成件，也不准进入变形生产。自动差异 80px/max50 比旧版 67px/max41 更大，因此只报告事实，不宣称质量提升。

## 官方工具 → 我们自制对应（zrig 体系，不抄代码、学思路）
| 官方工具/概念 | 本项目自制对应 | 状态 |
|---|---|---|
| PSD 分层拆件 | `tools/prepare_sprites.py`+`make_*_parts.py`+`rebuild_parts.sh`（27步） | ✅ 已有，Chibi 已跑通新一轮 |
| ArtMesh 网格编辑器 | `zrig` 网格形变（deformers）+ 待建可视化网格检查工具 | 🟡 有渲染、无编辑器；先做检查器 |
| Warp/Rotation Deformer 层级 | `rig.json deformers/groups` + 新工具 `tools/live2d_rig_inspect.py`（骨骼/变形器树检查） | ✅ 本轮新增检查器；可视化编辑器待建 |
| 参数面板/关键帧 | `rig.json params/actions` + 预览 `/api/param` 滑杆（测试台） | ✅ 可调参预览 |
| 物理设置 | `rig.json physics/physics2` + `zphys2` | ✅ 已有，参数待按新件复核 |
| 动作/表情制作 | `motions/*.motion3.json`、`expressions/*.exp3.json` 导入 | ✅ 已有通道 |
| Texture Atlas | sprites 独立 PNG + @2x（`make_hires_sprites.py`） | 🟡 无图集打包，桌宠规模可接受，后续评估 |
| Viewer/预览 | C 引擎 headless 预览（5173/5175）动态帧+参数 API | ✅ |
| 导出 moc3 | 无（铁律16：需官方 Editor，不自制冒充） | ⛔ 不做假导出 |

## 参考项目（查思路，已在 docs/REFERENCE_NOTES.md 登记）
BongoCat(C/SDL) https://github.com/vladelaina/BongoCat ；BongoCat(Rust/Live2D) https://github.com/ayangweb/BongoCat ；ds-local-pet https://github.com/QCYTSN/ds-local-pet ；VPet https://github.com/LorisYounger/VPet ；airi https://github.com/moeru-ai/airi ；CubismWebFramework https://github.com/Live2D/CubismWebFramework（Core 专有不引入）。

## 下一步工具建设计划（按依赖）
1. `live2d_rig_inspect.py` 骨骼树/变形器/物理链检查（本轮）→ 2. 网格线框预览（preview 加 bones/wireframe 已有基础则复核）→ 3. 参数关键帧矩阵截图工具（替代已死的 capture_chibi_*，直连 preview API，不依赖缺失模块）→ 4. PSD 分层导出工具（把 sprites 按层导出为可导入 Editor 的分层包，为真 Cubism 留门）。
