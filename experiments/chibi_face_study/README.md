# 小寻 Q 版面部动画试作（隔离候选）

这不是完成的 Live2D/Cubism 模型，也不是已验收的完整自研 rig。这里仅验证一张新图的**眼睛与嘴型**在项目现有 C `zrig` 中可被控制；未替换 `characters/xiaoxun/forms/chibi` 的正式模型。

## 内容和来源

- 基础概念：`characters/xiaoxun/design/chibi/production_concept_2026-11-06.png`，参照原有小寻 Q 版形象生成。
- AI 编辑差分：同目录 `rebuild_2026-11-06/face_underpaint.png`（去五官的面部底图）、`eyes_closed.png`、`mouth_open.png`。它们是生成/编辑结果，不是手绘分层原稿，也不是被遮挡部位的原始真值。
- `sprites/base.png` 是包括身体、头发、衣服、四肢的一整张底图；左右开闭眼、鼻子、静止/张嘴另为 7 个透明件，总共 8 件。`rig.json` 使用自研 JSON 格式；`tools/build_chibi_face_study.py` 由上述图片生成。
- `idle`、`sway`、`talk` 是试作动作，其中 `sway` 旋转**整张身体图**，不是独立头发、衣物、关节或物理链。左右眼可单独按参数开闭，`ParamMouthOpenY` 交叉切换嘴型。眨眼是图层切换，不是完整连续眼睑网格变形。

## 操作

```sh
# 仅本次自动拆取过程需要 Pillow 和 numpy
/home/user/.imgenv/bin/python tools/build_chibi_face_study.py
make build/zhuochong_preview
python3 tools/preview_chibi_face_study.py 5201
# 另开终端：冻结时间并抓取真实 C 帧；会临时改变试作预览的状态
/home/user/.imgenv/bin/python tools/capture_chibi_face_study.py
```

预览脚本把配置与专用界面放在被忽略的 `build/chibi-face-preview/`，使用独立形式 `face_study`；不会覆盖正式资产。专用界面只显示该试作支持的动作与眼口控制。预览没有公网认证，不要用于真实私有数据或密钥。

## 实测和局限

`qa/open.png`、`qa/closed.png`、`qa/mouth.png` 是真实 C 服务帧（554×573，窗口缩放 0.55），`qa/metrics.json` 记录固定时钟前后双眼和嘴部变化像素：左眼 3924、右眼 3752、嘴部 518。测试验证渲染确实变化，并不证明观感、遮挡或质量达标。`tests/test_core.c` 也对实际图像验证双眼、左眼单独闭合和嘴型的区域像素变化。

本人观察：试作能显示睁眼、闭眼和张嘴，脸部相对旧资源更干净；但头发外轮廓及手鞋处仍可见细小洋红边，细发边缘需要人工清理；局部差分的接缝、眨眼中间态还需细修。身体/头发完全未独立拆件，缺少遮挡补画、腕关节、发型、表情、网格与物理绑定，也没有 Windows 真机测试。不得以这套试作声称原任务完成或生产质量通过。

制作试作时发现：没有 `param_groups` 的 rig 中，C 引擎提前返回导致双眼眨眼目标为 0，而参数本身仍显示闭合；现已修复缺省双眼，并用试作实际渲染的像素测试守住回归。
