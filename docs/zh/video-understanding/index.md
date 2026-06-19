# 视频理解

视频理解设置用于管理本地模型、视频片段分析参数、外部视觉角点检测、摘要编排和知识补充 LLM。当前设置面板中的模型下载来源支持 HuggingFace 和 ModelScope。

## 本地模型

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 下载使用代理 | 开关 | 关闭 | 本地模型下载使用媒体凭据页的代理地址。 |
| 下载来源 | 下拉框 | HuggingFace | 每个模型可单独选择 HuggingFace (`hf`) 或 ModelScope (`modelscope`)。 |
| MiniCPM-V 4.5 | 模型项 | 未下载 | Vision encoder + LLM decoder，约 6.88GB。 |
| GLM-OCR | 模型项 | 未下载 | OCR engine，约 1.40GB。 |
| BGE Embedding (ONNX) | 模型项 | 未下载 | 文本向量模型，ONNX runtime，无需 torch，约 95MB。 |
| FUN-ASR Nano | 模型项 | 未下载 | Fun-ASR speech recognition，ONNX + GGUF，约 988MB。 |
| GLM-ASR Stack | 模型项 | 未下载 | GLM-ASR Nano + Qwen3 ForceAligner，约 6.37GB。 |
| 下载按钮 | 按钮 | 下载 | 根据状态显示下载、重新下载、重试或下载中。 |

## 推理参数

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| Thinking Budget | 下拉框 | Low (7 帧) | 控制每个视频片段采样的帧数。可选 Low (7 帧)、Medium (14 帧)、High (21 帧)。 |

## 外部视觉角点检测

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 角点检测 Provider | 下拉框 | OpenRouter (Gemini as default) | 可选 OpenRouter、Gemini Official、MiMo、OpenAI Compatible。 |
| 使用代理 | 开关 | 关闭 | 角点检测请求使用代理。 |
| 最小裁切覆盖率 | 滑块 | 0.6 | 范围 0.3 到 1.0，步进 0.05。低值裁切更激进。 |
| API Key | 密码输入 | 空 | 当前角点检测供应商的密钥。 |
| Base URL | 文本输入 | 随供应商变化 | 当前角点检测供应商的接口地址。 |
| Model | 文本输入 | 随供应商变化 | 当前角点检测供应商的模型名。 |

## 角点检测供应商默认值

| 供应商 | Base URL 默认值 | Model 默认值 |
| --- | --- | --- |
| OpenRouter | `https://openrouter.ai/api/v1` | `google/gemini-2.5-flash` |
| Gemini Official | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.5-flash` |
| MiMo | 空 | `mimo-v2.5` |
| OpenAI Compatible | 空 | 空 |

## 摘要编排 (Tool-Calling)

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| Provider | 下拉框 | DeepSeek | 可选 DeepSeek 和 OpenAI Compatible。 |
| 使用代理 | 开关 | 关闭 | 摘要编排请求使用代理。 |
| API Key | 密码输入 | 空 | 摘要编排供应商密钥。 |
| Base URL | 文本输入 | `https://api.deepseek.com` | 摘要编排接口地址。 |
| Model | 文本输入 | `deepseek-chat` | 摘要编排模型名。 |

## 知识补充 LLM (Knowledge LLM)

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| Provider | 下拉框 | Doubao | 可选 Doubao、StepFun、OpenRouter、OpenAI Compatible。 |
| 使用代理 | 开关 | 关闭 | 知识补充请求使用代理。 |
| API Key | 密码输入 | 空 | 知识补充供应商密钥。 |
| Base URL | 文本输入 | 空 | 知识补充接口地址。 |
| Model | 文本输入 | 空 | 知识补充模型名。 |

## 如何下载本地模型

1. 按需开启下载使用代理。
2. 为每个模型选择下载来源。
3. 点击下载。
4. 等待进度条完成。

> 当前设置面板没有 GPU Layers 数字输入项。若部署文档提到 GPU 层数，请以当前版本设置面板为准。

---

[返回中文文档首页](../) | [上一节：API 令牌](../api-token/) | [下一节：标签管理](../tags/)
