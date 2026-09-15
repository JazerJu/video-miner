# Docker Deployment

Deploy VideoMiner using the pre-built image.

## Prerequisites

- Docker 24+
- NVIDIA driver + [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- Recommended GPU VRAM ≥ 8GB

## docker-compose (Recommended)

1. Clone the repo and prepare config:
```bash
git clone https://github.com/JazerJu/video-miner.git
cd video-miner
cp .env.example .env
```

2. Adjust `.env` as needed:
```bash
VIDGO_PORT=8080          # Web/API port
ENABLE_MCP=0             # Enable MCP service (0/1)
VIDGO_MCP_PORT=8787      # MCP port
```

3. Create data directories and start:
```bash
mkdir -p data/{media,config,models}
touch data/videos.db
docker compose up -d
```

4. Open `http://localhost:<VIDGO_PORT>`.

## docker run

```bash
docker pull jaceju68/video-miner:cuda-latest

docker run -d --name video-miner \
  --restart unless-stopped \
  --runtime nvidia \
  --gpus all \
  -p 8080:8080 \
  -p 8787:8787 \
  -v "$(pwd)/data/videos.db:/app/database/videos.db" \
  -v "$(pwd)/data/media:/app/media" \
  -v "$(pwd)/data/config:/app/config" \
  -v "$(pwd)/data/models:/app/models" \
  jaceju68/video-miner:cuda-latest
```

## Data Persistence

| Container path | Purpose |
|---|---|
| `/app/database/videos.db` | SQLite database |
| `/app/media` | Video and subtitle files |
| `/app/config` | User configuration (config.ini) |
| `/app/models` | ASR / VLM / OCR model files |

> Model files are not bundled in the image. Download them from the settings panel (Video Understanding tab) on first use, or place them manually in `data/models/`.

## GPU and Model Configuration

The `.env` file provides extensive model runtime parameters. Common ones:

```bash
# VidUnder inference
VIDUNDER_N_GPU_LAYERS=99          # VLM GPU layers (0 = CPU-only)
VIDUNDER_THINKING_BUDGET=low      # Frame sampling density: low / medium / high
VIDUNDER_GLM_OCR_N_GPU_LAYERS=18  # GLM-OCR GPU layers

# GLM-ASR transcription engine
GLM_ASR_MODEL=/app/models/glm-asr/glm-asr-nano-2512
GLM_ASR_FA_MODEL=/app/models/glm-asr/qwen3-forcealigner-0.6b

# GLM-ASR runtime
GLMASR_VRAM_UTIL=0.9              # VRAM utilization
GLMASR_MAX_SEQS=256               # Max concurrent sequences
```

See `.env.example` for the full parameter list.

## Network Proxy

To use a proxy inside the container, set in `.env`:

```bash
HTTPS_PROXY=http://host.docker.internal:7890
```

`host.docker.internal` is mapped to the Docker host in docker-compose.yml.

## MCP Service

Set `ENABLE_MCP=1` in `.env` to start the MCP ASGI service (port `VIDGO_MCP_PORT`). MCP tools call the main API via the container-internal address `http://127.0.0.1:8080`.

If MCP clients are not on localhost, set:

```bash
VIDGO_MCP_PUBLIC_URL=http://<server-ip>:8787
```

## WeMM Clip Search on ONNX Runtime

`find_clips` encodes each 10-second clip with WeMM-Embedding-4B. The image runs this model on ONNX Runtime, so it does not need PyTorch.

### Measured Speed and Retrieval Quality

Test setup: one RTX 5070 Ti (16 GB). Clips are 10 seconds at 2 fps and 640 px wide, about 2,300 tokens each.

| Per clip | Vision encoder | Text model | Total | VRAM |
| --- | --- | --- | --- | --- |
| PyTorch, NF4 (before) | 0.11 s | 0.26 s | 0.37 s | about 5 GB |
| ONNX, NF4, onnxruntime 1.26 | 0.12 s | 0.65 s | 0.77 s | 6.5 GB |
| ONNX, NF4, onnxruntime 1.30 (in the image) | 0.13 s | 0.25–0.28 s | 0.39–0.42 s | 4.8 GB |

The index of a 23-minute video (137 clips) took 93 s to build, including clip cutting. That is 0.68 s per clip. The PyTorch server took 1.01 s per clip.

Retrieval quality on two long screen-recorded tutorials (437 clips), measured as MRR:

| Question type | Questions | PyTorch | ONNX |
| --- | --- | --- | --- |
| Visual | 26 | 0.60 | 0.62 |
| Trial and error | 14 | 0.72 | 0.72 |
| Speech | 43 | 0.76 | 0.74 |

For negative queries (content that is not in the video), the AUC is 0.80 for both. The ONNX embeddings match the PyTorch embeddings at cosine 0.998–0.999, so existing indexes stay valid.

### Why the Image Builds onnxruntime 1.30

- The WeMM text model has 24 Gated DeltaNet (linear attention) layers.
- In onnxruntime 1.26, the `LinearAttention` CUDA kernel runs the recurrence one token at a time. One layer takes 12 ms for 2,300 tokens, so encoding is about half as fast as PyTorch.
- onnxruntime 1.30 adds the `GatedDeltaNet` operator with a chunked prefill kernel. One layer takes about 1 ms.
- Every GPU wheel of onnxruntime on PyPI since 1.28 targets CUDA 13. The image uses CUDA 12.8, and its llama.cpp libraries link cuBLAS 12.
- The image therefore installs onnxruntime 1.30.0 built from source against CUDA 12.8, with the GPU architecture list of the official CUDA 12.8 package. The build steps are in [docker/onnxruntime-wheel](../../docker/onnxruntime-wheel/).
- The other ONNX models (bge, GLM-OCR, MiniCPM-V, FunASR, silero VAD) give the same outputs on this build as on onnxruntime 1.26.

---

[Back to English docs](index.md) | [Build from Scratch](build-from-scratch.md)
