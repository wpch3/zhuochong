# 无兽特征 Chibi · 短发隔离试装

在 `experiments/live2d_chibi_short/` 的短发试装上制作独立版本：移除猫耳、猫尾及对应骨组/动作，保留新生成的无猫耳发型底图、无猫尾身体底图以及头部、眼口分层。鲸鱼发夹保留；手臂包含在身体贴图里。**未覆盖**带兽特征版本、桌宠面部试作、正式少女或正式 Q 版。

这是自研 C `zrig` 的 9 部件试装，并非 Cubism 工程或完成的模型。无兽特征是根据已有 AI 去耳/去尾补画生成，遮挡内容并非原始隐藏真值；无完整手臂/手型分层、网格、物理或长发等变体。头颈拼接及发丝边缘仍需精修。默认的细手尚未以用户要求的小巧手及手套感两套独立手件验收。形象需用户目视确认。

## 复现

```sh
# 如果源试装的素材需要重生，先使用有 Pillow/numpy 的 Python：
python3 tools/build_live2d_chibi_study.py
python3 tools/build_human_chibi_study.py
make build/zhuochong_preview
python3 tools/preview_live2d_chibi.py --human 5203
# 另开终端（需 Pillow/numpy；会临时修改预览状态）
python3 tools/capture_human_chibi_study.py
python3 tests/test_human_chibi_study.py
```

`qa/` 是真实 C 帧；`metrics.json` 是双眼、嘴和头部位移像素及头部动作时身体不变的检查，不等于美术验收。预览监听 `0.0.0.0` 且无认证，只适合可信隔离环境，勿放真实个人数据或密钥。
