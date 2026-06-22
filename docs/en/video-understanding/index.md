# Video Understanding

Video Understanding settings manage local models, clip analysis parameters, external vision corner detection, summary orchestration, and the Knowledge LLM. The current model download sources are HuggingFace and ModelScope.

## Local Models

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Use proxy for downloads | Switch | Off | Downloads local models through the proxy configured in Media Credentials. |
| Download From | Select | HuggingFace | Each model can use HuggingFace (`hf`) or ModelScope (`modelscope`). |
| MiniCPM-V 4.5 | Model item | Not downloaded | SigLip encoder + 3D-resampler + LLM decoder, about 6.88GB. |
| GLM-OCR | Model item | Not downloaded | OCR engine, about 1.40GB. |
| BGE Embedding (ONNX) | Model item | Not downloaded | Text embedding model, ONNX runtime, about 95MB. |
| FUN-ASR Nano | Model item | Not downloaded | Fun-ASR speech recognition, ONNX + GGUF, about 988MB. |
| GLM-ASR Stack | Model item | Not downloaded | GLM-ASR Nano + Qwen3 ForceAligner, about 6.37GB. |
| Download button | Button | Download | Shows Download, Re-download, Retry, or Downloading based on model status. |

## Inference Parameters

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Thinking Budget | Select | Low (7 frames) | Controls frames sampled per video clip. Options are Low (7 frames), Medium (14 frames), and High (21 frames). |

> Because local small language models can hallucinate, long videos already have fairly strong summary quality with Low sampling. For short videos, you can increase the sampled frame rate to get more information, but it does not greatly reduce hallucination.

## External Vision Corner Detection

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Corner Detection Provider | Select | OpenRouter (Gemini as default) | Options are OpenRouter, Gemini Official, MiMo, and OpenAI Compatible. |
| Use Proxy | Switch | Off | Sends corner detection requests through the proxy. |
| Min Crop Coverage<sup>1</sup> | Slider | 0.6 | Range is 0.3 to 1.0, step 0.05. Lower values crop more aggressively. |
| API Key | Password input | Empty | Key for the selected corner detection provider. |
| Base URL | Text input | Provider specific | Endpoint for the selected corner detection provider. |
| Model | Text input | Provider specific | Model name for the selected corner detection provider. |

> <sup>1</sup>: Min Crop Coverage means that if the rectangle formed by the visual corners returned by the external model is smaller than the original image's minimum crop coverage, that image is not cropped.

## Corner detection provider defaults

> Corner detection identifies slide or presentation boundaries in video frames (e.g., lectures, keynotes), automatically cropping the relevant region to improve downstream OCR and frame analysis accuracy.

| Provider | Default Base URL | Default Model |
| --- | --- | --- |
| OpenRouter | `https://openrouter.ai/api/v1` | `google/gemini-2.5-flash` |
| Gemini Official | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.5-flash` |
| MiMo | Empty | `mimo-v2.5` |
| OpenAI Compatible | Empty | Empty |

## Summary Orchestration

> Summary orchestration is the core scheduler for video summarization. It uses Tool-Calling to coordinate local VLM (frame understanding), OCR (text extraction), and Embedding (semantic retrieval) tools, aggregating per-clip results into a structured video summary.

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Provider | Select | DeepSeek | Options are DeepSeek and OpenAI Compatible. |
| Use Proxy | Switch | Off | Sends summary orchestration requests through the proxy. |
| API Key | Password input | Empty | Key for the summary orchestration provider. |
| Base URL | Text input | `https://api.deepseek.com` | Endpoint for summary orchestration. |
| Model | Text input | `deepseek-chat` | Model used for summary orchestration. |

## Knowledge LLM

> The Knowledge LLM enriches the generated summary with background context, terminology explanations, and related information not directly mentioned in the video, making the final output more complete and easier to understand.

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Provider | Select | Doubao | Options are Doubao, StepFun, OpenRouter, and OpenAI Compatible. |
| Use Proxy | Switch | Off | Sends Knowledge LLM requests through the proxy. |
| API Key | Password input | Empty | Key for the Knowledge LLM provider. |
| Base URL | Text input | Empty | Endpoint for the Knowledge LLM provider. |
| Model | Text input | Empty | Model used by the Knowledge LLM provider. |

## How to download local models

1. Enable download proxy if needed.
2. Choose a download source for each model.
3. Click Download.
4. Wait for the progress bar to finish.

---

[Back to English docs](../) | [Previous: API Token Management](../api-token/) | [Next: Tags Management](../tags/)
