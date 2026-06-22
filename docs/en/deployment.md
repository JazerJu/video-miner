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

---

[Back to English docs](index.md) | [Build from Scratch](build-from-scratch.md)
