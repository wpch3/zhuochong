# Chibi 摸头命中区 X 边界修复 — 2026-11-01

> 隔离候选的一个已验证修复；仅改变交互矩形，不改变贴图或视觉，不代表整个 Chibi 已验收/接生产。

## 根因与改动

`make_rig.py` 原先只用 `sprites_report` 粗略建议的 head X 范围 `[196,649)`，没有按实际 `seg_head` 覆盖。最新 Chibi 候选 `seg_head` 占 `[140,707]`，左右真实脸/发缘超出区域，机器 QA 判定脸边会落到 body，触摸不能稳定触发 `head_pat`。

现在 `head` region 的左右边界取建议值与实际 `seg_head` bbox 的并集，并外扩 4px；实际 rig 矩形是 `[136,0,575,718]`（x+width 为 711）；垂直下巴边界保持原规则，head 与 body 仍在 chin 分界处交接。没有改变 QA 阈值，也没有更改生产 rig。

## 验证

- 变更前隔离 `check_assets.py`：1342 项 / 34 fail，其中 `摸头区域罩住整张脸` 失败。
- 只重生成隔离候选 rig 后再次跑同一 1342 项检查：**33 fail**；该摸头区域项现通过，head 区域 `[136,711]` 覆盖 `seg_head [140,707]`。全链其余 33 项仍未解决。
- C 引擎以 Chibi、scale=1.0、freeze、ambient/physics off 实测 `/api/region?space=canvas`：真实有像素的左/右边界点 `(180,500)`、`(690,500)`、`(705,500)` 都返回 `region=head, action=head_pat`；透明控制点 `(150,500)` 仍返回空区，没有把透明像素伪报成命中。
- 证据：`head_hitbox_engine_probe_2026-11-01.json` 与 `asset_qa_targeted_hitbox_rerun_2026-11-01.json`。这是目标 rig 重生成后的局部回归，不是一次新的 27 步完整 clean rebuild。

下一步依照最新 33 项失败台账继续修眼口、身体几何、鞋与差分接管；每项修复仍需隔离、全阈值重测与真实 C 引擎目视。生产门禁未解除。
