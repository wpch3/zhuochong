# Chibi 手指、口腔与眼睑：隔离绑定试验

状态：**未完成，未通过美术验收**。这是自研 zrig/C 引擎的独立试验，不是官方 Cubism 模型；没有覆盖少女、桌宠或既有 Chibi。旧关节限制见 `CHIBI_JOINT_FACE_ART_2026-11-06.md`。本轮把可编辑图保留在 `experiments/live2d_chibi_binding_art/`，构建结果只放 `build/`（不入库）。

## 制作与绑定

- `fingers.svg` 的五指和掌心分别栅格化，左右手各有五个部件；各指组继承相应腕组，`ParamFinger{L,R}{Little,Ring,Middle,Index,Thumb}` 限制在 -1～1，各自约 ±5°。手掌接袖及隐藏指根仍是草稿。`finger_test` 是轻微交错的循环试验，不是握拳。
- `mouth.svg` 分为口腔、舌、上唇、下唇、牙齿高光五层，同一 `ParamMouthOpenY` 驱动五张 4×4 网格的闭/开关键形态；0～0.2 由原闭嘴线过渡到新分层，非 A/I/U/E/O 音素绑定。图层一开始来自先前嘴草稿，已经接入 C 预览，但不可声称口型制作完成。
- 另有**独立的** `eyelids.svg` 试验：`build_chibi_lid_art.py` 基于重绘眼白虹膜的肩肘腕候选，将眼睑拆成移动层，眼白和虹膜共用随 blink 收缩的遮罩。它没有合并进手指口腔候选，以免把未通过的两个试验冒充完整模型。遮罩锚点是贴图尺寸比例，不是像素；用 `[0,105/114]` 配 `[x,391]`。早期写 105 导致整个眼白消失。
- 动态面板仅在 binding 报告存在时启用十指滑块；动作按钮调用 `finger_test`。默认旧面板不增加手指控件。预览是无认证测试服务，不应放入私人数据或密钥。

## 实际目视检查

真实 C 渲染抓图保存在 `experiments/live2d_chibi_binding_art/qa/`（浅底、放大 3 倍）：

- 手指各自确实改变画面，但几根像平行条纹，拇指与掌连接偏尖；左右镜像且手形扁平。肩肘腕组合图仍可见袖口轮廓和衣身接缝的不自然处；手指在多姿态的遮挡补画不足。
- 口型 0 保留旧笑线，0.25/0.5/1 能看到张口过程；0.1 嘴角有淡化双线与变形接缝。第一版直接交叉淡化全程重影，第二版统一缩放让闭嘴变水平红线；第三版网格闭口存在碎线；现试验把旧笑线短暂淡出并采用相同网格，仍未修完。
- 眼睑 0/0.5/0.92/1 已实际观察：半闭眼不再与睁眼完全相同，但睫毛较粗且像整条机械滑动，下眼周有残点和浅线，眼睛重绘改变原貌；完全闭眼的线形不自然。仍需重新分离头发、皮肤、上下睫毛并画闭眼关键形态及表情，而非靠测试数字宣称平滑。

`metrics.json` 是回归用的像素变化量，不是艺术质量评分：十指单独变化 49～218 像素，肩肘腕指组合 16575，嘴开合 779，手指循环两帧 970。独立眼睑半闭和全闭相对于睁眼分别变化 4280、6766 像素；抓图不涵盖所有缩放/动作/表情。

## 重建及检查

需要 Pillow、numpy、resvg-py 0.5.0，先 `make build/zhuochong_preview`。以下输出必须是 `build/` 下**尚不存在**的独立目录：

```sh
python tools/build_chibi_binding_art.py build/chibi-binding-repro
python tools/capture_chibi_binding_art.py build/chibi-binding-repro build/chibi-binding-repro-qa
python tools/preview_live2d_chibi.py --dynamic --dynamic-study build/chibi-binding-repro --preview-root build/chibi-binding-repro-preview 5238
# 另开终端或另选端口：眼睑与手口是两个独立候选
python tools/build_chibi_lid_art.py build/chibi-lid-repro
python tools/capture_chibi_binding_art.py build/chibi-lid-repro build/chibi-lid-repro-qa
python tools/preview_live2d_chibi.py --dynamic --dynamic-study build/chibi-lid-repro --preview-root build/chibi-lid-repro-preview 5239
make test-chibi-binding-art
node tests/test_dynamic_study_ui.js
```

可用装有 `playwright-core` 和 `@sparticuz/chromium` 的环境，在手口预览启动后运行 `node tests/test_chibi_binding_browser.js`；本轮真实 Chromium 测了左右指滑块、肘滑块、复位和循环动作。安全路径、源素材不变、十指及眼睑 C 帧、两个 `.zproj` 验证解包和 C 帧往返通过。新包只含 rig 和被引用图片，不含可编辑 SVG。相关肩肘腕、衣身、动态、编辑器、项目包、动作 API 回归通过；`make test` 2646 通过、0 失败，示例模块热加载跳过，长稳未运行；旧正式 Chibi 仍有 3 条加载警告。Windows 真机未测。

## 下一阶段

先重绘非镜像自然手型和完整指根，试更小的指间距/关键形态并检查所有旋转方向；再用真实上下唇和口角形状代替短暂双线淡化，做多个开度与音素。眼睑需要皮肤遮盖与下沿补画并处理闭眼表情。随后在隔离候选中合并眼口手，检查深浅底、多缩放、肩肘腕和语音/表情组合、完整动作循环，人工认可后再考虑合入正式资源。

参考：[Live2D 分层说明](https://docs.live2d.com/4.2/en/cubism-editor-tutorials/psd/)、[口型表情教程](https://docs.live2d.com/en/cubism-editor-tutorials/expression/)、[A/I/U/E/O 口型](https://docs.live2d.com/en/cubism-editor-tutorials/mouth-aiueo/)、[关节重叠绘制参考](https://en.esotericsoftware.com/blog/How-to-cut-your-assets-for-animation)。这些是设计参考，不代表格式或运行时与官方兼容。
