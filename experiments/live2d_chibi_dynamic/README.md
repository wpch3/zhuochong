# 无兽 Chibi 动态绑定试装（独立实验，不是正式模型）

这是 `live2d_chibi_human_blackline_seam` 的隔离派生，不替换桌宠、少女、有兽 Chibi 或先前无兽试装。自研 C 运行时读取 `rig.json` 和 PNG，**不是** Live2D Cubism 的 CMO3/MOC3，也不是完整的官方工具链。

## 当前可用

- 从原身体平面图按人工多边形分离两侧袖手：下半部通过原图 alpha 连通域保留完整手指，并独立设置肩部旋转组。手臂只允许约 ±2° 的小摆动，以避免第一版大洞。
- 新增头部平移、倾斜、躯干小摆、轻微呼吸、左右袖手、原有眨眼和嘴型，以及待机、摆动、袖手轻摆、倾头、说话、静止检查。头部是二维整层运动，不是三维转头；眼睛没有独立眼球/瞳孔跟踪。
- `physics2` 由身体摆动驱动袖子参数，真实 C 求值并经冲击/回稳测试。输出经过限幅，视觉上是微小的衣袖跟随，不是精细布料模拟。
- 动态预览右侧提供参数滑块；拖动自动进入静止检查以防动作通道覆盖输入。动作按钮恢复循环；“静止并复位”将参数归零。表情面板可以眨眼/张嘴。

## 重建、预览、验证

需要 Python 3、Pillow 和 numpy；工程已有不含这些库的默认 Python 时，请明确指定相应解释器。不能在正式模型目录运行覆盖操作。

```sh
# 仅重建本目录的 rig、报告及素材；会检查固定的来源 rig/body 哈希。
python tools/build_dynamic_chibi.py
make build/zhuochong_preview
python3 tools/preview_live2d_chibi.py --dynamic 5209
# 访问预览的 5209 端口；通过 Arena 的 LIVE PREVIEW 或本地浏览器访问。
make test-dynamic-chibi
# 已启动动态预览时，抓真实 C 帧并检查参数、动作及物理（会短暂改变预览状态）：
python tools/capture_dynamic_chibi.py
# 可选：同时启动 --seam 5207，加入 C 中立帧对照：
python tools/capture_dynamic_chibi.py --baseline-port 5207
python3 tools/zrig_project.py create experiments/live2d_chibi_dynamic/rig.json build/dynamic-chibi.zproj
python3 tools/zrig_project.py verify build/dynamic-chibi.zproj
```

`make test-dynamic-chibi` 在临时目录启动独立 C 服务，验证构建可复现、源不变、默认素材逐像素合成、动作通道、帧变化、回零和物理回稳，不依赖用户正在看的预览。QA 在 `qa/`：PNG 为真实 C 帧，`*_detail.png` 是该帧背景合成后放大裁切；`metrics.json` 是一次验证记录。可选浏览器测试需安装 `playwright-core`、`@sparticuz/chromium` 和其系统库，再对运行中的 5209 执行 `node tests/test_dynamic_chibi_browser.js`。

## 目视结果与未通过项

1. 第一版 ±5° 造成腋侧、袖口、手指的明显断裂：袖口部分和右手拇指留在身体层，背景露出长缝。经放大目视后**未作为最终试装保留**。
2. 当前连通域修正手指、限制旋转，并在身体背后用相邻身体颜色延展了 4674 个窄带像素：这是程序合成的遮挡试验，**不是真实手绘隐藏底稿**。中立和 ±2° 的浅/深底 C 帧、两侧局部与动作序列已目视；缺口明显减轻，但腋侧/外套边仍有不自然接缝和局部颜色拉伸，原发梢有少许紫色毛边。不能通过高品质验收或进入正式模型。
3. PNG 三层在中立位重新合成与原身体图 RGBA 逐像素一致；但 563×563 实际 C 帧与旧试装相比仍有 **301 个像素不同**，集中在分层边缘。不能把源素材合成一致误称为 C 渲染逐像素一致。
4. 严格视觉完成需要可编辑的头发、眼白/虹膜、独立上臂与前臂、衣身和肩部遮挡原画及手绘隐藏区；应重新制作素材、网格、权重和关键形态，再检验大动作与组合。当前只有小幅 2D 层变换、差分、以及少量物理，既不是完整 Live2D 模型，也不是完整建模器。
5. 预览服务无认证，绑定 `0.0.0.0` 供沙箱代理访问，不要将个人数据或密钥放入该预览。Windows AMD64 交叉编译通过但有两条未使用参数警告，桌面 Windows 真机未验证。正式少女素材与旧正式 rig 的既有全量自检问题仍未解决。
