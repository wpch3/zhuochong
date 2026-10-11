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
