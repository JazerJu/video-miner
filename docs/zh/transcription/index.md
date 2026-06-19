# 转录引擎

转录引擎设置控制音频转文字时使用的后端。当前设置面板提供本地 Fun-ASR-GGUF、本地 GLM-ASR Stack 和 ElevenLabs Speech-to-Text。

## 基础设置

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 转录引擎 | 下拉框 | Fun-ASR-Nano (ONNX + GGUF，本地 GPU 加速) | 可选 Fun-ASR-Nano、GLM-ASR Stack、ElevenLabs Speech-to-Text。 |
| 热词表 | 多行文本 | 空 | 每行一个热词。以 `#` 开头的行作为注释。 |
| VAD Backend | 下拉框 | Silero VAD | 可选 Silero VAD 和 FireRed VAD。 |

## 引擎说明

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| FunASR-GGUF 信息 | 条件信息块 | 选择 Fun-ASR-Nano 时显示 | 本地引擎，包含 CTC 硬对齐和 Qwen3 解码器，中文优化，字级 CTC 时间戳，约 1.5GB 显存，无需 API Key。 |
| ElevenLabs API Key | 密码输入 | 空 | 仅在选择 ElevenLabs Speech-to-Text 时显示。 |

## 热词格式

```text
# 人名
撒贝宁
CapsWriter
iPhone
```

## 如何选择转录引擎

1. 优先选择本地引擎处理私有音频。
2. 需要云端高质量多语言转录时选择 ElevenLabs，并填写 API Key。
3. 如果语音活动检测效果不理想，可以在 Silero VAD 和 FireRed VAD 之间切换。

> 当前设置面板只显示以上三个转录引擎。旧文档或部署脚本中出现的 Faster-Whisper、DashScope、OpenAI 等选项不属于当前面板选项。

---

[返回中文文档首页](../) | [上一节：字幕设置](../subtitle/) | [下一节：媒体凭据](../media/)
