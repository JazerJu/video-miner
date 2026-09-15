<p align="center">
  <img src="docs/images/logo.svg" width="100" />
</p>

<h2 align="center">VideoMiner</h2>

<p align="center">
  Local-first long-video understanding for AI agents.<br>
  GPU transcription at 540x real time, chapter summaries with code and slides, and MCP tools to search and read.
</p>

<p align="center">
  <img src="https://img.shields.io/github/v/release/JazerJu/video-miner?display_name=tag" />
  <img src="https://github.com/JazerJu/video-miner/actions/workflows/ci.yml/badge.svg?branch=main" />
  <img src="https://codecov.io/gh/JazerJu/video-miner/graph/badge.svg?branch=main" />
</p>

---

## Motivation

Luo Fuli, head of Xiaomi's MiMo LLM team, mentioned in an interview that OpenClaw's audio-video understanding capability is weak, which is why their lab open-sourced the omni-modal model MiMo v2.5.

<p align="center">
  <img src="docs/images/luofuli.en.png" width="500" />
</p>

In our daily work:
- We want to record a screen and have AI summarize what we did.
- When watching code walkthrough videos — whether traditional web dev or cutting-edge CUDA kernels — we want to generate a summary with the actual code extracted,and ask questions based on the summaries.

<p align="center">
  <img src="docs/images/youtube.en.png" width="500" />
</p>

---

However, relying purely on large LLMs for video understanding has two hard blockers:

1. **Prohibitively expensive.** Even the most cost-effective plans with no weekly limits (e.g., Zhipu AI's legacy tier) can't sustain it.

<p align="center">
  <img src="docs/images/z-ai-coding-plan.en.png" width="400" />
</p>

2. **Real-time factor < 1.** An LLM takes more than 30 seconds to answer a question about a 30-second video. For 1-2 hour or even 11-hour videos, a pure-LLM approach is simply impractical.

The second problem is ASR throughput: the popular Faster-Whisper achieves only ~10x RTFx in practice. Tweaking batch size or upgrading from a 4060 Ti to a 5070 Ti makes no difference. But on consumer GPUs, combining KV Cache, Paged Attention, and Flash Attention tuning, this rate can reach **540+ RTFx** — **50× faster** than Faster-Whisper.

<p align="center">
  <img src="docs/images/faster-whisper-bench.png" width="500" />
</p>

This is exactly the problem VideoMiner solves.

---

## Features

VideoMiner is **local-first**. The local GPU does the expensive work on audio and frames: transcription, OCR, and embeddings. A cloud LLM only reads text, to find chapters, write summaries, translate, and answer questions. Hours-long videos stay cheap and fast to process, and AI agents get the results as text through MCP.

### Ultra-Fast Transcription Engine

- **GLM-ASR Stack**: Built on GLM-ASR-Nano + Qwen3 ForceAligner, with KV Cache, Paged Attention, and Flash Attention tuning. Achieves **540+ RTFx** on consumer GPUs (~50× Faster-Whisper). A 1-hour video takes only ~15-20 seconds for transcription + forced alignment.
- **Fun-ASR-GGUF**: Quantized Fun-ASR for broad compatibility. Supports hotword guidance and switchable VAD backends (Silero / FireRed).
- **ElevenLabs Scribe**: Cloud API alternative for environments without a GPU.

### Local Video Understanding

Instead of sending video to a cloud LLM, the entire pipeline runs locally:

1. **Frame Sampling**: Samples key frames based on Thinking Budget (Low / Medium / High)
2. **OCR Extraction**: GLM-OCR recognizes text in frames
3. **Corner Detection**: A cloud VLM (Gemini / MiMo-V2.5, etc.) detects slide boundaries; cropped frames are sent back to OCR for improved accuracy on lecture videos
4. **Semantic Retrieval**: BGE Embedding builds a frame vector index
5. **Chapter Summaries**: An LLM reads the transcript and on-screen text to find chapters, then writes a summary for each chapter with its slides and code

### Smart Subtitle System

- **LLM Sentence Splitting**: Word-level ASR timestamps are re-segmented by an LLM for natural readability
- **Multi-Language Translation**: Independently configurable translation LLM provider, with proxy support, concurrency control, and plain-translation mode
- **Subtitle Editor**: Waveform visualization, real-time preview, dual-language subtitles, custom styling (font / color / shadow / stroke), and a fullscreen table to edit every line
- **Burned-in Subtitle Extraction**: Draw a box over the subtitles in one frame. OCR reads that region through the whole video and writes a subtitle file
- **Subtitle Fonts**: Upload TTF, OTF, WOFF, or WOFF2 fonts, or use a font that is installed on the device. Uploaded fonts work on every device
- **Hardcoded Subtitle Export**: Burn subtitles directly into video files

### Video Management

- Download from Bilibili, YouTube, Apple Podcasts, and more
- Hierarchical organization with Folders and Tags
- Batch operations: move, delete, merge, bulk subtitle generation
- Built-in player: chapter navigation, subtitle panel, dual-language toggle, loop count, infinite loop, and autoplay of the next video

### MCP Tool Integration

Built-in MCP Server lets AI agents (Claude Code, OpenCode, Pi Agent, Claude Desktop) work with the video library directly. Agents read subtitles and on-screen text for any time range, grab frames, open chapter outlines, fetch summaries, and manage tags and folders. Each result has a link that opens the video at that time.

**Clip search**: `find_clips` returns the 10-second clips that match a description of what is said or shown. It uses WeMM-Embedding-4B, which encodes the subtitles, on-screen text, and frames of each clip into one vector. The encoder runs on ONNX Runtime and does not need PyTorch. Download the model in Settings (3.41 GB), then build the index with `submit_clip_index_task`. See [measured speed and retrieval quality](docs/en/deployment.md#wemm-clip-search-on-onnx-runtime).

See [Using Video-Miner MCP in OpenCode](docs/en/api-token/index.md)

---

## Summary Examples

The following examples demonstrate VideoMiner's structured summaries for CUDA course lectures.

| Lecture | YouTube | English Summary |
|---------|---------|-----------------|
| **Lecture 5: Performance Considerations** | [▶ Watch](https://www.youtube.com/watch?v=x5trGVMKTdY) | [📄 View Summary](https://github.com/JazerJu/video-parsing/blob/main/summary_export_examples/lecture5-720p-en_summary.md) |
| **Lecture 8: 2D Convolution CUDA Implementation** | [▶ Watch](https://www.youtube.com/watch?v=mVGY1i8iYxs) | [📄 View Summary](https://github.com/JazerJu/video-parsing/blob/main/summary_export_examples/lecture-08-convolution_summary.md) |

---

## Interface Preview

### Media Library

Grid view organized by folders, tags, and collections, with batch operations and search.

<p align="center">
  <img src="docs/images/preview-library.en.png" width="600" />
</p>

### Video Player

Integrated subtitle panel, chapter navigation, notes, and mind map.

<p align="center">
  <img src="docs/images/preview-video-player.en.png" width="600" />
</p>

### Subtitle Editor

Waveform alignment, real-time preview, and style adjustment.

<p align="center">
  <img src="docs/images/preview-subtitle-editor.en.png" width="600" />
</p>

### Burned-in Subtitle Extraction

Drag a box over the subtitles, choose the sample rate, and start the extraction.

<p align="center">
  <img src="docs/images/hardsub-extract.en.png" width="600" />
</p>

### Subtitle Fonts

Upload a font file in Subtitle Style, then choose it for the original or the translated subtitles.

<p align="center">
  <img src="docs/images/subtitle-font-upload.en.png" width="600" />
</p>

### Settings Panel

8 tabs covering models, transcription engine, subtitle styling, media credentials, video understanding, API tokens, tags, and folder management.

<p align="center">
  <img src="docs/images/preview-settings.en.png" width="600" />
</p>

---

## Documentation

See [Documentation](docs/en/index.md)

---

## Docker Deployment

### Prerequisites

- Docker 24+
- NVIDIA driver + [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- Recommended GPU VRAM ≥ 8GB

### Quick Start

```bash
git clone https://github.com/JazerJu/video-miner.git
cd video-miner
cp .env.example .env
mkdir -p data/{media,config,models}
touch data/videos.db
docker compose up -d
```

Open `http://localhost:8080` in your browser.

> Full deployment guide (GPU parameters, port config, data persistence, proxy, MCP service): [Docker Deployment](docs/en/deployment.md).
>
> Need to build from source? See [Build from Scratch](docs/en/build-from-scratch.md).
>
> The image includes onnxruntime-gpu 1.30.0 built for CUDA 12.8, because PyPI only ships CUDA 13 builds of this version. To rebuild the wheel, see [docker/onnxruntime-wheel](docker/onnxruntime-wheel/).

---

## Roadmap

NVIDIA's CUDA ecosystem is indeed easy to use, but consumer GPUs have skyrocketed in price — the 5090 is selling at nearly double MSRP.
My lab happens to have 8×910B and 8×310B Ascend clusters, so the next step is:

- [ ] Optimize the project for Ascend NPU

---

## Acknowledgments

1. [Fun-ASR-GGUF](https://github.com/HaujetZhao/Fun-ASR-GGUF) / [Fun-ASR](https://github.com/FunAudioLLM/Fun-ASR) — Fun-ASR model and ONNX + llama.cpp collaboration approach
2. [GLM-ASR](https://github.com/zai-org/GLM-ASR) / [GLM-OCR](https://github.com/zai-org/GLM-OCR) — GLM-ASR and GLM-OCR models
3. [MiniCPM-V](https://github.com/OpenBMB/MiniCPM-V) — Best high-FPS local video understanding model
4. [WeMM-Embedding](https://huggingface.co/tencent/WeMM-Embedding-4B) — Video and text embedding model for clip search
5. [ONNX Runtime](https://github.com/microsoft/onnxruntime) / [mobius](https://github.com/onnxruntime/mobius) — GatedDeltaNet operator and the ONNX export of WeMM
