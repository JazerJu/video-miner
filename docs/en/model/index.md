# Model Settings

Model Settings configure the large language models used for subtitle splitting and subtitle translation. Split LLM and Translate LLM are stored separately, so each task can use its own provider, model, concurrency, and proxy behavior.

## Split LLM

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Enable LLM Split | Switch | On | Uses an LLM to split ASR output into subtitle sentences. When off, ASR direct sentence splitting is used. |
| Model Provider | Select | DeepSeek | Options are DeepSeek, OpenAI, Qwen, Ollama, LM Studio, Moonshot, Volcano Engine, OpenRouter, and Cerebras. |
| API Key | Password input | Provider specific | Access key for the selected provider. Treat it as a secret. |
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
| Model Name | Text input | Provider specific | Model called for subtitle translation. |
| Request Threads | Number input | 8 | Concurrent request count. Range is 1 to 32. |
| Use Proxy | Switch | Off | Sends translation requests through the proxy configured in Media Credentials. |
| Test Connection | Button | None | Saves settings and tests the Translate LLM connection. |
| Enable single-sentence translation | Checkbox | Off | Adapts translation for local vLLM models such as Hunyuan-MT-7B. JSON output is not required. |

## Provider defaults

| Provider | Default Base URL | Default Model |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| OpenAI | `https://api.chatanywhere.tech/v1` | `gpt-4o` |
| Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Ollama | `http://127.0.0.1:11434` | `llama3` |
| LM Studio | `http://localhost:1234/v1` | Empty |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| Volcano Engine | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-2-0-lite-260428` |
| OpenRouter | `https://openrouter.ai/api/v1` | `google/gemini-3-flash` |
| Cerebras | `https://api.cerebras.ai/v1` | `llama3.1-8b` |

## How to test a connection

1. Choose a provider.
2. Enter the API key, Base URL, and model name.
3. Enable proxy if needed.
4. Click Test Connection.

> Connection tests save the current settings before calling the backend test endpoint. Configure the shared proxy in [Media Credentials](../media/).

---

[Back to English docs](../) | Previous: none | [Next: Interface Settings](../interface/)
