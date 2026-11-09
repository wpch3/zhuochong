# Chibi 额外失败试验与连续袖网格诊断（2026-11-06）

**状态：仍不通过视觉验收；不是正式 rig，也不能交真机验收。** 本记录接续 `CHIBI_EXTENDED_REPAIR_AND_TOOLING_2026-11-06.md`，描述的是当时的试验，后续工作和引擎新增的独立 opt-in 见 `CHIBI_CONTOUR_AND_LAYER_STUDIES_2026-11-06.md`。所有帧来自 C 预览；采样和技术测试均不证明连续参数空间、视觉质量或 Windows 实机通过。原正式资源没有采用下面的试验；当时默认引擎没有加入这些眼线补丁。

## 眼线：按同一斜坡淡出也不够

隔离的引擎补丁按闭眼、笑眼或痛眼各自的进入斜坡来退出旧闭眼线，并用 `zrig_xfade_hidden` 降低透明间隙；标记仅打在候选闭眼和笑眼层。72 帧依旧逐只眼、单个 smile/pain 的 3 个值 × 6 眨眼值；**没有覆盖 smile 和 pain 同时存在**。0.5 强度全眨眼灰线明显改善（`experiments/live2d_chibi_extended/qa/weighted_study/eye_smile_05.png`），但 0.85 痛眼 + 全眨眼的两套轮廓并不重合，形成灰色重影（`eye_pain_ghost.png`）。因此拒绝此方案，不能只用数值上的 alpha 覆盖率做视觉通过判断。应考虑绘制/插值一条连续闭眼轮廓及表情优先级，另外测双表情和双眼组合；不得仅靠淡化压掉症状。瞳孔 0.65 附近仍无瞳，未在此轮修复。

失败补丁归档在 `experiments/live2d_chibi_extended/rejected/aligned_eye/engine.patch`，**默认引擎不包含它**。以下在 build 中编译另一份二进制，不覆盖正常引擎；路径必须是新目录：

```sh
make build/zhuochong_preview
mkdir -p build/rejected-eye-source/src/core
cp src/core/zrig.c build/rejected-eye-source/src/core/zrig.c
patch -p1 -d build/rejected-eye-source < experiments/live2d_chibi_extended/rejected/aligned_eye/engine.patch
cc -std=c11 -O2 -Wall -Wextra -Wno-unused-parameter -pthread -Isrc -Isrc/core \
  -o build/zhuochong_eye_rejected src/headless/main_headless.c \
  $(find src/core -maxdepth 1 -name '*.c' ! -name zrig.c | sort) \
  build/rejected-eye-source/src/core/zrig.c -lm -pthread -ldl
/home/user/.imgenv/bin/python tools/build_chibi_aligned_eye_study.py build/eye-aligned-repro
/home/user/.imgenv/bin/python tools/capture_chibi_expression_blink.py build/eye-aligned-repro build/eye-aligned-repro-qa --preview-executable build/zhuochong_eye_rejected
```

复现时已对照 3 张首次试验 PNG 逐像素一致。未打补丁的引擎会忽略该可选标记，不能用默认二进制声称复现了改动。

## 指间：整体平移仍失败

保留原始拆件、拇指旋转不动，仅把其余四根指组从旋转改为镜像的刚性 x/y 平移；分别试 1.2、2、3 画布像素，2 的每手 32 端点、两种底色从 C 渲染并核对参数。2 像素示例 `qa/weighted_study/finger_slide_L_01010.png` 中指根和轮廓出现不自然断离/融合，依然不是解决方案。不是通过降低动作幅度或更换刚体变换就能补齐指缝；下一步需要重新设计手掌与指根遮挡、重画并配置连续变形，再采中间态和双手组合。原 1024 个双手二值组合以及连续空间依旧没有完整覆盖。

```sh
/home/user/.imgenv/bin/python tools/build_chibi_finger_slide_study.py build/finger-slide-repro --distance 2
/home/user/.imgenv/bin/python tools/capture_chibi_finger_endpoints.py build/finger-slide-repro build/finger-slide-repro-qa
```

正式复现的左右、深浅四张端点表与首次 2 像素试验逐像素一致；该脚本明确标为失败，仅作负对照。

## 袖管：连续网格候选有进步，但不能合并

用压力 rig 原上袖、前袖合成的透明纹理生成一张 8×16 连续网格，肩旋转仍为刚体、肘关节通过单个 `chain_w` 从 0 渐变到 1（默认过渡半宽 45 画布像素），腕和袖口仍走原来的组。压力测试仍是肩 ±12°、肘 ±20°、腕 ±15°，**不是批准活动范围**。48 固定姿势和 20 帧扫动已采；`qa/weighted_study/L_joint_mix_0_light.png` 相对旧 `qa/stress_L_joint_mix_0_light.png`，外侧旧切边小尖角在该例中消失，部分方向看起来更连续。然而：

- 内侧仍有尖角/露缝，`L_joint_mix_7_dark.png` 等仍需逐帧重画检查；图中手部模糊、轮廓问题仍存在。
- 合成原本位于不同层的袖片，统一为 layer 21，与身体的前后遮挡不是原来的逻辑。中立身体裁图的浅色 RGB 放大截图相对压力基线有 **197 个不同像素**（截取 `(290,450,730,720)` 后用 Pillow 默认重采样放大三倍，不能将该计数解释为实际画布像素）；网格采样、层序等都可能影响差异，不能声称中立逐像素等价。
- 当前引擎中形变链位于 group 变换外侧，而原组链为父包子；身体倾斜/呼吸叠加时两者次序不一致，存在错位风险。当时矩阵采 16 个选定的单侧肩/肘/腕与 `ParamMotionDrive=±1`、`ParamBreath=1` 组合及中立，共 17 帧；之后脚本扩展为 32 个单侧端点组合及中立，详见后续记录。两者均非全部双侧或连续范围。`L_body_base.png` 与 `L_body_weighted.png` 给出同一姿势对照，但未把图差直接认定为单一原因。
- 原引擎 `chain_w` 不是通用多骨蒙皮：一条链仅允许一个带权节点，层序、子件与父组坐标耦合、扭曲及 UV 仍需单独处理。现有 rig 编辑器不能交互绘制该权重，也不支持完整多骨蒙皮，不能宣称 Live2D Cubism 完整等价。

```sh
/home/user/.imgenv/bin/python tools/build_chibi_joint_stress.py build/stress-repro
/home/user/.imgenv/bin/python tools/build_chibi_weighted_sleeve_study.py build/weighted-repro --band 45
/home/user/.imgenv/bin/python tools/capture_chibi_visual_matrix.py build/weighted-repro build/weighted-repro-qa
/home/user/.imgenv/bin/python tools/capture_chibi_body_joint_matrix.py build/stress-repro build/stress-body-qa
/home/user/.imgenv/bin/python tools/capture_chibi_body_joint_matrix.py build/weighted-repro build/weighted-body-qa
make test-chibi-weighted-sleeve-study
```

此构建器经过新目录和软链越界保护；测试覆盖候选权重长度/范围、左右关节 C 帧响应和归零、显式选择 C 可执行文件以及 `.zproj` 打包/还原帧一致，**不判定画面好坏**。动作和身体组合实际采样时查询 API 核对各参数；截图放大显示会截掉超出裁图区域的肢体，不能据此判定截断。

## 工具链增量与未完成项

`preview_live2d_chibi.py` 与表情矩阵新增显式可执行文件选择，支持在不替换默认 C 程序的情况下运行隔离 A/B；默认行为保持原样。新增身体叠关节采样脚本、可复现的两个失败试验和连续袖研究构建器；`make test-chibi-weighted-sleeve-study` 同时检查这些试验的结构、失败标识、安全路径，以及显式二进制和包往返。实验编辑器的既有组/关键点和浏览器+C 测试重新通过，尚无动态 C 主画布、权重绘制、任意 UV、完整作者工程等功能；仍需按 `EXTENDED_AUTHORING_WORKFLOW_2026-11-06.md` 和上份缺陷记录推进，不能把 rig+PNG 包当作完整 PSD/Cubism 作者工程。

继续工作顺序：独立设计指根遮挡和真实可变形的指部美术；解决眼线轮廓插值及表情共存；为袖网格实现和验证与身体组一致的变换及正确的前后层遮挡，检查腕袖交界并采双向大角/身体叠加；再扩大组合、连续扫动、尺度与真机验证。上述任一阻塞未解决前不应要求用户验收。
