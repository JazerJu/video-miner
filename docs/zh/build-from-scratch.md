# 从零编译 Docker 镜像

适用于需要自定义镜像（修改依赖、更换 CUDA 版本、添加编译产物等）的场景。

## 前置要求

- Docker 24+（支持 BuildKit）
- 构建机器需要网络访问 npm registry、PyPI、HuggingFace

## 多阶段构建概览

Dockerfile 使用三个阶段：

| 阶段 | 基础镜像 | 产物 |
|---|---|---|
| `compile-frontend` | `node:22-bookworm-slim` | 前端静态文件 → `/app/static` |
| `python-builder` | `nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04` | Python 依赖（系统级安装） |
| `runtime` | `nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04` | 最终运行时镜像 |

运行时镜像基于 CUDA 12.8.1 + cuDNN，包含 ffmpeg、Node.js、SQLite 和 Python 3.10。镜像内默认使用清华 PyPI 源和 HuggingFace 镜像加速构建。

## 编译命令

```bash
git clone https://github.com/JazerJu/video-miner.git
cd video-miner

# 标准 GPU 镜像
docker build -t video-miner:local .

# 指定 Python 版本
docker build --build-arg PYTHON_VERSION=3.11 -t video-miner:local-py311 .
```

构建完成后，按 [Docker 部署](deployment.md)的 docker run / docker-compose 方式启动，把镜像名替换为 `video-miner:local`。

## 自定义构建

### 更换镜像源

Dockerfile 默认使用清华源。如果构建环境在国外或需要其他源，修改 Dockerfile 中的：

```dockerfile
# Ubuntu 源
RUN sed -i 's@archive.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list

# PyPI 源
RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/

# HuggingFace 镜像
ENV HF_ENDPOINT=https://hf-mirror.com
```

### docker-compose 本地构建

在 `docker-compose.yml` 中将 `image:` 替换为 `build:`：

```yaml
services:
  vidgo:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: vidgo-app
    # ... 其余配置不变
```

然后 `docker compose up -d --build`。

## 镜像体积优化

Dockerfile 已做了以下瘦身：

- 移除 pip、sympy（仅安装期需要）
- 清理 `__pycache__` 和 tests 目录
- 移除 CUDA 开发包（libcusparse、libcusolver、libnpp），仅保留运行时库
- 多阶段构建，最终镜像不含编译工具链

## 运行时架构

```
entrypoint.sh
  ├── gunicorn (WSGI, port 8080)     ← Django 主服务
  └── MCP ASGI (port 8787)           ← 可选，ENABLE_MCP=1 时启动
```

容器以非 root 用户 `vidgo` (uid=1000) 运行。挂载的宿主机目录需对该用户可读写。

---

[返回中文文档首页](index.md) | [Docker 部署](deployment.md)
