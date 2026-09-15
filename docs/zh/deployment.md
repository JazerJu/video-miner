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


## WeMM 片段检索运行在 ONNX Runtime 上

`find_clips` 用 WeMM-Embedding-4B 给每个 10 秒片段编码。镜像里这个模型运行在 ONNX Runtime 上，不需要 PyTorch。

### 实测速度和检索效果

测试环境：一张 RTX 5070 Ti（16 GB）。片段为 10 秒、2 fps、宽 640 px，每段约 2,300 个 token。

| 每片段 | 视觉编码器 | 文本模型 | 合计 | 显存 |
| --- | --- | --- | --- | --- |
| PyTorch，NF4（之前） | 0.11 s | 0.26 s | 0.37 s | 约 5 GB |
| ONNX，NF4，onnxruntime 1.26 | 0.12 s | 0.65 s | 0.77 s | 6.5 GB |
| ONNX，NF4，onnxruntime 1.30（镜像内） | 0.13 s | 0.25–0.28 s | 0.39–0.42 s | 4.8 GB |

一个 23 分钟的视频（137 个片段）建索引用时 93 秒（含切片），即每片段 0.68 秒；PyTorch 版是每片段 1.01 秒。

在两个录屏长教程（共 437 个片段）上的检索效果（MRR）：

| 题型 | 题数 | PyTorch | ONNX |
| --- | --- | --- | --- |
| 画面类 | 26 | 0.60 | 0.62 |
| 试错类 | 14 | 0.72 | 0.72 |
| 说话类 | 43 | 0.76 | 0.74 |

对负样本（视频里没有的内容），两者的 AUC 都是 0.80。ONNX 与 PyTorch 的向量余弦相似度为 0.998–0.999，已有索引无需重建。

### 为什么镜像要自行编译 onnxruntime 1.30

- WeMM 的文本模型有 24 层 Gated DeltaNet（线性注意力）。
- onnxruntime 1.26 的 `LinearAttention` CUDA 内核逐个 token 递推，2,300 个 token 时每层 12 ms，编码速度约为 PyTorch 的一半。
- onnxruntime 1.30 新增 `GatedDeltaNet` 算子，带分块并行的预填充内核，每层约 1 ms。
- PyPI 上 onnxruntime 从 1.28 起的 GPU 包都是 CUDA 13 的；镜像使用 CUDA 12.8，其中的 llama.cpp 库链接 cuBLAS 12。
- 因此镜像安装的是按 CUDA 12.8 从源码编译的 onnxruntime 1.30.0，GPU 架构列表与官方 CUDA 12.8 包相同。编译步骤见 [docker/onnxruntime-wheel](../../docker/onnxruntime-wheel/)。
- 镜像内其他 ONNX 模型（bge、GLM-OCR、MiniCPM-V、FunASR、silero VAD）在这个版本上的输出与 onnxruntime 1.26 一致。

---

[返回中文文档首页](index.md) | [从零编译镜像](build-from-scratch.md)
