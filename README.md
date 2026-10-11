# zhuochong（桌宠）

拟人化桌面 AI 伴侣：**Windows 原生 C 桌宠** + （后续）Web 主工作区。

## 现状（2026-10-11）

- ✅ Windows 原生 C 桌宠可运行：透明小窗、像素级鼠标穿透、拖动、托盘菜单、缩放、热键、
  动作状态机、眨眼、摸头/抚摸/锤击、空闲 90 秒入睡。
- ✅ 动态立绘引擎（数据驱动）：`characters/<角色>/forms/<形态>/rig.json` 描述图层、骨骼组、
  动作通道、交互区域；换角色/换形态/换服装/加动作都**不需要改 C 代码**。
- ✅ 配置全部可自定义 + JSON Schema 校验，出错会明确指出“文件 + 行 + 字段 + 原因”。
- ✅ 96 项单元测试全绿；`scripts/selfcheck_all.sh` 一键自检。
- ✅ 沙箱预览服务（用同一套 C 引擎渲染）：`make preview` → http://localhost:5173
- ⬜ 二次元风格 UI、7 个 AI 角色 × 4 形态 × 多服装、Web 工作区/API/语音/社交（按用户指示排后）。

## 快速开始

```bash
make test      # 单元测试（[测试锁]）
make preview   # 本地预览（C 引擎实时渲染）
make win       # 交叉编译 Windows exe → dist/windows/x86_64/zhuochong.exe
bash scripts/selfcheck_all.sh   # 一键自检（必须全绿）
```

Windows 使用：把 `dist/windows/zhuochong/`（`make pack-win` 生成）整个目录拷到 Windows，
双击 `zhuochong.exe`。托盘右键或角色上右键可切换形态/服装/动作/缩放，`Ctrl+Alt+T` 切换整窗穿透。

## 文档

| 文件 | 内容 |
| --- | --- |
| `docs/PROJECT_SPEC.md` | **当前有效规格**：已做到什么、角色与色卡、可自定义清单、验收口径 |
| `docs/HANDOVER.md` | 交接：给下一个代理的入口（含六个参考项目地址与查询方法） |
| `docs/REFERENCE_NOTES.md` | 六个参考项目地址、许可、实际查阅结论（可复核到具体文件） |
| `docs/ROADMAP.md` | 下一步：素材拆件、UI、7 角色 4 形态、语音/社交、Web 工作区 |
| `HANDOVER_RESTART (1).md` | 旧交接文件（历史上的角色方向 B 已舍弃，技术教程部分仍有效） |

## 许可

本项目原创代码。第三方仅 `src/third_party/stb_image.h`（MIT / Public Domain）。
参考项目只学思路不复制代码，见 `docs/REFERENCE_NOTES.md`。
