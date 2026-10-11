# voices/ — 音色包目录

把**下载到的音色**放进这里即可使用，**不需要改任何代码**（对应交接文件的"全部可自定义"原则）。

## 音色包格式

```
voices/<音色id>/
    model.onnx          # ONNX 语音模型（当前支持 Piper VITS 格式）
    model.onnx.json     # 与模型配套的配置（音素表、采样率等）
    meta.json           # 元数据（名称、语言、性别、年龄感、许可、来源）
    sample.wav          # 试听样音（install 时自动生成）
```

`meta.json` 示例：

```json
{
  "id": "my_young_voice",
  "name": "我的少女音",
  "lang": "zh-CN",
  "gender": "female",
  "age": "少女(16)",
  "license": "Apache-2.0",
  "source": "https://example.com/voice-pack",
  "note": "训练数据许可：xxx"
}
```

`license` 与 `source` **必填**（合规要求，见 `docs/VOICES.md`）。

## 用法

```bash
# 安装（目录或 zip 都行；会校验能不能真跑出声音，并生成试听样音）
python3 tools/voice_packs.py install ~/Downloads/某个音色包.zip --id xiaoxun_girl

# 列出已装音色（含语言、年龄感、许可）
python3 tools/voice_packs.py list

# 校验
python3 tools/voice_packs.py verify xiaoxun_girl

# 用这个音色合成（psola=只抬基频保共振峰，少女化的推荐做法）
python3 tools/voice_local.py --voice xiaoxun_girl \
    --text "你好呀，我是小寻。" --out /tmp/a.wav --pitch 1.25 --shift-method psola
```

选好音色后，把它写进 `config/voices.json`（角色 → 音色映射）即可让软件使用。
