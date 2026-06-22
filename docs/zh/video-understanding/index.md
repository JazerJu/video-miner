# 视频理解

视频理解设置用于管理本地模型、视频片段分析参数、外部视觉角点检测、摘要编排和知识补充 LLM。当前设置面板中的模型下载来源支持 HuggingFace 和 ModelScope。

## 本地模型

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 下载使用代理 | 开关 | 关闭 | 本地模型下载使用媒体凭据页的代理地址。 |
| 下载来源 | 下拉框 | HuggingFace | 每个模型可单独选择 HuggingFace (`hf`) 或 ModelScope (`modelscope`)。 |
| MiniCPM-V 4.5 | 模型项 | 未下载 | SigLip encoder + 3D-resampler + LLM decoder，约 6.88GB。 |
| GLM-OCR | 模型项 | 未下载 | OCR engine，约 1.40GB。 |
| BGE Embedding (ONNX) | 模型项 | 未下载 | 文本向量模型，ONNX runtime，约 95MB。 |
| FUN-ASR Nano | 模型项 | 未下载 | Fun-ASR speech recognition，ONNX + GGUF，约 988MB。 |
| GLM-ASR Stack | 模型项 | 未下载 | GLM-ASR Nano + Qwen3 ForceAligner，约 6.37GB。 |
| 下载按钮 | 按钮 | 下载 | 根据状态显示下载、重新下载、重试或下载中。 |

## 推理参数

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| Thinking Budget | 下拉框 | Low (7 帧) | 控制每个视频片段采样的帧数。可选 Low (7 帧)、Medium (14 帧)、High (21 帧)。 |

> 由于本地小型语言模型具有一定幻觉，长视频以"Low"采样已经具备相当可观的总结质量。短视频可以酌情增加采样帧率，增加信息的获取，但并不能较大改善"幻觉"。


## 外部视觉角点检测

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 角点检测 Provider | 下拉框 | OpenRouter (Gemini as default) | 可选 OpenRouter、Gemini Official、MiMo、OpenAI Compatible。 |
| 使用代理 | 开关 | 关闭 | 角点检测请求使用代理。 |
| 最小裁切覆盖率<sup>1</sup>  | 滑块 | 0.6 | 范围 0.3 到 1.0，步进 0.05。低值裁切更激进。 |
| API Key | 密码输入 | 空 | 当前角点检测供应商的密钥。 |
| Base URL | 文本输入 | 随供应商变化 | 当前角点检测供应商的接口地址。 |
| Model | 文本输入 | 随供应商变化 | 当前角点检测供应商的模型名。 |

> <sup>1</sup>： 最小裁切覆盖率，外部模型返回的视觉角点，构成的矩形小于原始图片的"最小裁切覆盖率"，则该图片不裁切。

## 角点检测供应商默认值

> 角点检测用于识别视频画面中幻灯片或演示文稿的边界（如讲座、 keynote 视频），自动裁切画面中的有效区域，提升后续 OCR 和帧分析的准确率。

| 供应商 | Base URL 默认值 | Model 默认值 |
| --- | --- | --- |
| OpenRouter | `https://openrouter.ai/api/v1` | `google/gemini-2.5-flash` |
| Gemini Official | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.5-flash` |
| MiMo | 空 | `mimo-v2.5` |
| OpenAI Compatible | 空 | 空 |

## 摘要编排 (Tool-Calling)

> 摘要编排是视频总结的核心调度器，通过 Tool-Calling 能力协调本地 VLM（帧理解）、OCR（文字提取）、Embedding（语义检索）等工具，按片段汇总并生成结构化的视频摘要。

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| Provider | 下拉框 | DeepSeek | 可选 DeepSeek 和 OpenAI Compatible。 |
| 使用代理 | 开关 | 关闭 | 摘要编排请求使用代理。 |
| API Key | 密码输入 | 空 | 摘要编排供应商密钥。 |
| Base URL | 文本输入 | `https://api.deepseek.com` | 摘要编排接口地址。 |
| Model | 文本输入 | `deepseek-chat` | 摘要编排模型名。 |

## 知识补充 LLM (Knowledge LLM)

> 知识补充 LLM 在摘要生成后对内容进行二次加工，补充视频中没有直接提及的背景知识、术语解释和关联信息，让最终摘要更完整易懂。

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

---

[返回中文文档首页](../) | [上一节：API 令牌](../api-token/) | [下一节：标签管理](../tags/)
