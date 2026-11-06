# zrig 编辑与绑定原型

这是独立静态网页，**不是 Cubism Editor**。当前支持读取 zrig JSON、调整部件位置/层号、新增非内建参数、添加/删除参数到现有组的旋转/平移/缩放绑定、撤销/重做及下载 JSON 副本。输入仅在浏览器中处理，下载不覆盖源文件。示例 `demo.json` 是无兽特征 Chibi 的 rig 快照，图片资源不包含在下载中；将导出 JSON 用于引擎时，应在隔离模型目录手动配齐原有相对路径贴图。

```sh
cd tools/rig_editor
python3 -m http.server 5204 --bind 127.0.0.1  # 本地使用；受信任沙箱预览可改为 0.0.0.0
# 另开终端，自仓库根目录：
node tests/test_rig_editor.js
make build/zhuochong_preview
python3 tests/test_rig_editor_integration.py
```

集成测试把原型输出的 JSON、贴图放入临时隔离根目录，用实际 C 服务加载，比较参数为 0、1、0 的渲染帧；不修改正式模型。已禁止新建同名内建参数与 C 引擎会忽略的组 alpha 绑定。校验只覆盖本原型能编辑的字段，不能代替 C 引擎的完整校验；任意手工导入的 rig 仍必须在隔离实例中加载和目视。

**尚未实现**：绘制/预览模型画布、纹理导入、PSD、三角网格、变形器及 keyform 的编辑、二轴角度、遮罩、物理、时间线、插件接口、编辑状态持久化、Cubism 文件导出或完整产品安全机制。参考与后续任务见 `docs/CUBISM_WORKFLOW_AND_EDITOR_GAPS_2026-11-06.md`。不要把这个原型称为完整编辑器/绑定器。
