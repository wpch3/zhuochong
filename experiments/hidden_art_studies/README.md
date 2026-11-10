# 两种体型的可编辑隐藏衣物试验（未验收）

这里存的是本工作包新绘的矢量曲线、渐变和阴影，不是从源图延长扫描线，也不是原始 PSD；但它们只是有限区域的概念底稿，**不是完整的肩袖、手臂和躯干原画，不是合格模型**。两种体型独立绘制和保存。原模型未修改。`qa/` 是实际目视证据，不是素材审批。

- `chibi/inner_jacket.svg` 是 Chibi 身体图（480×512）局部坐标中的内侧布料试画。`inner_jacket_clipped.png` 是按原袖手全不透明区做 0px 裁切后的试验补画，透明区外仍需要真实画稿。这个边距是为了观察实际露出的效果，已知会造成 C 中立缩放漏色；**不要用于生产模型**。
- `teen/torso_underarms.svg` 是少女躯干部件（273×500 的 1× 局部坐标）的独立内侧布料试画，不复用 Chibi 图。PNG 为 1× 可查看版，C 候选用矢量重新渲染的 2× 版本，作为独立部件放在 `chest`、层 97、坐标 `[282,308]`、缩放 0.5。未解决已有轮廓锯齿或帽发缺稿。

## 重建

需要 Python、Pillow、numpy、`resvg-py==0.5.0` 和 C 预览（`make build/zhuochong_preview`）。例如在已有隔离 Python 环境安装 `pip install resvg-py==0.5.0`：

```sh
python tools/build_hidden_art_studies.py build/hidden-art-studies-v1
make test-hidden-art-studies
# 启动分开的未验收试验预览，输出路径不能已存在：
python tools/preview_live2d_chibi.py --dynamic --dynamic-study build/hidden-art-studies-v1/chibi --preview-root build/chibi-hidden-preview 5213
python tools/preview_teen_hidden_art.py build/hidden-art-studies-v1/teen --preview-root build/teen-hidden-preview --port 5216
```

生成器仅允许新的 `build/` 子目录，拒绝覆盖，核对坐标相关源文件 SHA-256。两个候选分别位于输出的 `chibi/` 和 `teen/`；少女候选引用角色目录上层的外部 motions / expressions，因此移动到真正预览根的 `characters/xiaoxun/forms/teen/` 时还需准备这些外部依赖，不能只拷贝 rig。自动测试使用临时预览根和真实 C，运行后清理；并非性能或视觉验收。

## 本轮真实 C 与目视

- Chibi 563×563、0.55、固定步进中立 / 两侧 ±2° 与原动态试装相比相差 386 / 771 / 280 像素。中立源分辨率三层合成虽相等，真实 C 仍因分层缩放发生变化；本候选不能作为无漏色修复。打开无遮挡身体图可以清楚看到新增的两条平滑布块与原衣服不衔接、底端突兀；浅/深底动作中接缝仍存在。因此拒绝晋升为正式图。
- 少女真实 C 加载新增第 113 件并载入外部 motion 和 expression，实际查看呼吸及 wave 多个步进，截图为 0.55 缩放。wave 右袖与躯干交界仍有尖锐深色裂缝、左衣侧也有不连续边线；无遮挡躯干中旧切边仍在前面，新增布料也未构成完整肩部结构。因此拒绝晋升，不能声称解决动态接缝。
- 少女两个独立引擎进程存在动作/物理历史及随机状态差异；本次未控制全部状态，两个进程的像素差异**不能归因于新图，也不作为性能或静止等价数字**。截图仅用于人眼检查。本轮随后加入同一实例的部件开关对照（见下），不同 rig 的完整状态对齐仍是后续工作；应按缺口逐部件重绘，不能靠一条通用镜像曲线代替真实服装。

## 同一状态的 C 部件开关对照

为消除两个进程之间的姿态差异，新增 `tools/rig_part_ab.c`：在**同一个**真实 zrig 实例中按 60fps 固定步进动作，然后不再 tick，仅关闭/开启/再关闭指定部件并渲染；最后两次关闭帧必须逐字节一致。它只验证这一时刻、该部件在同一 rig 中显示对渲染结果的影响，不保证两个不同 rig 的物理、隐藏层或遮罩行为等价，也不自动评价美术。

少女候选上，0.55 缩放下 breath 第 1 步差异 419 像素，wave 第 0/15/30/60 步为 428/757/833/894；wave 第 30 步 1.0 缩放为 2079。关闭—开启—关闭逐字节一致。目视同一 wave 帧的浅色布料变化仍不能修复右袖尖裂和左衣侧边线，结果依然不予批准。

运行示例（少女 rig 应位于其角色目录下，以解析外部动作；输出目录须预先创建且不可已有 off.png/on.png）：

```sh
make build/rig_part_ab
mkdir -p build/teen-ab
build/rig_part_ab build/teen-hidden-preview/characters/xiaoxun/forms/teen/rig.json \
  build/teen-hidden-preview/characters/xiaoxun/forms/teen hidden_torso_underarms wave 30 0.55 build/teen-ab
```

离线探针采用单线程 C 渲染，不接网页或生产服务。原始 PNG 无损，输出中的 off/on 命名固定，已存在时拒绝覆盖；若第二张保存失败，第一张可能已写出。`qa/teen_same_wave_{off,on}.png` 是同一帧深底放大图。
