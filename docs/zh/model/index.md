# 模型设置

模型设置用于配置字幕断句和字幕翻译使用的大语言模型 (LLM)。当前面板把断句 LLM (Split LLM) 与翻译 LLM (Translate LLM) 分开保存，因此两类任务可以使用不同供应商、模型和代理策略。

## 断句 LLM (Split LLM)

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 启用 LLM 断句 | 开关 | 开启 | 开启后使用 LLM 对 ASR 输出进行断句。关闭后使用 ASR 直接断句。 |
| 模型供应商 | 下拉框 | DeepSeek | 可选 DeepSeek、OpenAI、Qwen、Ollama、LM Studio、Moonshot、火山引擎、OpenRouter、Cerebras。 |
| API Key | 密码输入 | 按供应商配置 | 当前供应商的访问密钥。界面支持复制按钮，不应公开保存到文档或截图。 |
| Base URL | URL 输入 | 随供应商变化 | 当前供应商的接口地址，例如 DeepSeek 默认使用 `https://api.deepseek.com`。 |
| 模型名称 | 文本输入 | 随供应商变化 | 当前供应商调用的模型名，例如 DeepSeek 默认 `deepseek-chat`。 |
| 请求线程数 | 数字输入 | 8 | 并发请求数量，范围 1 到 32。 |
| 使用代理 | 开关 | 关闭 | 开启后断句请求使用媒体凭据页的代理地址。 |
| 测试连接 | 按钮 | 无 | 保存设置后发起断句 LLM 连接测试。 |

## 翻译 LLM (Translate LLM)

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 模型供应商 | 下拉框 | DeepSeek | 可选 DeepSeek、OpenAI、Qwen、Ollama、LM Studio、Moonshot、火山引擎、OpenRouter、Cerebras。 |
| API Key | 密码输入 | 空 | 当前翻译供应商的访问密钥。 |
| Base URL | URL 输入 | 随供应商变化 | 当前翻译供应商的接口地址。 |
| 模型名称 | 文本输入 | 随供应商变化 | 当前翻译供应商调用的模型名。 |
| 请求线程数 | 数字输入 | 8 | 并发请求数量，范围 1 到 32。 |
| 使用代理 | 开关 | 关闭 | 开启后翻译请求使用媒体凭据页的代理地址。 |
| 测试连接 | 按钮 | 无 | 保存设置后发起翻译 LLM 连接测试。 |
| 启用单句翻译 | 复选框 | 关闭 | 面向本地 vLLM 部署的翻译模型，例如 Hunyuan-MT-7B，不要求 JSON 格式输出。 |

## 供应商默认模型

| 供应商 | Base URL 默认值 | 模型默认值 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| OpenAI | `https://api.chatanywhere.tech/v1` | `gpt-4o` |
| Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Ollama | `http://127.0.0.1:11434` | `llama3` |
| LM Studio | `http://localhost:1234/v1` | 空 |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 火山引擎 | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-2-0-lite-260428` |
| OpenRouter | `https://openrouter.ai/api/v1` | `google/gemini-3-flash` |
| Cerebras | `https://api.cerebras.ai/v1` | `llama3.1-8b` |

## 如何测试连接

1. 选择供应商。
2. 填写 API Key、Base URL 和模型名称。
3. 按需开启代理。
4. 点击测试连接。

> 测试连接会先保存当前设置，再调用后端测试接口。代理地址在[媒体凭据](../media/)中配置。

---

[返回中文文档首页](../) | 上一节：无 | [下一节：界面设置](../interface/)
