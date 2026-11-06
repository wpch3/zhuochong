# zrig 编辑与绑定工具（实验版）

独立静态网页，**不是 Cubism Editor，也不是完整建模器**。支持读取自研 `rig.json`、加载 PNG 图层、静态近似画布及拖动部件、编辑坐标/层号、新增非内建参数、参数到组的平移/缩放/旋转绑定、撤销/重做与下载 JSON 副本。文件在浏览器处理，不自动覆盖源文件。挂点部件的位置由引擎中的 socket 决定，当前不能拖动或直接编辑。

画布用于方便布置部件，不是自研 C 引擎帧：它不计算遮罩、参数绑定、物理、姿态、动作或变形器，不等于最终外观；某些多状态眼口也只是默认静态近似。导入工程时选择含 `sprites/` 子目录的模型文件夹；示例是黑描边无兽特征 Chibi，PNG 放在 `demo/sprites/` 供离线演示。缺件、重复路径会提示。下载 JSON 不包含贴图。

```sh
cd tools/rig_editor
python3 -m http.server 5204 --bind 127.0.0.1  # 仅本机；可信沙箱预览可改为 0.0.0.0
# 仓库根目录运行：
make test-rig-editor test-zrig-project test-blackline
```

模拟 DOM 测试覆盖 UI，画布数学和拖动有独立单测；编辑器导出的参数绑定通过真实 C 引擎渲染测试。尚无真实浏览器自动化测试。只校验本工具可编辑的字段，不替代引擎完整校验和目视验收。

## 自研工程快照 `.zproj` v1

项目打包工具位于 `tools/zrig_project.py`。支持 `rig.json` 和 `sprites/` 下 PNG，清单记录路径、长度及 SHA-256。默认拒绝覆盖、路径穿越、重复或大小写冲突路径、解包到现有目录、超限压缩包、PNG 异常尺寸和外部动作/表情文件；不下载或执行任何代码。校验和仅用于损坏检测，并不验证文件可信或作者身份。**含外部 motions/expression_files 的少女 rig 会被拒绝**，v1 不声称完整支持那些工程，不能靠清单隐藏依赖。

```sh
# 不覆盖现有文件；这里创建一个新工程快照
python3 tools/zrig_project.py create experiments/live2d_chibi_human_blackline/rig.json /tmp/new-model.zproj
python3 tools/zrig_project.py verify /tmp/new-model.zproj
python3 tools/zrig_project.py unpack /tmp/new-model.zproj /tmp/new-model-unpacked
```

验证通过后解包到全新目录；测试会用解包文件加载真实 C 引擎并取得 PNG 帧。v1 只保留运行 rig 与 PNG，不包含分层源稿、编辑历史、PSD、源文件许可、外部动作或 Cubism 工程；也没有编辑器里的图形化打包界面。不要把它叫做完整作者工程。

## 后续缺口

网格/UV 与遮罩编辑、参数 keyform/多轴合成、实时 C 画布、PSD 分层导入、物理/动作时间线、真实浏览器端到端、工程迁移和完整插件安全体系均未完成。验收步骤见 `docs/TOOL_PRODUCTION_WORKFLOW_2026-11-06.md`。
