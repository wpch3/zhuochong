# Chibi `seg_head` source-underlay keep rule — full-chain WIP

日期：2026-11-02  
分支：`arena/aaf1408c-zhuochong`  
状态：生成器规则已实现并归档；隔离全链与真实 C 引擎已复验；**不等于 Chibi 验收或生产贴图验收**。

## 结论

眼缘浅色底片的缺失来自 `tools/clean_head_backing.py`：重建到 `after_clean_hair` 时这些源像素仍存在，且 `body_full` 在同位置有完整支持；随后脸部肤色带 / 4px halo keep mask 没覆盖三个已映射的小窗口，清理步骤便把 `seg_head` alpha 清掉。不是侧发遮挡、eyeline 绘制阶段或 rig/socket 坐标漂移。

已给 `xiaoxun/chibi` 加入一份 form-scoped JSON ROI 规则。它只扩 keep mask，要求每个保留像素同时满足：

1. `seg_head` 原始 alpha > 16；
2. 对齐的 `body_full` alpha > 16；
3. 该像素属于原始 `seg_head` 最大连通分量。

规则不画 RGB、不造 alpha、不扩张头部轮廓、不改变 rig 几何。配置只含左侧黑色短边、右上外缘、右下短边三个经固定 C 帧映射的区域；左灰标记明确不在配置中。

## 修复前后像素证据

纹理大小 `567×644`，ROI 为 source-space 半开区间 `[x0,y0,x1,y1)`：

| ROI | Before `clean_head` 的有效源像素 | baseline 清理后 | `body_full` 支持 | 原 keep mask | 配置实际留回 |
|---|---:|---:|---:|---:|---:|
| 左黑 `[145,470,156,472)` | 22/22 | 0/22 | 22/22 | 0/22 | 22 |
| 右上 `[411,447,426,449)` | 30/30 | 1/30 | 30/30 | 1/30 | 29 |
| 右下 `[409,462,413,464)` | 8/8 | 0/8 | 8/8 | 0/8 | 8 |
| 左灰参照 `[149,453,154,455)`（未配置） | 10/10 | 5/10 | 10/10 | 5/10 | 0 |

三处配置 ROI 合计 60 个符合条件的像素；左灰参照仍按原规则处理。源图阶段拼图见 `source_stage_underlay_transition.png`，逐窗统计见 `source_stage_alpha_analysis.json`。

## 构建、纹理与 QA

- 对配置规则做隔离完整重建；第一次进程在 rig 后运行 `trim_exposed_residue.py` 时被系统 `Killed`，**该次单进程不是完整通过**。停止多余 C 引擎预览释放内存后，从被中断的后续阶段单独续跑：trim 完成（0 px 变化），其余挂链步骤完成，最终 `check_assets.py` 真正执行。
- 这次配置驱动完整候选全链 QA：**1,342 项、33 项失败、`design_iou=0.9934918477598998`，`pass=false`**。失败仍涉及无损切分/袖下躯干洞、鞋、嘴部真素材与越界、闭眼 seam、腮红、发型同源/接管、手垫和 mouth mask 等；本规则没有解决这些全身问题。
- 配置驱动重建与隔离临时等效规则输出的两张头部纹理逐字节一致：
  - `seg_head.png`: `12cbd11b9889bc74f127c95a12649f00e0254b4f8c56ef328e3fb2aa7f0a80ea`
  - `seg_head@2x.png`: `170ac1d6b5bc12a2b02a117cbc8a9d4f2361b8b614a00b76d63cc66315270220`
- 这组 1,342/33 是本次候选的独立全链快照；不要和锁定源件 1,342/34、早期定向/聚焦 QA 或别的候选报告作连续改善/相减解读。

## 真实 C 引擎 A/B 目视

基线与配置驱动完整链各启动独立 C 引擎实例，统一设置 Chibi、全零参数、`t=0` 暂停、physics/ambient off、scale=1；采样状态中的 params 与 sockets 完全相同。

| C 帧窗口 | 基线暗像素 | 配置候选暗像素 |
|---|---:|---:|
| 左黑短边 | 10 | 0 |
| 左灰标记（控制项） | 7 | 7 |
| 右上外缘 | 29 | 0 |
| 右下短边 | 7 | 0 |

本人已直接查看 `c_engine_eye_area_baseline_vs_config.png` 和源图阶段对比：三个量测窗口的黑色 underlay 缺口被现有源肤色底片承接；左灰控制项不变；没有看到矩形补色补丁。外眼角仍有原有睫毛/轮廓细节，本次不把这些窗口外的黑色尖端统称为“全部清干净”。眼底、眼线和左右侧发隔离输出均与对应基线逐字节相同，说明 A/B 变化不来自眼件或侧发被替换。整帧变化 9,262 px、`seg_head` 隔离图变化 1,902 px；**整帧差异含完整重建的其他素材差异，不能全归因给此规则**。

## 仓库变更与边界

本阶段仓库实际变更：

- `tools/clean_head_backing.py`：新增只读源像素/身体支持/主连通分量校验的 keep-mask helper，并读取 Chibi 配置。
- `characters/xiaoxun/forms/chibi/design/seg_head_underlay_keep.json`：三个经过 C 帧配准的最窄 ROI。
- `tests/test_clean_head_backing.py`：三项测试，覆盖仅留合格像素、拒绝越界和拒绝尺寸不匹配。

现行生产 `sprites/seg_head*.png`、`rig.json` 未被本轮覆盖；候选生成纹理仅保存在此隔离证据目录。工具/配置进主分支后，下一次明确的 Chibi 重建会应用该规则，仍需重看全身及高分辨率输出。此前用等效 WIP 做过 C 目视；本轮配置驱动全链的 C 截图和 QA 已再次归档。未接受为整体 Chibi 验收。

## 本目录文件

- `source_stage_underlay_transition.png`、`source_stage_alpha_analysis.json`：清理前后源 alpha、body 支持与 keep-mask 的根因证据。
- `baseline_seg_head*.png`、`candidate_fullchain_seg_head*.png`：真实输入与候选 1×/2×源纹理。
- `c_engine_*` 与 `c_engine_isolation_hash_checks.json`：基线/候选固定帧、头部隔离、眼底和侧发层、运行状态及 hash 对照。
- `asset_qa_fullchain_config_driven.json`：完整配置候选链最终 QA 报告。
- `fullchain_config_build_partial.log`：第一次在 trim 阶段被系统杀掉的原始日志；续跑与最终 QA 口径见 `fullchain_config_resume_summary.json`。
- `candidate_underlay_keep.json`：本轮生效配置副本；权威配置位于 Chibi `design/` 目录。
- `SHA256SUMS.txt`：归档文件完整性清单。

## 下一阶段

先提交并推送本次代码、配置、测试及证据，再继续全身拆件和差分：`small` / `mitten` 通过独立 `hand_style` 切换，和 wrist/open/heart 手势解耦；之后检查发型/兜帽、眼口表情、服装遮挡、动作与真实 C 引擎组合。失败项逐类归档，不把局部眼缘结果当成整体完成。
