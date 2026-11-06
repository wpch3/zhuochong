# 小寻 Live2D 风格 Chibi · 短发试装（隔离）

与 `experiments/chibi_face_study/` 的桌宠 Q 版分开存放，**未覆盖桌宠试作或任何正式形态**。以少女短发设定 `characters/xiaoxun/design/design_sheet_short.png` 的角色、线条和配色，以及用户选定的 `docs/qa/chibi_candidate_2026-11-01/reference_generated/chibi_short_hair_live2d.png` 的 Chibi 比例为方向，制作独立新图。仍需用户视觉审阅确认；本图并不代表长发或双马尾已完成。

## 当前实际完成

- 概念及 AI 补画在 `characters/xiaoxun/design/live2d_chibi_2026-11-06/`，含原图、面部底图、闭眼/说话、去猫耳和去尾巴图。它们是整图生成和编辑结果，不是原画师提供的分层源文件。`torso_underlay.png` 为失败试验：去袖后的身体被重绘成露臂及裙摆，**未用于 rig**。
- `rig.json` 是项目自研 C `zrig`，不是 Cubism `.cmo3` / `.moc3`；12 张透明贴图：身体、头、左右耳、尾巴、左右开闭眼、鼻、闭口和张口。身体包括四肢、衣服；头包括发型及脸底。耳和尾由可见部分与补画差分估算，**不是被遮挡部位的完整真实画稿**。
- `head_test`、`ear_test`、`tail_test` 为分开检查头、猫耳、猫尾的小角度旋转，`sway` 是组合动作；`talk` 切换嘴形。眨眼切图，头部/耳尾均为刚性贴图旋转，不是网格形变或物理模型。

## 复现和实测

```sh
# Python 环境需安装 pillow、numpy；也可使用仓库外的独立虚拟环境。
python3 tools/build_live2d_chibi_study.py
make build/zhuochong_preview
python3 tools/preview_live2d_chibi.py 5202
# 另开终端；只会改变隔离试装的临时状态
python3 tools/capture_live2d_chibi_study.py
```

预览配置和运行数据在被忽略的 `build/live2d-chibi-preview/`；UI 仅提供支持的动作和眼口控制。监听 0.0.0.0 的预览没有认证，只能在可信隔离环境使用，不要放入私密数据或密钥。

`qa/` 是实际 C 服务的 563×563 像素帧，`metrics.json` 是图像差异计数，不是视觉质量评分：分别比较眨眼两侧、口型及头/双耳/尾巴动作，并确认头和耳动作时身体区域、尾巴动作时头部区域保持不变。数值可能随渲染尺度和环境改变；重跑脚本可复核。使用 `api/action` + 冻结时钟单步，而不是只检查 JSON 声称的动画。

## 未完成与风险

- 当前仍只是试装：手臂、腕、手、衣物、头发和身体没有分别拆层，也没有可用的两套独立手型；后续要依照用户选定的**小巧手 / 手套感**契约分别制作，不能把当前手部视为已验收。
- 头与身体交界、耳根与尾根的补画不充分；旋转幅度放大可能露出切缝。细发丝和鞋手周围仍有少量抠色杂边，应人工精修、补全遮挡区后逐帧复查。眼口差分是配准近似且切换式，不是高质量连续变形。
- 长发、双马尾、帽兜、完整动作、物理、表情、网格和 Windows 真机均未完成或未验证；桌宠和本试装仍需分别验收，不可把任何一个称为正式模型已完成。
