# 无兽特征 Chibi · 黑描边隔离试装

从 `experiments/live2d_chibi_human_short/` 单独派生，不覆盖原无兽特征版或带猫耳/尾巴的版本。根据用户偏好，对已有暗线做局部压暗，并对头、身体透明轮廓作近黑色边缘处理；保持每个像素的 alpha、位置、尺寸、层级不变。**这是自动色调试验，不是画师逐线重描**：细发、鞋边和半透明抠色处仍需在浅/深背景、运动和极值下审查，不能称为精修通过。手臂、双手型、长发/双马尾、连续眼睑、网格及物理仍未完成。

```sh
# 需 Pillow 和 numpy；不会更改原版本
python3 tools/build_human_chibi_blackline.py
make build/zhuochong_preview
python3 tools/preview_live2d_chibi.py --blackline 5205
# 另开终端；会临时切换隔离预览的动作状态
python3 tools/capture_human_chibi_study.py --blackline
make test-blackline
```

`qa/` 为真实 C 预览帧；`metrics.json` 验证双眼、嘴、头部动作及身体静止区域。像素测试不能替代美术验收。预览无认证，勿用于私密数据或密钥。

`model.zproj` 是自研工程快照，含 `rig.json` 与 9 个 PNG，不包含未遮挡的分层原画，也不是 PSD、`.cmo3` 或 `.moc3`。检查/解包方法见 `tools/rig_editor/README.md`。zip 内哈希只检测破损，不认证作者或内容安全。
