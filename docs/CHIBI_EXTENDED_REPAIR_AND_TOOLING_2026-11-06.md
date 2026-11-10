# Chibi 扩展修复与工具链核查（进行中，尚不能真机验收）

用户要求先修复手指融合、半眨偏空、袖口/袖侧线，再检查更大肩肘腕角度、表情叠眨眼与全部手指组合；只有自查无阻塞问题后才交用户真机。**本轮未达该门槛**，不覆盖正式模型、旧候选，也不把技术结果当视觉通过。

## 本轮实际结果

### 半眨眼：试验性改善，仍需复核

在隔离候选中将虹膜本体与瞳孔／高光拆层；二者同一眼眶遮罩和视线组，瞳孔细节增加开度驱动的单轴 keyform：睁眼与近闭回到原位、半眨相对本体下移 10 像素。0.5 闭合比旧版更能看到瞳孔，0.85 的已采帧未重新出现蓝边；但 0.65 瞳孔又几乎消失，过渡仍简化，睁眼细节拆层可能有微小像素变化。采用的是独立试验，尚不声称美术通过。

`qa/blink_*_compare.png` 为旧／新真实 C 帧；`auto_blink_slow.gif` 为真实自动眨眼逐步采样慢放（100ms/样本，并非真实速度），数值在旁边 JSON。采了额外的左右横向视线、头倾和笑眼叠加；本 rig 仍没有上下视线。

### 手指与袖口：阻塞未清除

- 两次独立试验均拒绝：把指线独立置于填色上方，交错时出现多余重叠线；把手指扇开并做细长形，静止手形过于细长，依然不能可靠解决交错遮挡。保留 `qa/rejected_*` 与 `rejected/`，最终试验候选沿用旧手图、原 ±5° 小摆幅，**不冒称手指已修好**。
- 对每只手单独采了全部 32 个二值端点，共 64 帧，五位顺序是小指、无名指、中指、食指、拇指，0 表示 -1、1 表示 +1；`qa/L_dark_endpoints.png`、`R_dark_endpoints.png` 和参数 JSON 可复核。多处指间仍融合。**没有**跑完双手同时的 2¹⁰ = 1024 个端点，更不可能通过有限采样覆盖连续参数的全部组合；目前连单手端点已有失败，应先修画再扩展验证。
- 上轮腕补片内缩后已采小角度组合的袖外肤色尖点不再明显，但细黑线和袖侧切线仍未最终修复。其余袖管结构在大角度下出现明显突角，不能只靠少量隐藏补片宣称通过。

### 大角度、表情与眨眼：发现新阻塞

- 新建**纯压力测试副本**，肩 ±12°、肘 ±20°、腕 ±15°（不是正式允许范围）；两侧各 8 个肩肘腕端点组合，附交错指姿、20 帧同步插值以及浅深底。`qa/stress_L_joint_mix_0_light.png` 可见肘/袖边突片，`qa/stress_L_joint_mix_7_dark.png` 与其他组合有尖锐切线和形变不自然。原素材不支持这些角度，不能扩大正式范围。
- 72 帧表情矩阵：左右、笑眼/痛苦眼、强度 0.5/0.85/1 × 眨眼 0/0.25/0.5/0.75/0.85/1。`qa/L_Smile_sheet.png`、`qa/L_Pain_sheet.png` 等可见某些强度的表情与全闭叠加时眼线变灰／重影（例如 `L_Smile_0.5_1.png`）。引擎现有闭眼线按表情强度抑制，但表情线直到强度 0.75 之后才淡入，留下视觉缺口；需要设计一致的叠加权重或可编辑差分图并逐帧检查，**本轮未修改通用引擎**。
- 阶段结论：尚未满足「自查确认没有问题」；不要求用户真机验收，也不将失败压力测试或试验眼睛晋升正式模型。

## 必备工具链盘点：不完整，新增一段但不是完工

- **画稿与遮挡**：SVG/PNG 分层与独立补画构建脚本、`tools/underpaint_editor/` 原型存在；缺完整分层作者工程、PSD 导入、可扩角度的高质量肩肘腕和指根原画。
- **自研骨骼与绑定**：`tools/rig_editor/` 过去能改位置、给已有组绑参数，但不能创建骨骼/连接部件。本轮补了数值创建组、设置枢轴和父组、非 socket 部件挂组，父组必须先于子组声明，防循环及超限，支持撤销/重做和导出副本。真实 Chromium 交互导出后送入真实 C，驱动新组中的部件并恢复原帧；具体操作见工具 README。仍缺骨线显示、拖动枢轴、姿态保持重父化、复杂网格权重/UV 编辑和真实 C 实时画布，不是完整建模器。
- **引擎与包**：自研 C 支持组链、参数和单轴形变；`tools/zrig_project.py` 只打包运行 rig + PNG，不包含 PSD/源稿、历史、外部动作/表情或完整作者工程，也不是 `.moc3/.cmo3`。本轮试验 49 文件工程包往返帧一致。
- **验证与发行**：有独立构建、C 抓帧、表情/手指矩阵、浏览器、包及自动化测试；缺连续姿态全面人工审查、性能长稳、完整真机与跨平台发行验证。预览无认证，只用于可信环境，不放私人数据。

查阅 [3](https://docs.live2d.com/en/cubism-editor-manual/skinning/) 理解旋转变形器、连接及参数范围需要一起检查；另查 [2](https://docs.live2d.com/4.2/en/cubism-editor-manual/keyform-parent-chilid-relation/) 理解分层父子变形对组合数量的影响。这里只借鉴概念，未复制官方代码，本工具不是 Cubism。

## 复现与后续闸门

```sh
make build/zhuochong_preview
/home/user/.imgenv/bin/python tools/build_chibi_extended.py build/my-extended
/home/user/.imgenv/bin/python tools/capture_chibi_finger_endpoints.py build/my-extended build/my-fingers
/home/user/.imgenv/bin/python tools/capture_chibi_expression_blink.py build/my-extended build/my-expression-blink
/home/user/.imgenv/bin/python tools/capture_chibi_art_review.py build/my-extended build/my-full-review --auto
/home/user/.imgenv/bin/python tools/build_chibi_joint_stress.py build/my-joint-stress
/home/user/.imgenv/bin/python tools/capture_chibi_visual_matrix.py build/my-joint-stress build/my-stress-qa
make test-chibi-extended test-chibi-visual-review test-rig-editor test-zrig-project
```

输出目录必须为 `build/` 下尚不存在的新目录；`--auto` 等待一次真实眨眼，可耗时数分钟。真实浏览器测试另需 README 中的 Playwright / Chromium 依赖。此次 `make test` 2684 通过、0 失败（示例模块热加载跳过），网页测试 266/0；`test-chibi-extended`、`test-chibi-visual-review`、`test-rig-editor`、`test-rig-editor-browser`、`test-zrig-project`、动态控件专项和 5261 真实浏览器控件检查通过；未跑两万帧 soak 或 Windows 真机。

后续顺序：①重画适合各指运动的指根和层序（必要时用差分姿态，而不是只缩幅）；②解决眼睑/表情的连续权重及半眨视觉；③按更大角度重新补画并分层袖管与肩腕；④重新抓所有单指端点、双手端点及中间插值、较大角度和表情组合，逐帧查图、缩放/背景/动作测试；⑤工具和工程包缺口逐项补齐并端到端验证；⑥仅在阻塞问题清除、自查通过后邀请用户真机验收。有限测试永远不证明连续参数空间毫无瑕疵。
