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
