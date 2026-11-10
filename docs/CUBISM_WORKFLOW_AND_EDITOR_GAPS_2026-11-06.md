# 2D 立绘制作流程、Cubism 纠偏与本项目差距（2026-11-06）

## 边界

小寻现有少女是自研 C 引擎 `zrig` + PNG，不是官方 Cubism `.cmo3` / `.moc3`，也没有官方运行包与 Viewer/SDK 验证。自研作者工具/运行时和官方 Cubism 编辑/导出是**两条路线**。名称、参数或数学类似不意味着官方格式兼容。不是需要 Cubism 才能做 2D 模型，但若要求真正的 Cubism 产物，应在合法授权下使用官方工具链并做官方加载验证。见 `docs/LIVE2D_CONFORMANCE.md` 顶部纠正。

## 对用户所列流程的修正

- 「四角合成自动实现 360°」不正确。官方的四角是从已有上下左右角度关键形态生成 X/Y 对角形态，结果通常还要人工修整；2D 面片不能凭插值还原背面或被遮挡的真实信息。常说的“九点”一般指 X/Y 各三档组成的 3×3 关键形态，不是九根空间轴。Z 通常是画面内歪头，X/Y 如何定义以目标参数约定为准。实际可动角度取决于分层、补画和关键形态，不应承诺 360°。[官方四角教程](https://docs.live2d.com/en/cubism-editor-manual/synthesize-corners/)
- 每个眼/口需要拆到什么程度由动作质量和设计决定，不是所有模型都必须照固定清单拆；层名也不强制英文，但稳定唯一 ID、命名映射和编码检查有利工具链。拆件须含背景下补画、保持可编辑分层源和授权记录。
- PSD 中一层可成为供 ArtMesh 使用的源素材，但并非简单保证“一层必定一个 ArtMesh”；可能需要同素材多网格或一层合并处理。Cubism 导入 PSD 有 sRGB、透明度、遮罩/剪贴与图层属性等限制，应按版本检查，不要假设所有 PSD 特性都可原样带入。[PSD 注意事项](https://docs.live2d.com/en/cubism-editor-manual/precautions-for-psd-data/)、[源图及参考图](https://docs.live2d.com/en/cubism-editor-manual/original-picture/)
- Mesh 常用三角形，但密度要按轮廓、关节和局部变形权衡，不是越密越好；检查退化、翻面、UV 与纹理图集边界。[手工网格](https://docs.live2d.com/en/cubism-editor-manual/mesh-edit-manual/)
- `.moc3` 是官方运行模型数据；`.model3.json` 描述资源关联；纹理图集是图片；`.physics3.json`、动作、表情等是依需求配置的独立资源，并非每个模型都必备。可选 `.motion3.json`、`.exp3.json`、`.pose3.json`、`.cdi3.json` 等；版本与运行环境须匹配。[官方嵌入数据](https://docs.live2d.com/4.2/en/cubism-editor-manual/export-moc3-motion3-files/)
- 应用通过 SDK/Core 的 API 给模型设置参数并更新绘制，不是摄像头直接向文件发命令。面捕识别、滤波、坐标/左右眼映射、口型及权限是独立模块。[官方 Native SDK](https://docs.live2d.com/en/cubism-sdk-manual/cubism-sdk-for-native/)

## 补全的制作与验收步骤

1. **设计与权限**：锁定版本、色板、比例、发型/兜帽/手型组合、来源授权；桌宠 Q 与 Live2D Chibi 分开验收。
2. **原画与拆件**：统一画布和坐标；按运动与遮挡设计 PSD/等价分层源，分别画眼白/瞳孔/睫毛、上下眼睑、口内/嘴线及各部件需要的遮挡补画。检查边缘、笔触、阴影、切线、遮挡前后顺序和左右约定；记录失败候选和来源，不以自动抠出的隐藏像素冒充原画。
3. **资产导入**：保留层名、可见性、混合模式、坐标、尺寸、色彩与 alpha 语义，校验不支持的图层特性；重导入时做稳定 ID/关联迁移和变更备份。
4. **网格与遮罩**：对每张贴图划网格、UV、顶点/三角索引；编辑、自动网格、贴图布局/留边；验证自交、反面、纹理溢出，测试眼球眼眶、头发/衣服及多层遮挡；需要时做连接/粘合（glue）或专门的接缝处理。[纹理图集](https://docs.live2d.com/en/cubism-editor-manual/texture-atlas-edit/)、[Glue](https://docs.live2d.com/en/cubism-editor-manual/glue/)
5. **层级与参数**：建旋转/弯曲变形器父子树、原点、绑定；设置参数范围/默认值和关键形态（含角度 X/Y 的组合）、插值与遮罩/绘制顺序。目视检查上下左右、斜角、闭眼+转头、张嘴+表情等组合的极值与中间态，避免撕裂和穿帮。[官方制作总流程](https://docs.live2d.com/en/cubism-editor-manual/workflow/)
6. **表情、动作、物理**：设置眨眼、口型和表情叠加顺序；制作待机、动作、过渡以及发/衣/饰物惯性；验证暂停/帧率/不同时间步、参数上下限、碰撞与边缘，不因单一周期摆动而冒充真实物理。
7. **导出/运行验证**：对自研格式验证资源路径、版本、透明/混合、纹理、性能与内存；对官方 Cubism 路线用官方 Editor 导出对应版本资产并用 Viewer 或 SDK/Core 真机加载。将图片差分、动画录屏、问题与人工审批分开记录。
8. **维护**：工程/素材版本控制、撤销与快照、参数/部件重命名迁移、可重现构建、损坏文件恢复、插件边界与供应链许可；在 Windows 真机与目标显示缩放下验证，不以无头单元测试替代视觉验收。

## 当前少女（Teen）的可核实缺口

- 当前 `characters/xiaoxun/forms/teen/rig.json` 含 112 个部件、15 个组、86 个 JSON 参数、55 个形变器、32 个 `physics`、5 个 `physics2`、26 个动作、9 个表情（静态计数，只证明声明，不证明质量）。它比本轮 Chibi 试装复杂得多；`forms.json` 的 `ready` 仅表示可加载，旧注释中“Live2D 合规”不能视为官方 Cubism 认证。
- 确认的严重缺陷：长发 + 戴兜帽时 `hair_hood_long@2x.png` 的袖/手遮挡烘入及隐藏区缺画，动态抬手可能露洞或残留；历史局部设计均未通过目视门。扁平源不存在隐藏部位真值，需要新设计/人工补画并按隔离审查→用户确认→C 动作测试→另行批准生产的顺序处理，不重试既拒绝的几何补丁。证据：`docs/T67_71_HANDOFF_CURRENT_2026-11-05.md`。
- 历史 2026-10-31 少女目视报告还记录了长发横向断口/透明碎边、双马尾和马尾根部接缝，以及若干动作中双臂接近直线、踮脚视觉难确认等问题；该报告的隔离截图原在 `/tmp`，本轮未重做同一套测试，因此这些是**待复核历史发现**，不能直接断言所有症状仍然存在或已修复。见 `docs/qa/CHIBI_Teen_visual_audit_20261031.md` 的 Teen 部分。
- 模型没有官方 `.cmo3`、`.moc3`、正式 `.model3.json` 资源包与官方 Viewer/SDK 加载证据。现有 C `rig.json` 及 PNG 并不能证明可在 Cubism 中编辑或运行。
- 当前仓库静态自检仍有正式 teen/chibi 生成器指纹过期和 ROADMAP/TASKS 计数不一致两项失败；不应盲目重生成正式 rig。2026-11-06 没有 Windows 真机验收。可加载、参数像素变化、或旧文档“通过”都不能代替对少女各发型、手臂、角度组合、过渡和实际画质逐项复审。除上述明确缺陷以外，未逐项实测的地方标为**待查**，不虚报缺件。

## 可参考的源码与许可（实际查询时间 2026-11-06）

- [Inochi Creator](https://github.com/Inochi2D/inochi-creator/tree/dba60811cff224f8cc9ce367b1d9291bfa5f7640)，项目仓库标注 BSD-2-Clause；所查 [PSD 导入](https://github.com/Inochi2D/inochi-creator/blob/dba60811cff224f8cc9ce367b1d9291bfa5f7640/source/creator/io/psd.d) 维护组层级、可见性、混合模式；[参数动作](https://github.com/Inochi2D/inochi-creator/blob/dba60811cff224f8cc9ce367b1d9291bfa5f7640/source/creator/actions/parameter.d) 使用可撤销动作与驱动关联；[自动网格接口](https://github.com/Inochi2D/inochi-creator/blob/dba60811cff224f8cc9ce367b1d9291bfa5f7640/source/creator/viewport/common/automesh/automesh.d) 分离算法与配置。仅研究思路；若将来复制代码、依赖或商标，先复核具体组件及其授权、保留版权声明，不能假设素材与商标都随源码许可。
- [Live2D Native Framework](https://github.com/Live2D/CubismNativeFramework/tree/45de21229a9faab9675525bc59deddbe089b0e95) 的 [物理实现](https://github.com/Live2D/CubismNativeFramework/blob/45de21229a9faab9675525bc59deddbe089b0e95/src/Physics/CubismPhysics.cpp) 声明 Live2D Open Software License；官方文档明确 Core 是专有组件、未公开在 GitHub（见上 Native SDK 链接）。不能把 Framework 的公开源码当作 Core、MOC3 编辑器源码或随意再分发核心的授权；具体许可与商业条件以官方当时版本为准。本项目未复制源码、未集成官方 Core。

## 自研工具现状与顺序

- **已有**：`src/core/zrig.c` 有组、参数、形变器、物理及 PNG 渲染等自研能力；`src/core/zmod.c` / `zmod.h` 有动态模组 ABI（加载本机代码并非安全沙箱）；`web/components/rig.js` 是运行时调试面板，不是作者编辑器。
- **本轮原型**：`tools/rig_editor/` 可本地导入 JSON、编辑部件位置和组绑定、撤销重做及导出副本；`tests/test_rig_editor_integration.py` 用真实 C 渲染验证导出绑定。仅是文本/数值级原型，没有画布/网格/PSD/物理编辑，不能称完整插件、编辑器或绑定器。
- **后续交付顺序**：① 新建带唯一 ID 的安全工程格式与完整测试、纹理导入和图层画布；② 可视化网格/UV/遮罩及图集校验；③ 参数滑块、多轴 keyform、变形器树、绑定与动画时间线；④ 物理调参、角色组合 QA、真实渲染预览及错误恢复；⑤ 定义版本化插件 SDK、示例和完整生命周期、授权/能力边界、异常隔离与安全策略，再做跨平台与 Windows 真机测试。上述均为未完成项，先做自研 `.zrig`，不能许诺导出官方私有二进制。
