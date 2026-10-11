# 参考项目笔记（六个地址 + 实际查阅结论）

> 用户明确要求：遇到问题先去这六个项目的源码里查，不能只看摘要，也不能凭猜测下结论；
> 六个项目解决不了再上网查资料，并记录来源；**不把参考项目源码整体复制进仓库**（AGPL 的尤其只学思路）。
>
> 六个地址见下表。前四个＋第二个 BongoCat 在旧交接文件第二节也有记录。

| # | 项目 | 地址 | 许可 | 本项目实际用到/将用到什么 |
| --- | --- | --- | --- | --- |
| 1 | BongoCat（C + SDL3 + OpenGL） | https://github.com/vladelaina/BongoCat | AGPL-3.0 | 原生透明窗与渲染思路、托盘与品牌图标一致性、"鼠标穿透开/关"开关。**只学思路，不复制代码**（AGPL）。 |
| 2 | BongoCat（Rust + Live2D + 全局输入） | https://github.com/ayangweb/BongoCat | Apache-2.0 | 全局键鼠钩子驱动的反应、动作可重叠播放（优先级表达）、各平台权限流程。第三步做全局输入时参考。 |
| 3 | ds-local-pet（PySide6） | https://github.com/QCYTSN/ds-local-pet | MIT | **已在用**：动作状态机语义（优先级/可中断/过期回退）、`GetLastInputInfo` 空闲检测、素材与代码授权分离。 |
| 4 | VPet（WPF） | https://github.com/LorisYounger/VPet | Apache-2.0 | 桌宠交互语汇：拖动、点击反应、右键菜单、托盘、缩放贴合窗口、触摸分区（头部 30% 摸头）。 |
| 5 | airi（Web + Live2D/VRM） | https://github.com/moeru-ai/airi | MIT | 实时语音四段结构（STT 端点 → turn → 打断 barge-in → 口型）、供应商适配层、多渲染后端舞台抽象。第五步做语音时参考。 |
| 6 | Live2D CubismWebFramework | https://github.com/Live2D/CubismWebFramework | Live2D Open Software License（Cubism Core 为专有，**不引入**） | **已在用**：眨眼状态机的五态时序。注意：年营收超 1000 万日元商用需按 Cubism SDK Release License 取得授权；本项目不引入 Cubism Core，只按公开做法自己实现参数动画。 |

## 实际查阅记录（可复核）

### 1) 眨眼状态机 —— CubismWebFramework `src/effect/cubismeyeblink.ts`
读了源码中的 `setBlinkingSetting(closing, closed, opening)` 与 `updateParameters()` 的状态分支，
确认五态：`EyeStateFirst → EyeStateInterval → EyeStateClosing → EyeStateClosed → EyeStateOpening`。
默认时序（闭合 / 保持 / 睁开）与"间隔随机"的处理方式，被移植为 `src/core/zrig.c` 里的
`blink_update()`（同时也是 `blink` 配置段的字段含义）。

### 2) 动作状态机 —— ds-local-pet `animation/state_machine.py`
读了 `ActionStateMachine.request()` 的判定顺序：
```
if not force:
    if not current.interruptible and candidate.priority <= current.priority: return None
    if candidate.priority < current.priority: return None
```
以及 `update()` 里"到期后进入 `_queued_after` 或 `spec.return_state`"的逻辑。
本项目把它翻写成 C（`src/core/zsm.c` 的 `zsm_request()` / `zsm_update()`），并保留
"同一状态重复请求不重置计时、`force` 可重播"的行为（用于摸头连击与唤醒）。

### 3) 空闲检测 —— ds-local-pet `awareness/idle_detector.py`
`GetLastInputInfo` + `GetTickCount` 求差值、并按 32 位环绕取模（`& 0xFFFFFFFF`）。
C 版见 `src/win32/zw32.c` 主循环里的 `LASTINPUTINFO` 段：差值转秒后交给 `zpet_report_idle()`，
由 `src/core/zpet.c` 判断"超过 90 秒 → sleep、任何输入 → 唤醒"。

### 4) 交互语汇 —— VPet（WPF）
参考其"拖动 / 点击反应 / 右键菜单 / 托盘 / 触摸分区"的组织方式：
- 头部区域 → 摸头，身体 → 抚摸，脚部 → 惊讶（本项目的 `regions` 与 `zpet_poke()`）；
- 拖动 vs 点击用系统拖拽阈值区分（`SM_CXDRAG`），避免"想点一下却把窗口拖走"。
（VPet 为 WPF/C#，本项目为 C/Win32，只借鉴交互定义，不复制代码。）

### 5) 托盘图标与角色一致 —— BongoCat（vladelaina）
该项目的托盘图标与角色形象保持一致。本项目实现为：**从当前帧实时生成 HICON**
（`icon_from_pet()`，32px/16px 各一份，换形态后自动刷新），因此不需要额外维护一套图标文件。

### 6) 透明窗与穿透 —— 综合结论
- 透明：`WS_EX_LAYERED` + `UpdateLayeredWindow(ULW_ALPHA)`，每帧直接推 RGBA（预乘），无需 GDI 双缓。
- 穿透：**不是**整个窗口开 `WS_EX_TRANSPARENT`，而是在 `WM_NCHITTEST` 里用角色 alpha 判定，
  透明处返回 `HTTRANSPARENT`，让鼠标事件落到下面的窗口；这与用户在旧交接文件里的要求一致
  （"角色以外的区域不拦截鼠标"），同时保留"整窗穿透"作为托盘开关（BongoCat 的开关思路）。

## 未决 / 待查（下一步做对应功能前先查这六个项目）
- 全局键鼠钩子：Windows 的 `WH_KEYBOARD_LL` / `RawInput` 取舍与权限流程 → 参考 #2。
- 语音打断（barge-in）与端点检测 → 参考 #5。
- 网格形变（mesh warp）做脸/身体平滑弯曲 → 参考 #6 的参数与形变管线（不用 Cubism Core）。

---

## 拉取与查阅记录（2026-10-11 第二轮：七个项目全部落地）

拉取脚本：`bash scripts/fetch_references.sh`（只查阅，不入库；用完 `clean_references.sh` 删除）
实际目录：`~/.cache/zc-refs/`

| 项目 | 大小 | 本轮实际查验的内容（可复核） |
| --- | --- | --- |
| bongocat-sdl | 11M | 原生透明窗与托盘思路（AGPL，只学思路不复制） |
| bongocat-tauri | 21M | 全局输入钩子与动作重叠播放 |
| ds-local-pet | 210M | 已在用：`animation/state_machine.py`、`awareness/idle_detector.py` |
| vpet | 1.8G | **模组化证据**：`VPet-Simulator.Windows.Interface/Mod/IModInfo.cs`（第三方 Mod 接口）、`Function/CoreMOD.cs`、`VPet.Solution/Models/ModLoader.cs`（Mod 装载）→ 验证"部件/服装可插拔"的工程做法 |
| airi | 948M | **语音流水线证据**：`packages/pipelines-audio/src/speech-pipeline.ts`、`managers/playback-manager.ts`、`llm-streaming-control/`、`timeline.ts`；barge/interrupt 出现在 speech-pipeline 与 playback-manager → 打断与播放队列按此结构实现 |
| cubism-web-fw | 1.4M | **部件与渲染证据**：`src/rendering/cubismrenderer_webgl.ts` 的 `drawMeshWebGL(model, index)`（每个可绘制对象 = 一个网格 + 独立绘制序号）、`cubismclippingmanager.ts`（遮罩/裁剪）、`src/cubismdefaultparameterid.ts`（`ParamAngleX` 等标准参数命名） |
| photocraft | 54M | **图层与选区证据**：`crates/algo/src/selection.rs`、`selection_blur.rs`、`crates/engine/`（图层引擎与填充图层测试）、`assets/icons/layer-mask.svg` → 素材精修（蒙版/选区/图层）参考 |

### 结论一：Live2D 是不是"单独做独立部件"？
**是。** 源码层面的结构是：
1. **每个部件 = 一个独立网格（mesh）**：顶点、三角形索引、UV、绘制序号（`drawMeshWebGL(model, index)` 逐个绘制，顺序由模型决定）；
2. **部件内部还有网格细分级别的形变单元**（deformer 层级：父级旋转/弯曲 → 子级网格 warp），参数（`ParamAngleX` 等）驱动层级逐级变形；
3. **遮罩（clipping）单独管理**（眼睛裁剪、刘海遮罩），与部件绑定；
4. 因此"能不能自然弯曲"取决于**拆件时每个部件是否自带网格**，而不是引擎算法多高级。

本项目的等价实现（已落地，代码可查）：
- 部件独立拆分 + 层级（rig.json 的 groups/parts/layer）＝ 第 1、2 点的简化；
- **`zimg_draw_warp`（逐像素平滑形变）**＝ 网格形变的连续等价实现（无分段接缝）；
- **`bend_x`/`bend_y` 通道 + curve（root/sine/linear）+ strips** ＝ 参数驱动形变；
- 尚缺"部件内细分网格（多控制点）"与"顶点级遮罩"，已列入 `PRODUCT_PLAN.md` 缺口（T12.6）。

### 结论二：本地与云端的分工（"AI 模仿动漫角色唱歌"）
- 那些视频用的是 **歌声转换（SVC）**：So-VITS-SVC / RVC 训练目标音色，再把歌声转成该音色；或 DiffSinger 直接合成歌声。**本地完全可以跑**（GPU 4–8 GB），云端只是算力替代。
- **合规红线不变**：不能克隆真人声音、不能拿商业角色音源训练（见 `docs/TRAINING.md` 第六节）。
- "小寻会唱歌"的正确路线：用自己的音色模型 → TTS 唱句 + 音高对齐，或用 SVC 转换自有录音。见 `TRAINING.md` 第十节。
