# Docker 部署

使用预编译镜像快速部署 VideoMiner。

## 前置要求

- Docker 24+
- NVIDIA 驱动 + [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- 建议 GPU 显存 ≥ 8GB

## docker-compose（推荐）

1. 克隆仓库并准备配置：
```bash
git clone https://github.com/JazerJu/video-miner.git
cd video-miner
cp .env.example .env
```

2. 按需修改 `.env`：
```bash
VIDGO_PORT=8080          # Web/API 端口
ENABLE_MCP=0             # 是否启用 MCP 服务（0/1）
VIDGO_MCP_PORT=8787      # MCP 端口
```

3. 创建数据目录并启动：
```bash
mkdir -p data/{media,config,models}
touch data/videos.db
docker compose up -d
```

4. 访问 `http://localhost:<VIDGO_PORT>`。

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

## 数据持久化

| 容器路径 | 用途 |
|---|---|
| `/app/database/videos.db` | SQLite 数据库 |
| `/app/media` | 视频和字幕文件 |
| `/app/config` | 用户配置（config.ini） |
| `/app/models` | ASR / VLM / OCR 模型文件 |

> 模型文件不随镜像打包。首次使用时在设置面板的「视频理解」标签页下载，或手动放入 `data/models/` 对应目录。

## GPU 与模型配置

`.env` 中提供了丰富的模型运行参数，常用的包括：

```bash
# VidUnder 推理参数
VIDUNDER_N_GPU_LAYERS=99          # VLM GPU 层数（0 = 纯 CPU）
VIDUNDER_THINKING_BUDGET=low      # 帧采样密度：low / medium / high
VIDUNDER_GLM_OCR_N_GPU_LAYERS=18  # GLM-OCR GPU 层数

# GLM-ASR 转录引擎
GLM_ASR_MODEL=/app/models/glm-asr/glm-asr-nano-2512
GLM_ASR_FA_MODEL=/app/models/glm-asr/qwen3-forcealigner-0.6b

# GLM-ASR 运行时
GLMASR_VRAM_UTIL=0.9              # VRAM 利用率
GLMASR_MAX_SEQS=256               # 最大并发序列数
```

完整参数列表见 `.env.example`。

## 网络代理

容器内需要代理时，在 `.env` 中配置：

```bash
HTTPS_PROXY=http://host.docker.internal:7890
```

`host.docker.internal` 已在 docker-compose.yml 中映射到宿主机。


---

[返回中文文档首页](index.md) | [从零编译镜像](build-from-scratch.md)
