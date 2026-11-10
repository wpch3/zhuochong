# Chibi 袖口与手腕：隐藏原画和活动连接试验

目标是在保留现有 Chibi 形象的前提下，继续补足可编辑的运动遮挡原画；不动桌宠、少女及既有试装。参考 [Live2D 官方拆分](https://docs.live2d.com/en/cubism-editor-tutorials/psd/) 和 [Spine 素材与关节](https://en.esotericsoftware.com/blog/How-to-cut-your-assets-for-animation)：袖子、手腕与手应分层，露出的部位须有圆润、相互重叠的原画，黑边须考虑动作时的连接。

## 长工作流与验收

1. 目视左右袖口、手、衣身及两种背景，按实际斜向袖口设计左右独立切线、枢轴和新增手腕原画；从现有试装派生独立候选，保留初始身体侧片的版本指纹。
2. 保持源图和先前模型不变，建立可编辑、可复现的隐藏皮肤原画；先验证袖手重组在源分辨率中立时与原始试装相同，再用真实 C 检查不同缩放的中立泄色与左右手腕极值、中间态、两手组合和身体/袖子同时动作。
3. 多轮目视无遮挡手腕、袖口接缝、深浅背景、放大与循环帧；若袖口断裂、手指破损、补色或黑线不自然，不批准为成品。小范围摆动通过也不代表肘、肩或眼口完成，更不代表官方 Cubism。
4. 对生成器安全、源指纹、编辑和项目包往返、C 动作和浏览器控制做回归；保留 QA 和完整复现步骤，每轮提交推送当前分支。需要人手精绘的缺口继续明确列出。

## 本轮制作记录

- 旧图两侧袖与手是各一张图。分别以源图坐标 `y >= 0.52*x + 156` 和 `y >= 376 - 0.46*x` 试切；距斜线 3px 内的暗色、青色碎片留在袖口，避免青色袖边随手移动。手指不是独立图层。
- `wrist_underpaint_v1.svg` 是初版；真实 C 中袖口边缘有粉色凸起（见 `qa/v2_rejected_plus_dark.png`），因此在 `wrist_underpaint.svg` 缩窄、圆润轮廓。这个 SVG 是可编辑源，不是自动得到的完整手臂；生成时按左右袖完全不透明的区域裁切并置于袖后。左右枢轴 `[380,663]`、`[640,663]` 是试验坐标，腕组各隶属于原肩组，两个独立参数各限制 ±6°。
- 目前的试验加载 15 个部件、8 个组、7 个动作；两个手腕滑块只在手腕试验页启用，`wrist_test` 是轻微的相反相位循环。源图不覆盖，候选只输出至新的 `build/` 子目录。
- 实际目视：分别看了左右 ±1、同时 ±1、中间 0.5、交叉、袖腕组合、身体/袖腕/呼吸组合，以及循环的多个深底帧和浅底帧。正常尺寸是小幅活动；新版削弱了初版边缘粉色凸出，但左袖下边仍见小暗点/边界不平，袖腕连接和另一侧阴影仍偏硬。`qa/uncovered_l.png` 和 `qa/uncovered_r.png` 展示袖子隐藏后，仍有切线上的灰暗碎点，腕部边缘也没有完整黑色外轮廓。衣身侧片原有侧边和下端问题还在。**不予成品美术验收或覆盖正式形态。**
- 留存 `qa/` 的 C 帧、循环采样、浏览器截图和数值；手腕图是从 0.55 C 透明帧合成背景后放大，不是新绘画。截图中的中文方框是本次无头 Chromium 环境缺少中文字体，不能用它判断用户浏览器字体。

## 可复现与测试

需要 C 构建工具、Python 的 Pillow、numpy、`resvg-py==0.5.0`，以及 Node。先用 `make build/zhuochong_preview` 构建预览。以下输出目录必须不存在；它们仅是临时产物，`build/` 不入库：

```sh
python tools/build_chibi_wrists.py build/chibi-wrist-candidate
python tools/compare_chibi_wrists.py build/chibi-wrist-candidate build/chibi-wrist-qa
python tools/preview_live2d_chibi.py --dynamic --dynamic-study build/chibi-wrist-candidate --preview-root build/chibi-wrist-preview 5220
make test-chibi-wrists test-chibi-underlay test-dynamic-chibi
```

预览默认监听 `0.0.0.0`，**无认证**，只用于不含真实隐私或密钥的隔离测试。生成报告只说明源分辨率重组校验，默认 `neutral_c_verified: false`；C 对照结果另记在 QA `metrics.json`，不能误认为所有缩放一致。比较脚本重建两份独立衣身基线，按同一冻结顺序先确认 12 帧逐像素相等，再比较袖腕候选；比较范围仅限列出的比例、姿态和状态。

| 缩放 | 中立 | 双袖外摆 | 双袖内摆 |
|---|---:|---:|---:|
| 0.35 | 63 | 74 | 68 |
| 0.55 | 101 | 122 | 123 |
| 0.8 | 122 | 153 | 152 |
| 1.0 | 0 | 110 | 109 |

表为相对衣身 v2 基线每帧的不同像素数，并非视觉评分。左右每侧袖+腕底+手在源图分辨率的中立 RGBA 重组与旧袖手逐像素一致；**但 C 分层缩放在小于 1 倍的中立帧并不一致**。`qa/metrics.json` 还记录 0.55 下单腕/组合相对候选中立帧的变化；它不证明其他任意姿态无缝。手腕动作有效值在循环采样中变化，见 `qa/action_values.json`。

本轮验证：`test-chibi-wrists` 覆盖不可覆盖/越界/符号链接输出、源指纹、切片与隐藏图约束、真实 C 两基线/多比例/运动、16 文件 `.zproj` 校验解包和 C 帧逐像素往返。包含 rig 与 PNG，但 **不包含可编辑 SVG 源**，源需随仓库保留。真实 Chromium 检查双腕快速输入、复位和动作按钮，并回归旧袖滑块；DOM 模拟覆盖默认无腕选项及异步合并/复位。`make -s test-chibi-wrists test-chibi-underlay test-dynamic-chibi test-underpaint test-hidden-art-studies test-rig-editor test-zrig-project test-preview-actions` 通过；`make -s test` 通过 2646、失败 0，未构建的示例模块热加载烟测跳过。旧正式 Chibi 加载仍有 3 个警告。本轮未做 Windows 真机测试。

## 后续不可跳过

重新手绘袖口黑描边与连续的腕部隐藏轮廓，清除切线残点，扩大动作范围并逐帧检查；重做肩、肘与衣身遮挡原画和运动关键形态；随后处理眼白/眼球、嘴型、头发等的独立切件、遮罩、变形与完整项目工作流。现有小幅旋转不是完整手臂运动，更不是完整隐藏画稿或官方 Cubism 模型。
