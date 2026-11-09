# Chibi 近闭、手形与关节遮挡继续试验

这是基于 `CHIBI_ART_REVIEW_2026-11-06.md` 的独立候选，不覆盖正式模型或上一轮候选。下面的观察基于真实 C 预览截图；**技术检查不等于美术验收**。

## 近闭蓝边

- 保留上一轮快速收口遮罩与不提前淡出；只将左右虹膜 `eyelid_travel` 从 -5 改为 -9，让虹膜更早被遮罩/眼线收住。0.8、0.85 固定图在本次中轴和左右视线采样中不再看到上一版的蓝色窄边；0.75 仍有蓝色小弧，消失过程偏快、几何仍简化。这是参数试调，不是严格的轮廓相切证明。
- 实测过 -7、-9、-11、-13，另试延迟移动方案；例如 -12 加 `lash_hold=.5` 虽能收住近闭，0.5 半眨时虹膜底部被裁成平边，因此未采用。最终 -9 半眨保留了圆润下沿，但瞳孔在半眨阶段仍被遮得较多，实际观感请审看慢放及交互预览。
- 自动眨眼从 C 模型逐步抓取 21 个闭合值，`qa/auto_blink_slow.gif` 以每样本 100ms 慢放，不代表实际速度，GIF 合并了重复图；数值在 `qa/auto_blink_values.json`。笑眼叠加、左右眼及转头仍需更多真实表情与视线组合的美术确认。

## 手和关节

- 左右手 SVG 分别重写了五指曲线、外轮廓，并对右掌轮廓单独调整；指根填色延伸到掌心下方、只给自由边上描线。右手仍使用镜像坐标变换定位，整体姿势依然相似，并非两套完全不同手势；右食指看起来偏独立、指间仍略机械，需人审看。手指是各自 ±5° 小摆，不能当成完整抓握/大角度姿态。
- 另绘肩、腕底稿；肘从袖管原图取色扩大隐蔽重叠区。构建时将新补片限制在静止状态前层完全不透明的区域：肩在身体/上袖下、肘在上袖/前袖下、腕在袖口下；这保证新补片静止时不直接露出，但不保证所有运动都被遮住。沿用上一轮肘旋转中心及 ±2° 肩、±4° 肘、±6° 腕范围。
- 真实 C 的各侧单关节极值、十指极值、组合姿势、浅深底及 0.35/0.55/0.8/1 缩放已采集；选图在 `experiments/live2d_chibi_closure/qa/`，`*_compare.png` 左旧右新。0.35 小尺寸仍有轮廓像素化，袖肘处细切线、袖侧边缘和腕线还不能判为彻底修好；未尝试超出上述范围的大角度。前后差异有些很小，不能从补片大小推断动态遮挡已完美。
- 两个动作 GIF 是 C 每三步采一帧、共 12 帧、150ms 播放的片段，非完整循环。截图和动作测试对指根露缝没有自动视觉判定，尤其混合手指组合仍需逐帧人工检查。

## 复现与检查

需要 Pillow、numpy、resvg-py；输出需为 `build/` 下不存在的新目录。预览无认证，不要存放私人数据。

```sh
make build/zhuochong_preview
/home/user/.imgenv/bin/python tools/build_chibi_closure.py build/my-closure
/home/user/.imgenv/bin/python tools/capture_chibi_art_review.py build/my-closure build/my-closure-qa --auto
/home/user/.imgenv/bin/python tools/preview_live2d_chibi.py --dynamic --dynamic-study build/my-closure --preview-root build/my-closure-preview 5259
make test-chibi-closure
```

`art_review_report.json` 是上游构建记录、已标记为被新报告取代；`closure_report.json` 记录本轮素材指纹及静态隐藏像素。交互滑块的开度 1 是睁眼、0 是闭眼；拖动后恢复自动眨眼先点“静止并复位”，再点“自动眨眼”。

- `make test`：2684 通过、0 失败；示例模块热加载跳过，长稳和 Windows 真机未测。
- `make test-chibi-closure`：独立路径、遮挡约束、十指/三关节实际 C 帧响应、47 文件 `.zproj` 打包还原后的 C 帧一致通过。十指两端差异 76–217 像素只说明有响应。
- Web 测试 266/0、动态控制专项及 5259 真实 Chromium 控件检查通过。人工视觉结论以上面的观察与限制为准，仍待用户验收。
