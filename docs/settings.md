# Settings Guide | 设置指南

> This document covers every setting in the VideoMiner settings panel.
> 本文档涵盖 VideoMiner 设置面板中的所有选项。

The settings panel has **8 tabs**. Click a section below to jump to it.

设置面板共 **8 个标签页**，点击下方链接跳转。

| Tab | English | 中文 |
|-----|---------|------|
| [Model](#1-model-settings--模型设置) | LLM for splitting & translation | 断句与翻译 LLM |
| [Interface](#2-interface-settings--界面设置) | Language preferences | 界面语言 |
| [Subtitle](#3-subtitle-settings--字幕设置) | Font, color, styling | 字体、颜色、样式 |
| [Transcription](#4-transcription-engine--转录引擎) | ASR engine & VAD | 语音识别引擎 |
| [Media](#5-media-credentials--媒体凭据) | Bilibili, YouTube, proxy, yt-dlp | B站、YouTube、代理 |
| [API Token](#6-api-token-management--api-令牌管理) | REST API tokens | REST API 令牌 |
| [Video Understanding](#7-video-understanding--视频理解) | Local VLM models & corner detection | 本地视觉模型 |
| [Tags](#8-tags-management--标签管理) | Tag CRUD & colors | 标签管理 |

---

## 1. Model Settings | 模型设置

Configure LLM providers for subtitle sentence splitting and translation.

配置用于字幕断句和翻译的 LLM 服务。

### 1.1 Split LLM | 断句 LLM

Controls whether subtitles are re-split by an LLM for better readability after ASR transcription.

控制 ASR 转录后是否使用 LLM 对字幕进行智能断句重排，提升阅读体验。

| Setting | Type | Description |
|---------|------|-------------|
| **Enable LLM Split** `enableSplit` | Toggle | On = LLM re-splits sentences; Off = use raw ASR output directly. **开启**=LLM 智能断句；**关闭**=直接使用 ASR 原始输出。 |
| **Model Provider** `selectedModelProvider` | Dropdown | LLM service provider. 供应商选择（DeepSeek、OpenAI、OpenRouter 等）。 |
| **API Key** `splitApiKey` | Password | API key for the selected provider. 供应商 API 密钥。 |
| **Base URL** `splitBaseUrl` | URL | API endpoint base URL. Override for self-hosted or proxy. API 地址，自部署或代理时需修改。 |
| **Model Name** `splitModel` | Text | Specific model identifier, e.g. `deepseek-chat`, `gpt-4o-mini`. 模型名称。 |
| **Request Threads** `splitNumThreads` | Number (1–32) | Concurrent API requests. More = faster but higher rate-limit risk. 并发请求数，越大越快但可能触发限流。 |
| **Use Proxy** `splitUseProxy` | Toggle | Route API requests through the proxy configured in [Media](#5-media-credentials--媒体凭据). 是否通过代理访问 API。 |
| **Test Connection** | Button | Sends a test request to verify the API key and endpoint. 测试连接是否可用。 |

### 1.2 Translate LLM | 翻译 LLM

Independent LLM configuration for subtitle translation. Can use a different provider than Split LLM.

独立的翻译 LLM 配置，可与断句 LLM 使用不同供应商。

| Setting | Type | Description |
|---------|------|-------------|
| **Model Provider** `translateSelectedModelProvider` | Dropdown | Same options as Split LLM. 同断句 LLM。 |
| **API Key** `translateApiKey` | Password | API key for translation provider. 翻译 API 密钥。 |
| **Base URL** `translateBaseUrl` | URL | API endpoint for translation. 翻译 API 地址。 |
| **Model Name** `translateModel` | Text | Model for translation, e.g. `deepseek-chat`. 翻译模型。 |
| **Request Threads** `translateNumThreads` | Number (1–32) | Concurrent translation requests. 翻译并发数。 |
| **Use Proxy** `translateUseProxy` | Toggle | Route translation API through proxy. 翻译是否走代理。 |
| **Test Connection** | Button | Verify translation API connectivity. 测试翻译连接。 |
| **Plain Translation** `plainTranslate` | Checkbox | When enabled, produces a plain/literal translation without adapting subtitle timing. 开启后生成直译，不调整时间轴。 |

---

## 2. Interface Settings | 界面设置

| Setting | Type | Options | Description |
|---------|------|---------|-------------|
| **Interface Language** `rawLanguage` | Dropdown | `zh`, `en`, `jp`, `de` | UI display language. 界面显示语言。 |
| **Default Translate Language** `defaultTranslateLang` | Dropdown | `zh`, `en`, `jp`, `de` | Default target language when translating subtitles. 字幕翻译的默认目标语言。 |

> **Note**: Interface language only affects UI labels. Video content and subtitles remain in their original language.
>
> **注意**：界面语言仅影响 UI 文字，不影响视频和字幕的原始语言。

---

## 3. Subtitle Settings | 字幕设置

Customize subtitle appearance for both original and translated tracks. All changes show in a real-time preview.

自定义字幕外观，支持原文和译文独立配置，修改后实时预览。

### 3.1 Subtitle Type | 字幕类型

Toggle between editing **Original Subtitle** (raw transcription) and **Translated Subtitle** styling.

切换编辑**原文字幕**或**译文字幕**的样式。

### 3.2 Typography | 排版

| Setting | Type | Options / Range | Description |
|---------|------|-----------------|-------------|
| **Font Family** `fontFamily` | Dropdown | 宋体, 微软雅黑, Arial, Times New Roman, Helvetica | Font for subtitle text. 字体。 |
| **Font Size** `fontSize` | Slider | 12–48 px | Text size. 字号。 |
| **Font Color** `fontColor` | Color picker | Hex + presets | Text color. 文字颜色。 |
| **Font Weight** `fontWeight` | Buttons | normal / medium / bold | Text thickness. 文字粗细。 |
| **Preview Text** `previewText` | Text | Any string | Sample text for the preview box. 预览示例文字。 |

### 3.3 Background & Layout | 背景与布局

| Setting | Type | Options / Range | Description |
|---------|------|-----------------|-------------|
| **Background Style** `backgroundStyle` | Dropdown | `none` / `semi-transparent` / `solid` | Background behind text. 无背景 / 半透明 / 实心。 |
| **Background Color** `backgroundColor` | Color picker | Hex | Used when background style is not "none". 背景色。 |
| **Bottom Distance** `bottomDistance` | Slider | 20–200 px | Distance from subtitle to bottom of video. 字幕距底部距离。 |
| **Border Radius** `borderRadius` | Slider | 0–20 px | Corner roundness of background. 背景圆角。 |

### 3.4 Text Effects | 文字特效

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| **Text Shadow** `textShadow` | Toggle | On | Drop shadow for readability on bright scenes. 文字阴影，提升亮场景可读性。 |
| **Text Stroke** `textStroke` | Toggle | Off | Outline around text. 文字描边。 |
| **Stroke Color** `textStrokeColor` | Color | `#000000` | Outline color (visible when stroke is on). 描边颜色。 |
| **Stroke Width** `textStrokeWidth` | Slider (1–5 px) | 2 | Outline thickness. 描边粗细。 |

---

## 4. Transcription Engine | 转录引擎

Configure the Automatic Speech Recognition (ASR) engine for generating subtitles from audio.

配置语音识别（ASR）引擎，用于从音频生成字幕。

### 4.1 Engine Selection | 引擎选择

| Setting | Type | Description |
|---------|------|-------------|
| **Transcription Engine** `transcriptionPrimaryEngine` | Dropdown | Primary ASR engine. Available options depend on installed models. 主 ASR 引擎，可选项取决于已安装的模型。 |

> **Available engines** (after downloading corresponding models):
> - **Faster-Whisper** — Local, GPU-accelerated Whisper. Supports CUDA.
> - **Fun-ASR** — Alibaba's FunASR models (local).
> - **FunASR-GGUF** — Quantized FunASR in GGUF format for CPU inference.
> - **GLM-ASR** — GLM-based ASR (local).
> - **ElevenLabs** — Cloud-based Scribe API (requires API key).
> - **DashScope** — Alibaba Cloud API (requires API key).
> - **OpenAI Whisper** — OpenAI Cloud API (requires API key).

### 4.2 Advanced Settings | 高级设置

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| **Hotword List** `hotwords` | Textarea | (empty) | Custom vocabulary to bias the ASR engine toward specific terms (names, jargon, etc.). One word/phrase per line. 热词列表，引导识别引擎优先识别特定词汇（人名、术语等），每行一个。 |
| **VAD Backend** `vadBackend` | Dropdown | `silero` | Voice Activity Detection backend. `silero` = Silero VAD (default, lighter); `firered` = FireRed VAD (higher accuracy). 语音活动检测后端。 |

### 4.3 Engine-Specific Settings | 引擎专属设置

- **FunASR-GGUF**: Displays model specs and quantization info. No additional configuration needed.
- **ElevenLabs**: Requires `transcriptionElevenlabsApiKey` (API key field appears when selected).

---

## 5. Media Credentials | 媒体凭据

Manage authentication for streaming platforms, network proxy, and yt-dlp.

管理流媒体平台认证、网络代理和 yt-dlp。

### 5.1 Bilibili SESSDATA | B站 SESSDATA

| Setting | Type | Description |
|---------|------|-------------|
| **SESSDATA** `bilibiliSessData` | Password | Bilibili session cookie for downloading higher-quality streams and age-restricted content. B站会话 Cookie，用于下载高画质和年龄限制内容。 |
| **Save & Validate** | Button | Saves the SESSDATA and validates it against Bilibili API. Shows account username, UID, and expiration. 保存并验证，显示账号信息和过期时间。 |

> **How to get SESSDATA**: Open bilibili.com → F12 → Application → Cookies → `SESSDATA`. Copy the value.
>
> **如何获取 SESSDATA**：打开 bilibili.com → F12 → Application → Cookies → 复制 `SESSDATA` 的值。

### 5.2 YouTube cookies.txt

| Setting | Type | Description |
|---------|------|-------------|
| **cookies.txt** | File upload | Upload a Netscape-format cookies file for YouTube authentication (required for age-restricted or member-only content). 上传 Netscape 格式的 cookies 文件，用于 YouTube 认证。 |

> **How to get cookies.txt**: Install the [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) browser extension, log into YouTube, export the file, and upload it here.
>
> **如何获取**：安装 [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) 浏览器扩展，登录 YouTube 后导出文件，然后上传。

### 5.3 Network Proxy | 网络代理

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| **Proxy Server Address** `proxyUrl` | Text | (empty) | Proxy URL, e.g. `http://127.0.0.1:7890`. Also sets `HTTPS_PROXY` environment variable for backend processes. 代理地址，同时设置后端 `HTTPS_PROXY` 环境变量。 |
| **Download Use Proxy** `downloadUseProxy` | Checkbox | Off | Route general downloads through proxy. 通用下载走代理。 |
| **Bilibili Download Use Proxy** `biliDownloadUseProxy` | Checkbox | Off | Route Bilibili downloads through proxy. B站下载走代理。 |
| **Split LLM Use Proxy** `splitUseProxy` | Checkbox | Off | Route sentence-splitting LLM API through proxy. 断句 LLM 走代理。 |
| **Translate LLM Use Proxy** `translateUseProxy` | Checkbox | Off | Route translation LLM API through proxy. 翻译 LLM 走代理。 |

### 5.4 yt-dlp Management | yt-dlp 管理

Manage the yt-dlp engine and its dependencies (EJS script, Node.js runtime) used for YouTube and other platform downloads.

管理 yt-dlp 引擎及其依赖（EJS 脚本、Node.js 运行时），用于 YouTube 等平台下载。

| Action | Button | Description |
|--------|--------|-------------|
| **Install Dependencies** | Button | Installs/updates EJS script and required Node.js packages. 安装/更新 EJS 脚本和所需 Node.js 包。 |
| **Check for Upgrade** | Button | Checks if a newer yt-dlp version is available and upgrades if so. 检查并升级到最新版本。 |
| **Refresh Status** | Button | Re-fetches current versions of yt-dlp, EJS, and Node.js. 刷新当前版本信息。 |

**Status display shows**: yt-dlp version, EJS script version, Node.js version + availability, Node.js requirement.

**状态显示**：yt-dlp 版本、EJS 脚本版本、Node.js 版本及可用性、Node.js 版本要求。

---

## 6. API Token Management | API 令牌管理

Manage REST API authentication tokens for programmatic access (e.g., MCP tools, scripts, external integrations).

管理用于编程访问的 REST API 认证令牌（如 MCP 工具、脚本、外部集成）。

| Action | Description |
|--------|-------------|
| **Generate Token** | Creates a new API token. The token is shown once — copy it immediately. 创建新令牌，仅显示一次，请立即复制。 |
| **Token List** | Shows all active tokens with creation timestamps. 显示所有活跃令牌及创建时间。 |
| **Revoke** | Permanently deletes a token. The token stops working immediately. 永久删除令牌，立即生效。 |

> **Usage**: Pass the token in the `Authorization: Token <your-token>` header for API requests.
>
> **用法**：在 API 请求头中添加 `Authorization: Token <your-token>`。

---

## 7. Video Understanding | 视频理解

Configure local Vision-Language Models (VLM) for video summarization, note generation, and chapter detection.

配置本地视觉语言模型（VLM），用于视频摘要、笔记生成和章节检测。

### 7.1 Local Models | 本地模型

Download and manage local AI models. Each model shows download status, progress bar, and total size.

下载和管理本地 AI 模型，每个模型显示下载状态、进度条和总大小。

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| **Use Proxy for Downloads** `vuDownloadUseProxy` | Toggle | Off | Route model downloads through proxy. 模型下载走代理。 |
| **Download Source** | Dropdown per model | `hf` | Where to download from: `hf` (Hugging Face) or `ms` (ModelScope). 下载源：Hugging Face 或 ModelScope。 |

**Available model groups**:

| Model | Description | Size |
|-------|-------------|------|
| **MiniCPM-V** | Vision-language model for video frame understanding | ~5.5 GB |
| **GLM-OCR** | OCR model for extracting text from video frames | ~1.2 GB |
| **Fun-ASR** | Automatic speech recognition model | ~1.8 GB |
| **GLM-ASR** | GLM-based ASR model | ~900 MB |
| **Embedding** | Text embedding model for semantic search | ~400 MB |

### 7.2 Inference Parameters | 推理参数

| Setting | Type | Range | Default | Description |
|---------|------|-------|---------|-------------|
| **Thinking Budget** `vuThinkingBudget` | Dropdown | low / medium / high | medium | Controls how much "thinking" the VLM does before responding. Higher = more thorough but slower. 控制模型推理深度，越高越精确但越慢。 |
| **GPU Layers (VLM)** `vuNGpuLayers` | Number | 0–40 | 40 | Number of model layers offloaded to GPU. Set to 0 for CPU-only inference. 卸载到 GPU 的层数，0 表示纯 CPU 推理。 |
| **GPU Layers (GLM-OCR)** `vuGlmOcrNGpuLayers` | Number | 0–17 | 17 | GPU layers for the GLM-OCR model specifically. GLM-OCR 模型的 GPU 层数。 |

### 7.3 External Vision Corner Detection | 外部视觉角点检测

Uses a cloud VLM API for slide/frame corner detection (e.g., detecting presentation slides in lecture videos).

使用云端 VLM API 进行视频画面角点检测（如识别讲座视频中的幻灯片）。

| Setting | Type | Options | Description |
|---------|------|---------|-------------|
| **Provider** `vuCornerProvider` | Dropdown | `gemini` (OpenRouter), `gemini_official`, `mimo`, `openai_compatible` | Cloud VLM provider. 云端 VLM 供应商。 |
| **Use Proxy** `vuCornerUseProxy` | Toggle | — | Route corner detection API through proxy. 是否走代理。 |
| **Coverage Threshold** `vuCornerCoverage` | Slider | 0.3–1.0 (30%–100%) | Minimum frame coverage ratio required before triggering detection. Lower = more aggressive. 触发检测的最低帧覆盖率，越低越激进。 |
| **API Key** | Password | — | Provider-specific API key. 供应商 API 密钥。 |
| **Base URL** | Text | — | Provider-specific endpoint. 供应商 API 地址。 |
| **Model** | Text | — | Provider-specific model name. 模型名称。 |

> **Provider-specific defaults**:
> - **OpenRouter**: Base URL `https://openrouter.ai/api/v1`, Model `google/gemini-2.5-flash`
> - **Gemini Official**: Base URL `https://generativelanguage.googleapis.com/v1beta/openai`
> - **MiMo** / **OpenAI Compatible**: Configure Base URL and Model manually.

---

## 8. Tags Management | 标签管理

Create, rename, recolor, and delete tags used for organizing videos.

创建、重命名、重新着色和删除用于组织视频的标签。

| Action | Description |
|--------|-------------|
| **Create New Tag** | Enter a name, pick a color (or use a recommended preset / random color), click Create. 输入名称，选择颜色（推荐色/随机色），点击创建。 |
| **Rename Tag** | Click the edit icon next to a tag to rename it. 点击标签旁的编辑图标重命名。 |
| **Recolor Tag** | Click the color swatch to change a tag's color. 点击颜色块修改标签颜色。 |
| **Delete Tag** | Click the trash icon. Deleting a tag does not delete videos. 点击垃圾桶图标删除，删除标签不会删除视频。 |
| **Merge Tags** | Merge one tag into another, then the source tag is deleted and all its videos are reassigned. 将一个标签合并到另一个，源标签删除，视频自动转移。 |

**Default tag color**: `#3B82F6`

**Recommended color presets**: A curated palette is provided; you can also use a random color generator.

---

## FAQ | 常见问题

### Do settings require a restart? | 设置需要重启吗？

Most settings take effect immediately. The following require a backend restart:
- Proxy address changes (affects `HTTPS_PROXY` environment variable)
- Transcription engine switch (loads new model on next task)
- GPU layer count changes (reloads model with new offload config)

大多数设置即时生效。以下需要重启后端：代理地址变更、转录引擎切换、GPU 层数修改。

### Where are settings stored? | 设置存储在哪里？

Settings are stored in the backend's config file (`backend/config/config.ini`) and SQLite database. API tokens are stored in the database with hashed keys.

设置存储在后端配置文件和 SQLite 数据库中。API 令牌以哈希形式存储在数据库中。

### How do I reset settings? | 如何重置设置？

There is no "reset all" button. To reset individual settings, clear the field or select the default option. For a full reset, delete the config file and restart the backend (this will NOT delete your videos).

没有"全部重置"按钮。如需重置，清空对应字段或选择默认值。如需完全重置，删除配置文件后重启后端（不会删除视频）。
