# 遮挡底稿实验工作台

这是动态 Chibi 的**局部补画工具**，不是完整绘画软件、Cubism Editor 或 C 运行时。只处理与当前动态试装对齐的 480×512 身体、左袖手、右袖手 PNG。浏览器内编辑；没有上传、覆盖源图或自动将候选安装到正式模型的功能。

## 使用

```sh
# 仓库根目录；只将工作台及三张公开试装图片复制到临时静态站点
python3 tools/preview_underpaint_editor.py --port 5211
# 打开预览 → 载入动态 Chibi 示例 → 隐藏袖手或打开高亮 → 取色/补画
# 用左右袖旋转、浅/深底检查，再下载 underpaint-patch.png

# Pillow/numpy 环境；输出必须是不存在的新目录，不会覆盖源
python tools/build_underpaint_trial.py ~/Downloads/underpaint-patch.png build/my-underpaint-candidate
# 可选：在隔离 C 引擎中查看候选，与原动态试装分别启动
python3 tools/preview_live2d_chibi.py --dynamic 5209
python3 tools/preview_live2d_chibi.py --dynamic --dynamic-study build/my-underpaint-candidate --preview-root build/my-underpaint-preview 5212
python tools/compare_underpaint_c.py --baseline-port 5209 --candidate-port 5212 --out build/my-underpaint-comparison
```

静态站点绑定 `0.0.0.0` 以便沙箱预览，但只提供隔离副本和三张示例 PNG，不提供仓库、`.git`、配置或私密文件；仍不应把不可信数据放在该服务的临时目录。要使用本地文件，选择三张对齐 PNG 后点击「载入所选文件」。已画过的内容在重新载入前要求确认；失败的载入不丢弃已有补画。刷新页面不会保存历史，**离开前应下载补画 PNG**。

画笔笔触、取色、大小、逐笔撤销/重做、取消指针、放大、浅/深/棋盘背景、袖手显示及中立位置可画区高亮均为局部试验。画布只预览袖手围绕固定枢轴的二维旋转；无头部合成、动作、物理、遮罩、蒙皮、抗锯齿一致性或实时 C 引擎求值。旋转超过 ±2° 仅用于暴露缺陷，不是更大动作已合格。

## 强约束与局限

- 笔触被裁剪到**中立袖手 alpha 恰为 255 的像素**；抗锯齿边缘不允许补画。它不能画到袖手外的透明背景，也不能凭空产生完整的肩膀、袖子背面或运动后出现的轮廓。要做真正大幅动作仍需要可编辑的完整原画及精确遮挡层。
- 下载的是透明补画层，不是重写后的身体图。`build_underpaint_trial.py` 独立重新计算来源袖手遮挡范围，拒绝越界、空补画、错误尺寸、已有输出路径及正式模型路径，核验三层中立 RGBA 合成完全一致，并输出来源和补画哈希报告。其验证不能证明图片好看，也不能保证 C 缩放后中立帧完全一致。
- 导入候选时仅复制 rig 和引用的 PNG；示例/原始补画及编辑历史不自动写进 `.zproj` v1。请另存 PNG 和报告。候选仍需人工目视、C 帧、动作和回归验证，不能自动升级正式模型。

## 测试与示例

```sh
make test-underpaint test-dynamic-chibi
# 可选真实 Chromium（先启动预览，安装 playwright-core 与 @sparticuz/chromium）
NODE_PATH=/path/to/node_modules make test-underpaint-browser
```

真实 Chromium 在正常和 150% 缩放下测试笔触、遮挡区高亮、撤销/重做、取消手势、取消重新载入、无效 PNG 保留当前内容及下载；下载的 PNG 随后在隔离真实 C 引擎测试。基于补画图建立的候选另通过 `.zproj` 创建、验证和解包。`qa/` 包含工作台截图、浏览器画出的示例补画及真实 C 对照图。

**这份示例补画不予采用**：使用单一浅色处理袖下条纹，虽然三层 PNG 中立合成完全相同，实际 563×563 C 中立帧仍与来源不同 200 像素；外摆 532、内摆 48 像素。目视浅/深底后，局部接缝仍明显、不具备完整隐藏画稿，不能证明品质提升。示例仅用于验证工具和暴露局限，原动态试装未被覆盖。

## 参考

- [Live2D Illustration Processing](https://docs.live2d.com/en/cubism-editor-tutorials/psd/)：分层后需补画移动时露出的区域。
- [Live2D About Material Separation](https://docs.live2d.com/en/cubism-editor-manual/divide-the-material/)：保留原图和可撤销蒙版，将补画放在独立层。
- [Canvas 合成模式](https://webplatform.github.io/docs/apis/canvas/CanvasRenderingContext2D/globalCompositeOperation/)：使用 destination-in 将笔触限制在遮挡范围；由 Python 侧独立验证，不能信任浏览器剪裁作为唯一保护。
