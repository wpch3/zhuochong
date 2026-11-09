# Chibi 美术复核：混合手指与关节（仍未验收）

本轮从 `CHIBI_CLOSURE_STUDY_2026-11-06.md` 的独立候选继续，不覆盖正式模型或上一轮候选。逐帧图来自自研 C 预览；以下是本次审查观察，**不是最终美术验收**。

## 审查发现与修订

1. **袖口露肤色尖点：发现并局部改善。** 上轮只检查了单关节及同向组合；本轮补了肩、肘、腕各两端的全部 8 种组合，双侧交错手指同时施加。原候选在若干反向组合中，袖口外边露出小肤色尖点；将腕部底稿设为透明的对照中尖点消失，定位为腕底稿外露。新候选将原腕部补片限制在距离不透明袖口边界至少 2 个画布像素的范围，保留底稿而不是整个删掉。已采样组合中该尖点不再可见；这不是对所有动作、所有角度的保证，袖口边缘仍有细黑线，需人继续检查。
2. **右食指轮廓：部分改善。** 对右食指曲线做小幅调整，使其与中指更靠近；中立和分开极值都保留对照。它仍显得比其他手指独立，变化幅度较小，不能当成完整重绘或手形已通过。
3. **交错手指：未通过。** 两侧相邻手指反向转动时仍会融合、遮住指间线，看起来只有两三个手指；这是目前明确的视觉缺陷，不是可用的抓握姿态。试过把单指旋转从 ±5° 缩到 ±3°，交错时仍显融合、运动也更弱，故未采用；保留原 ±5° 作为试验，并保留失败样本。下一步应重做指间层级和不同姿态的指根/轮廓，而不是只缩摆幅。
4. **眼睛：本轮未改，仍有保留项。** 视线左右 ±1、头倾左右 ±1（实际 ±4°）与闭合 0.5/0.75/0.85 的 12 帧中，0.85 未见此前的蓝色窄边；0.75 仍是小蓝弧。0.5 半眨时瞳孔和高光被大幅遮住，呈浅蓝半圆，观感偏空；笑眼和眨眼叠加也仍须审看。本 rig 只有横向试验视线，本轮**没有**上下视线覆盖。
5. **肩肘：有限范围继续观察。** 肘、肩、腕范围沿用 ±4°、±2°、±6°；手指/关节混合的肩袖连接未出现明显大裂口，但衣袖与衣身细切线和低分辨率边缘仍在，不能判为彻底修复。更大角度、全表情动作、Windows 真机均未验证。

## 审查材料

`experiments/live2d_chibi_visual_review/qa/` 中：

- `L_joint_mix_*_compare.png` / `R_joint_mix_*_compare.png` 为同一真实 C 姿势的旧版／新版对照（左旧右新）。`R_joint_mix_2` 及 `L_joint_mix_2` 可看袖口外缘。
- `R_neutral_dark_compare.png`、`R_index_spread_dark_compare.png`、`R_alternating_dark_compare.png` 展示右食指调整；`L_alternating_dark.png` 和 `R_alternating_dark.png` 直接展示仍未解决的指间融合。`rejected_finger_3deg_*` 是未采用的小摆幅试验。
- `mixed_sweep_dark.gif` / `mixed_sweep_light.gif` 是把肩腕从 -1 到 1、肘反向、交错指姿同步插值的 **20 帧真实 C 手动参数采样**，再以每帧 140ms 回放并循环；不是引擎自动动作或真实播放速度。`poses.json` 记录 48 个固定姿势和每个扫动采样的参数。自动眨眼 GIF 是逐 C 步采样慢放，也不是实际速度。
- 另采浅/深底的 48 个固定姿势，以及单关节、十指端点、头部／笑眼、自动眨眼和四个比例的肩臂姿势；完整临时输出在 `build/chibi-matrix-after-final/` 与 `build/chibi-visual-final-qa/`。固定组合与扫动是有限采样，不代表参数空间穷尽；小比例图主要验证肩臂姿势，不是全部手指组合。

## 复现和技术检查

需 Pillow、numpy、resvg-py；使用 `build/` 下尚不存在的新目录。预览服务无认证，不要放私人数据。

```sh
make build/zhuochong_preview
/home/user/.imgenv/bin/python tools/build_chibi_visual_review.py build/my-visual-review
/home/user/.imgenv/bin/python tools/capture_chibi_visual_matrix.py build/my-visual-review build/my-visual-matrix
/home/user/.imgenv/bin/python tools/capture_chibi_art_review.py build/my-visual-review build/my-visual-full --auto
/home/user/.imgenv/bin/python tools/preview_live2d_chibi.py --dynamic --dynamic-study build/my-visual-review --preview-root build/my-visual-preview 5260
make test-chibi-visual-review
```

构建报告 `closure_report.json` 是上游记录，已标注由 `visual_review_report.json` 取代。新专项检查安全构建、腕片内缩限制、手指原摆幅、部分混合姿势的真实 C 帧及 47 文件工程包还原一致；真实 Chromium 控件及动态控制专项通过。测试不作任何视觉自动判分，本轮没有修改 C 引擎。

**结论：不建议晋升正式版本。** 请优先审核尖点前后对照与交错手指失败帧；后续仍需要指间分层／补画、半眨瞳孔表现及更广动作范围的复核，再请用户确认观感。
