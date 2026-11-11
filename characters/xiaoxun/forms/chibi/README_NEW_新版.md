# 小寻 Q版（chibi）— NEW 新版（当前唯一生产形态）

- 真值源（NEW）：`characters/xiaoxun/design/design_sheet_chibi.png`（干净银紫短发母图）
- 整图：`sprites/body_full.png` MD5 ceb9e613…（由 prepare_sprites 按 body_fit 四点框重抠）
- 拆件：`sprites/` 202 文件，`rig.json` id=`小寻_chibi`，81 部件 / 26 动作 / 15 组
- 生成命令：隔离目录 `ZC_PYTHON=<venv> bash tools/rebuild_parts.sh xiaoxun chibi`（27步，日志 docs/qa/new_chibi_preview_2026-11-10/rebuild_new_chibi.log）
- 旧版（OLD，已删除）：原 49 部件 rig（id 误写小寻_teen）+ 粉白带黑点 body_full MD5 f56c542d…，2026-11-10 经用户命令彻底删除，禁止恢复/禁止在其上补丁。
- 已知未过（不冒充完成）：check_assets 1342项33项不通过（缺双马尾/马尾/兜帽差分源件、口内牙、闭眼接缝、腮红落点、躯干洞等，清单见审计）；引擎脸放大仍有额前浅矩形接缝、眼角小碎边、颈部粉块，待下一轮修。

## 修复轮 2026-11-10（第二轮）
- 诊断（逐件放大）：额前矩形=`make_eyeline_parts` 换皮硬边界+补片肤色偏差；眼角碎边=睫毛尖被1px抗锯齿断成独立块；颈部粉块经色值实测为正常颈影（两件差<3），不改。
- 修复（生成器级，已进 rebuild 链）：eyeline 加色调匹配（钳±16）+2px羽化；chibi 眼线加1px闭运算接回断口（l接110px/r接84px）；碎岛清理扩展名单（阈值保守，hair_front 630px 合法发梢未误删）。
- 验证：隔离全链重跑后引擎脸放大（docs/qa/new_chibi_preview_2026-11-10/engine_fix2_face.png）矩形明显变淡；眼角仍有小缺口、check_assets 仍33项（缺发型差分源件等结构欠账），未通过总验收。

## 修复轮 2026-11-10（第三轮：黑点定性 + 铁律19 重做 + 猫耳猫尾重置）
- 黑点定性（真值源三联对位：design_sheet / body_full / 引擎帧）：**原图干净，是拆件错误**。①眼睛黑点=`eye_?_lash_up` 的卫星碎块（左眼100px碎片、右眼390px竖条）；②头发黑点=`hair_front` 右下角630px断开碎片（内含100px深色块），落在右眼上方。
- 按铁律19（本轮新增：同件同路线修两次不好→整件重做）弃补丁路线：`make_eyeline_parts` 改为只留最大8连通主弧（l删711px/r删750px卫星块）；`make_bangs_parts` 改为只留最大连通主体（删630px碎片）。生成器级生效，全链重跑后引擎脸放大实拍黑点消失（docs/qa/new_chibi_preview_2026-11-10/engine_fix6_face.png）。
- 猫耳猫尾裁决：**画风不符、需要重置**。原猫耳为写实毛流（design/redraw/acc_ear_cat.png 旧版）、猫尾为空气喷涂渐变，与本体平涂赛璐璐不符；且设计稿本体无兽耳兽尾，属外加挂件。已重置：新生成平涂源图（银紫主体+蓝尖，与发色同逻辑）替换 ear/relaxed/up/puff/tuck 全部源图；尾巴四档改为独立源图，禁止再用 make_tail_poses 重铺（attachments.json 已注记）。
- 附带修复：`make_attach_parts` 反预乘把粉色内耳 (251,190,199) 洗成米黄 (251,221,190) 的系统性偏色——harden 后对实心内部逐字节回正原画颜色（仅原色直通分支），实测内耳恢复 (253,193,201)。
- 注意：rebuild_parts.sh 对 chibi 跳过挂件重生成（保留现有附件），本次挂件是手动跑 make_attach_parts 全量生成的（27件/12槽）；rig 部件 81→97（补齐发型/兜帽差分件），check_assets 1585项/30项不通过（较上轮33减少，余为闭眼接缝色差等结构欠账），仍未通过总验收。

## 修复轮 2026-11-10（第三轮续：耳宽 A/B + 眨眼诊断）
- 猫耳按教程口径（アタム/パルミー：略扁三角、Q版不画毛流）把 width_ratio 0.78→0.90，引擎脸放大对比后保留 0.90（engine_ear90_face.png）。调研依据已记 docs/REFERENCE_NOTES.md 第七十五批。
- 眨眼诊断（/api/part 逐件隔离实测）：闭眼线正常；眼角白点主因是 hair_side 发梢（原画连通发束，非碎片）压在闭眼皮肤上显眼，次因高光件在眨眼时未随眼睑淡净——列为次要项。当前脸部主要剩余缺陷：闭眼时眼上方皮肤补片接缝带（接缝色差 Δ≈45 的实拍对应，engine_blink_diag.png）。按铁律19判断：换皮路线已补两轮，下一轮须换路线（梯度域融合或重生闭眼补片），不在旧补丁上续补。
