# 原手部矢量的高分辨率采样试验（失败，2026-11-06）

**结果：不通过；不作为指根或整体视觉修复，不接入生产。** 此试验针对内收姿势下手指模糊，验证“矢量切件先以 2 倍分辨率栅格化能否改善采样”；不是新手型、不改变指根拓扑或遮挡关系。与之前平移、变形和增大截图不同：它重新渲染既有 SVG，而不是放大现有 PNG；仍不能解决前后顺序和根部融合。

`tools/build_chibi_hires_hand_study.py` 在隔离分层袖 stress rig 基础上，将原左、右独立手部 SVG（右食指使用既有单独修订图）按 960×1024 栅格化，12 个手掌/手指部件按 0.5 缩放；维持原坐标、组、层序和参数。源码 SHA 在 `qa/occlusion_probe_4/hires_build_report.json`；它的 `visual_acceptance` 为构建时的 `not evaluated`，本记录依据实际渲染作出失败结论。并不代表 2 倍纹理能避开引擎内部再次滤波；像素不保证中立完全一致。

使用真实 C 对候选采 33 身体姿势和左右各 32 种二值手指端点；基线同样采集。本人打开 `hires_hand_body_comparison.png`（左基线、右候选，原 RGBA 帧合成浅背景后等比最近邻 3 倍）、`baseline_L_01010.png`、`hires_L_01010.png`、`hires_R_10101.png`。结果：中立和外伸手均略有边缘采样变化；双侧内收靠裙子时手指仍明显发虚、线条不能辨清，交错姿势的指根仍融合。不能通过视觉验收，不能归因于单一已证根因，更不能据此继续仅提高分辨率反复试。正式屏幕尺度、其他姿势、动画和深色背景尚未完成目视复审。

身体采样前后候选 rig、46 个引用 PNG 和可执行文件哈希一致，见 `hires_body_provenance.json`；基线 `layered_body_provenance.json`。64 个端点清单 `hires_endpoint_poses.json` 只有采前 rig/二进制哈希（该采集器尚未接入资源前后哈希）；即使它的 rig 哈希与身体采样一致，也不能事后声称端点采集前有完整 PNG/环境哈希。两类哈希均不锁住所有配置和系统环境。

技术检查：`make test-chibi-hires-hand-study` 验证部件尺寸/半缩放/原组绑定、安全目的地、隔离 C 参数响应和 `.zproj` 校验/解包帧往返；并非视觉通过。整体 `make test` 本轮 2707/0，example_mod 热加载跳过；Windows 真机和长期运行未执行。

复现（要求 Pillow、numpy、resvg-py 和 `build/zhuochong_preview`）：

```sh
/home/user/.imgenv/bin/python tools/build_chibi_hires_hand_study.py build/hires-hand-repro
/home/user/.imgenv/bin/python tools/capture_chibi_body_joint_matrix.py build/hires-hand-repro build/hires-hand-repro-body
/home/user/.imgenv/bin/python tools/capture_chibi_finger_endpoints.py build/hires-hand-repro build/hires-hand-repro-fingers
```

下一步应先定位实际旋转下单件采样与多层遮挡、线条重叠各自的贡献，并设计新连接与遮挡结构；不能把重栅格化失败推广成所有分辨率、所有渲染器均无效。
