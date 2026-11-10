# 接手审计（2026-11-10）— 不接受未完成/错误事项

分支：`arena/60485539-zhuochong`（基于 `b208eb4`）｜方法：铁律 0–17，先用眼睛看真实产物，再信数字。

## 结论先行

- **接受**：C 引擎基础、干净的新 Chibi 设计底图。
- **不接受**：交接文里“200+ 部件新 Chibi 已入库、工具链已修复、组合检查待跑完即完工”的说法——仓库里不存在，数字对不上，工具 import 的模块缺失，实机画面仍是旧模型。
- **新旧 Chibi 必须分清**：今后一切 Chibi 工作以干净底图为真值源，**禁止**再以满身黑点的旧生产件（`forms/chibi/sprites/body_full.png` / `seg_head.png` 及其引擎帧）为基础修补。

## 一、亲眼看过（本轮证据）

| 图 | 我看到了什么 | 判定 |
|---|---|---|
| `characters/xiaoxun/design/design_sheet_chibi.png`（洋红底） | 银紫短发、蓝瞳、鲸鱼夹、白/青外套、藏青裙，线条干净，**无黑碎块**，无猫耳/尾巴 | ✅ 新基础真值源 |
| `characters/xiaoxun/design/chibi/desktop_pet_base_2026-10-31.png` + `desktop_pet_walk_side_2026-10-31.png` | 同一干净形象的正面/侧面行走，深蓝底，无黑点，比例约头占一半 | ✅ 新基础（桌宠版先行，见该目录 README） |
| `docs/qa/live2d_chibi_baseline_face_detail_2026-10-31.png` | 刘海下沿、额头两侧、鬓角有明显黑/褐碎块锯齿（仓库自记：chibi 近黑像素 7997 vs teen 10） | ❌ 旧模型，不接受 |
| `docs/qa/takeover_2026-11-10_live_chibi.png`（本轮 `./build/zhuochong_preview` 实拍，`/api/form?id=chibi`） | 与上同一旧模型：发色洗成粉白、鲸鱼夹旁与额前黑三角碎块仍在、猫耳/尾烘在画面里 | ❌ 当前生产 Chibi 仍旧，未换新 |
| `characters/xiaoxun/forms/chibi/design/redraw/head_nobangs.png` | 无刘海额头本身干净，但服装是青色拉链运动服、与常服外套不一致，且闭眼烘在脸上 | ⚠️ 只能当局部参考，不能直接当常服底图接生产 |

## 二、数字核对（不采信交接文数字）

| 交接文说法 | 仓库实测 | 判定 |
|---|---|---|
| rig 含 200+ 动态部件、30+ 动作通道 | `forms/chibi/rig.json`：**49 部件 / 22 动作 / 9 组 / 43 参数 / 8 表情**（teen 是 112/26/15） | ❌ 虚报，不接受 |
| 形态 ID `chibi` 正确入库 | rig 的 `id` 仍是 **`小寻_teen`**（`make_rig.py` 已改按 form 派生，但生产 rig 未重生，T70.5 已记此事） | ❌ 已知 bug，未修完 |
| 设计图 `live2d_chibi_2026-11-06/`、`tools/preview_live2d_chibi.py`、`tracking/CHIBI_*.md`、`COMBINATION_CHECK_RANGE_*.md` 已入库 | 全仓 `find` 无此四类文件；`tracking/` 目录不存在；`.imgenv` 不存在 | ❌ 不存在，不接受 |
| 工具链已修复（execv/verify_pose/循环导入） | `tools/capture_chibi_*.py` import 的 `capture_chibi_art_review / capture_chibi_joint_art / capture_chibi_refinement / chibi_capture_provenance / build_underpaint_trial / underpaint_mask` **六个模块全缺失**，系统 python 无 PIL | ❌ 跑不起来，不接受 |
| 三处视觉问题修复中、只差保存 C 帧 | TASKS 实况：T67.67 隔离候选 QA 1342 项 **33–34 fail**、T67.69 双手型未实现、T67.70 眼角碎边未过、T70.2–T70.5 均 `[~]`；本轮实拍黑点仍在 | ❌ 未完成，不接受为“只差一步” |
| 组合检查 1024 姿势/243 表情/手指矩阵 | 无任何已跑结果文件，执行工具本身 import 失败 | ❌ 未执行 |
| 真 Cubism 模型 | 无 PSD/CMO3/MOC3/model3（T70.5） | ❌ 未做，zrig 不冒称 Cubism |

## 三、接受清单（已验证）

1. **[测试锁] C 基础引擎**：本轮 `make test` **2638 项通过 / 0 失败**；`make build/zhuochong_preview` 构建成功。
2. **[沙箱实测] 预览与形态切换**：预览服务真实 C 引擎渲染，`/api/form?id=chibi` 返回 ok，动作表 21 项（呼吸…好奇歪头）可列；但画面内容是旧 Chibi（见上）。
3. **新 Chibi 基础（用户强调、已亲验）**：`design_sheet_chibi.png` 与 `design/chibi/desktop_pet_base/walk_side_2026-10-31.png` 干净、身份一致（银紫发/蓝瞳/鲸鱼夹/白青外套/藏青裙/双条纹袜/青白鞋）。这是后续拆件唯一真值源。
4. 形态可移植架构（T2.2.0/T2.2.5）、teen 主形态 112 部件链路——按 TASKS 已有证据接受，不在本轮重验范围外扩称。

## 四、下一步（按依赖，不跳步）

1. 以干净底图（优先 `design_sheet_chibi.png`，桌宠比例参考 desktop_pet_base）**隔离重做** Chibi 拆件：先整身校验 → 独立部件（前/侧/后发、眼 socket/base/ball/lash/closed/smile/pain/wide、口、臂/手 small+mitten 双手型、袖口夹层）→ 补遮挡区（铁律 9/10）→ 再生成 rig，并顺手修 rig `id`。
2. 补齐或重写 capture 工具缺失的六个模块（或删掉死 import 改直连 preview API），PIL 环境用仓库可复现方式声明，不依赖不存在的 `.imgenv`。
3. 新候选过：静态拼合 + 真实 C 引擎矩阵（眨眼/表情叠加/肩肘腕/手指/发型×兜帽）亲眼看图 → 用户确认 → 才替换生产 `forms/chibi/`。旧 body_full 在替换前保留仅作反面基线，不得在其上打补丁冒充新模型。
4. [需真机] 项（透明窗/穿透/托盘等）仍未验，不代用户宣布完成。

*本审计只纠正状态，不改任何生产素材/rig/生成器。*
