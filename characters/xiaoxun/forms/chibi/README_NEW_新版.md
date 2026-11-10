# 小寻 Q版（chibi）— NEW 新版（当前唯一生产形态）

- 真值源（NEW）：`characters/xiaoxun/design/design_sheet_chibi.png`（干净银紫短发母图）
- 整图：`sprites/body_full.png` MD5 ceb9e613…（由 prepare_sprites 按 body_fit 四点框重抠）
- 拆件：`sprites/` 202 文件，`rig.json` id=`小寻_chibi`，81 部件 / 26 动作 / 15 组
- 生成命令：隔离目录 `ZC_PYTHON=<venv> bash tools/rebuild_parts.sh xiaoxun chibi`（27步，日志 docs/qa/new_chibi_preview_2026-11-10/rebuild_new_chibi.log）
- 旧版（OLD，已删除）：原 49 部件 rig（id 误写小寻_teen）+ 粉白带黑点 body_full MD5 f56c542d…，2026-11-10 经用户命令彻底删除，禁止恢复/禁止在其上补丁。
- 已知未过（不冒充完成）：check_assets 1342项33项不通过（缺双马尾/马尾/兜帽差分源件、口内牙、闭眼接缝、腮红落点、躯干洞等，清单见审计）；引擎脸放大仍有额前浅矩形接缝、眼角小碎边、颈部粉块，待下一轮修。
