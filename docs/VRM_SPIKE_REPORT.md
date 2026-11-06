# VRM/VRChat 可行性 spike：源码与架构预审

日期：2026-10-24 ｜ 任务：P1.12 ｜ 状态：**部分完成（源码/架构预审）；没有做模型加载实测**。

## 1. 本仓库现状（已核对）

- 当前桌宠主线是 C11/Win32，Makefile 说明零外部依赖；核心 `zrig` 将各部件按 layer 进行 CPU RGBA 合成，`zimg` 提供 RGBA8 像素缓冲/仿射绘制；Win32 `zw32.c` 再转换成分层窗口所需像素格式并显示。
- 当前 rig 是图片部件 + group/pivot + 通道曲线；没有现成 GPU 3D 场景、三维骨架、mesh skinning、VRM/glTF loader、PBR/MToon material、blendshape runtime 或 SpringBone runtime。
- 因而 VRM 若进入主进程，不是添加一个 `.vrm` 文件解析器就完事；需要 3D renderer、材质、骨骼/表情、摄像机/灯光、物理和资源生命周期，并会增加依赖/体积/测试范围。
- **本次只读检查，没有改 C、Win32、rig、角色素材或构建依赖。**

## 2. 开源路线核查

- `vrm-c/UniVRM`：MIT；面向 Unity 的 VRM/glTF 标准实现，支持 VRM 0.x/1.0、glTF 2.0、VRMA。适合 Unity 导入/导出；不能直接插入当前 C11 renderer。
- `pixiv/three-vrm`：MIT；Three.js/WebGL 的 VRM loader/runtime，适合独立本地浏览器页面验证文件加载、表情等功能。选它意味着多一套 JS/Three.js runtime；若继续零依赖 Windows C 主程序，不能直接当主窗口插件。
- `VRMConverterForVRChat`：MPL-2.0 的社区 Unity 编辑器工具，公开功能为 VRM prefab 与 VRChat avatar 之间转换/网格合并；依赖 UniVRM 与 VRChat SDK 系列。它能辅助合法源文件转换，不代表可直接加载/上传任意 VRChat avatar。
- VRChat 官方 avatar 流程以 Unity + VRChat SDK 构建；VRChat SDK有独立许可。用户需拥有/获准使用模型源文件，不能把平台上传的 Avatar 当成可随意下载/再利用的模型包。

参考链接：
- https://github.com/vrm-c/UniVRM
- https://github.com/pixiv/three-vrm
- https://github.com/esperecyan/VRMConverterForVRChat
- https://creators.vrchat.com/avatars/creating-your-first-avatar/
- https://hello.vrchat.com/legal/sdk

## 3. 建议决策

1. **现在不做 3D 主程序集成**：保持现有 2D/Live2D 路径、包体与启动方式不变。
2. 若用户未来批准做验证，先把浏览器/WebGL 预览放在隔离目录或独立预览进程，按 `TASK_TEMPLATE.md` 上限短时验证；不要合入主窗口、不要默认安装运行时。
3. 只有独立预览有明确用户价值后，才讨论两种后续路线：保持 2D C 主程序并外接独立 3D 预览；或另立 3D renderer 后端/进程。**当前不建议**为了“兼容 VRChat”引入 Unity/VRC SDK 到主产品。
4. VRChat 兼容限定为用户拥有权利的模型源文件和清楚标注的可转换功能子集；VRChat 上传 Avatar、Unity prefab、平台专属组件/Shader/PhysBones/Contacts/Animator 等不纳入“直接支持”承诺。

## 4. 尚未验证/阻塞

- 未加载任何真实 `.vrm` 文件；VRM 0.x 与 1.0、材质、表情、眨眼、物理和授权元数据支持状态尚未在本项目实测。
- 未做 Windows GPU/内存/帧率/高 DPI/休眠恢复的 3D benchmark。
- 未测试 VRM 转 VRChat 的 Unity 工程/SDK版本矩阵、转换后 PhysBone/Expressions/Quest-PC等功能。
- 做实际加载测试需要可合法使用且可本地测试的 VRM 样例；当前不因缺少样例而下载或提交来历/许可证不明的角色模型。

## 5. 收尾口径

本次 P1.12 **仅完成只读架构与开源库预审**，未达到“本地 VRM 能显示”的验收条件，因此保持 `[~]`，不标完成。后续是否开始隔离预览、是否提供模型样例，由用户决定；无论如何不影响当前 Live2D。