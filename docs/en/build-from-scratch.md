# Build Docker Image from Scratch

For custom images (modified dependencies, different CUDA version, additional build artifacts, etc.).

## Prerequisites

- Docker 24+ (BuildKit support)
- Network access to npm registry, PyPI, and HuggingFace

## Multi-Stage Build Overview

The Dockerfile uses three stages:

| Stage | Base image | Output |
|---|---|---|
| `compile-frontend` | `node:22-bookworm-slim` | Frontend static files → `/app/static` |
| `python-builder` | `nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04` | Python dependencies (system-wide) |
| `runtime` | `nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04` | Final runtime image |

The runtime image is based on CUDA 12.8.1 + cuDNN and includes ffmpeg, Node.js, SQLite, and Python 3.10. Tsinghua PyPI mirror and HuggingFace mirror are used by default to speed up builds.

## Build Command

```bash
git clone https://github.com/JazerJu/video-miner.git
cd video-miner

# Standard GPU image
docker build -t video-miner:local .

# Specify Python version
docker build --build-arg PYTHON_VERSION=3.11 -t video-miner:local-py311 .
```

After building, follow the [Docker Deployment](deployment.md) instructions for docker run / docker-compose, replacing the image name with `video-miner:local`.

## Customization

### Changing Package Mirrors

The Dockerfile defaults to Tsinghua mirrors. If building outside China or needing different mirrors, modify:

```dockerfile
# Ubuntu mirror
RUN sed -i 's@archive.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list

# PyPI mirror
RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/

# HuggingFace mirror
ENV HF_ENDPOINT=https://hf-mirror.com
```

### docker-compose with Local Build

Replace `image:` with `build:` in `docker-compose.yml`:

```yaml
services:
  vidgo:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: vidgo-app
    # ... rest unchanged
```

Then run `docker compose up -d --build`.

## Image Size Optimization

The Dockerfile already applies these optimizations:

- Removes pip, sympy (only needed during install)
- Cleans `__pycache__` and test directories
- Strips CUDA development libraries (libcusparse, libcusolver, libnpp), keeping only runtime libs
- Multi-stage build — final image contains no build toolchain

## Runtime Architecture

```
entrypoint.sh
  ├── gunicorn (WSGI, port 8080)     ← Django main service
  └── MCP ASGI (port 8787)           ← Optional, started when ENABLE_MCP=1
```

The container runs as non-root user `vidgo` (uid=1000). Mounted host directories must be readable/writable by this user.

---

[Back to English docs](index.md) | [Docker Deployment](deployment.md)
