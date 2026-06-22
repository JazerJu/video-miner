# Model Settings

Model Settings: configure the large language models (LLMs) used for subtitle splitting and subtitle translation. The current panel stores Split LLM and Translate LLM settings separately, so the two task types can use different providers, models, and proxy strategies.

## Split LLM

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Enable LLM Split | Switch | On | When enabled, uses an LLM to optimize sentence splitting from ASR character-level timestamps. When off, ASR direct sentence splitting is used. |
| Model Provider | Select | DeepSeek | Options are DeepSeek, OpenAI, Qwen, Ollama, LM Studio, Moonshot, Volcano Engine, OpenRouter, and Cerebras. |
| API Key | Password input | Provider specific | Access key for the selected provider. The UI supports a copy button, and the key should not be saved publicly in docs or screenshots. |
| Base URL | URL input | Provider specific | API endpoint for the selected provider. DeepSeek defaults to `https://api.deepseek.com`. |
| Model Name | Text input | Provider specific | Model called by the selected provider. DeepSeek defaults to `deepseek-chat`. |
| Request Threads | Number input | 8 | Concurrent request count. Range is 1 to 32. |
| Use Proxy | Switch | Off | Sends split requests through the proxy configured in Media Credentials. |
| Test Connection | Button | None | Saves settings and tests the Split LLM connection. |

## Translate LLM

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Model Provider | Select | DeepSeek | Options are DeepSeek, OpenAI, Qwen, Ollama, LM Studio, Moonshot, Volcano Engine, OpenRouter, and Cerebras. |
| API Key | Password input | Empty | Access key for the selected translation provider. |
| Base URL | URL input | Provider specific | API endpoint for the selected translation provider. |
| Model Name | Text input | Provider specific | Model called by the selected translation provider. |
| Request Threads | Number input | 8 | Concurrent request count. Range is 1 to 32. |
| Use Proxy | Switch | Off | Sends translation requests through the proxy configured in Media Credentials. |
| Test Connection | Button | None | Saves settings and tests the Translate LLM connection. |
| Enable single-sentence translation<sup>1</sup> | Checkbox | Off | For local vLLM translation models such as Hunyuan-MT-7B. JSON output is not required. |

![]()

> <sup>1</sup>: Local translation models can hallucinate, so they cannot keep JSON output while accurately translating multiple sentences. They also tend to automatically complete context when translating incomplete sentences. For this mode, sentences are joined and translated by period. The drawback is that the restored split positions after translation are not guaranteed.

## Provider defaults

| Provider | Default Base URL | Default Model |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| OpenAI<sup>2</sup> | `https://api.chatanywhere.tech/v1` | `gpt-4o` |
| Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Ollama | `http://127.0.0.1:11434` | `llama3` |
| LM Studio | `http://localhost:1234/v1` | Empty |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| Volcano Engine | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-2-0-lite-260428` |
| OpenRouter | `https://openrouter.ai/api/v1` | `google/gemini-3-flash` |
| Cerebras<sup>3</sup> | `https://api.cerebras.ai/v1` | `llama3.1-8b` |

> <sup>2</sup>: Compatible with all OpenAI-format requests.
> <sup>3</sup>: Cerebras provides a limited amount of free API quota for registered users.

## How to test a connection

1. Choose a provider.
2. Enter the API key, Base URL, and model name.
3. Enable proxy if needed.
4. Click Test Connection.

> Connection tests save the current settings before calling the backend test endpoint. Configure the shared proxy in [Media Credentials](../media/).

---

[Back to English docs](../) | Previous: none | [Next: Interface Settings](../interface/)
