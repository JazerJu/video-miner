# Global ARG for Python version
ARG PYTHON_VERSION=3.10

# Step 0: compile-frontend(not included in final image)  
FROM node:22-bookworm-slim AS compile-frontend

# You can override these if your structure differs
ARG FRONTEND_DIR=frontend
ARG FRONTEND_OUT=dist

# /app is the ultimate working directory
# with manage.py in /app/manage.py 
# and .
WORKDIR /app/${FRONTEND_DIR}

# Install deps with cache-friendly order
# (copy lockfiles first for better layer caching)
COPY ${FRONTEND_DIR}/package*.json ./

RUN set -eux; \
    if [ -f package-lock.json ]; then npm ci; \
    else echo "No package-lock.json; running npm install"; npm install; fi

# Copy frontend source and build
COPY ${FRONTEND_DIR}/ ./
RUN npm run build

# Stage 1: Python dependencies builder
FROM python:${PYTHON_VERSION}-slim-bookworm AS python-builder

# 设置pip清华源和HuggingFace镜像
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/ \
    && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

ENV HF_ENDPOINT=https://hf-mirror.com

WORKDIR /app
COPY backend/requirements.txt .

# Install dependencies to system directory
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    # 安装 yt-dlp 完整依赖（含 EJS 脚本、加密库等）
    && pip install --no-cache-dir "yt-dlp[default]"

# Stage 2: Runtime
# FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04 AS runtime

# 设置清华源 (Ubuntu)
RUN sed -i 's@archive.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list \
    && sed -i 's@security.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list

# Install only runtime dependencies (no dev packages)
# 根据是否存在 package-lock.json 来决定用 npm ci 还是 npm install。
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    sqlite3 \
    # Node.js 运行时：yt-dlp-ejs 需要 Node 执行 JS 挑战脚本（仅需 node 二进制，无需 npm）
    nodejs \
    # FunASR-GGUF llama.cpp 依赖（GGUF decoder 通过 ctypes 加载）
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 仅复制配置的备份文件到镜像固定位置（**不是**挂载点）
COPY backend/config/config.ini.backup /app/config.ini.backup

RUN mkdir -p /app/config
# Copy Python packages from builder (system-wide installation)
COPY --from=python-builder /usr/local /usr/local

# Copy frontend build from compile-frontend stage
COPY --from=compile-frontend /app/frontend/dist /app/static

# Copy backend code only
COPY backend/ .
# 复制启动脚本
COPY --chown=vidgo:vidgo backend/docker/entrypoint.sh /app/entrypoint.sh
# Create user and directories
RUN useradd --create-home --uid 1000 vidgo \
    && mkdir -p /app/media /app/models /app/database /app/asr-models/funasr-gguf \
    && chown -R vidgo:vidgo /app

# FunASR-GGUF 模型权重（如构建上下文存在则拷入；不存在则跳过，由运行时挂载）
# 模型结构：
#   /app/asr-models/funasr-gguf/Fun-ASR-Nano-Encoder-Adaptor.int4.onnx
#   /app/asr-models/funasr-gguf/Fun-ASR-Nano-CTC.int4.onnx
#   /app/asr-models/funasr-gguf/Fun-ASR-Nano-Decoder.q5_k.gguf
#   /app/asr-models/funasr-gguf/tokens.txt
COPY --chown=vidgo:vidgo asr-models/funasr-gguf/ /app/asr-models/funasr-gguf/ 2>/dev/null || true

RUN chmod +x /app/entrypoint.sh
USER vidgo
# default port at 8000
EXPOSE 8000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=vid_go.settings \
    HF_ENDPOINT=https://hf-mirror.com \
    HUGGINGFACE_HUB_CACHE=/app/models/.cache/huggingface \
    APP_CONFIG_DIR=/app/config \
    VIDGO_ALLOWED_HOSTS=* \
    VIDGO_CORS_ALLOWED_ORIGINS=http://localhost:4173,http://127.0.0.1:4173 \
    VIDGO_CSRF_TRUSTED_ORIGINS=http://localhost:4173,http://127.0.0.1:4173 \
    # FunASR-GGUF 路径；用户可改 config.ini 中的 funasr_gguf_dir 覆盖
    FUNASR_GGUF_DIR=/app/asr-models/funasr-gguf

VOLUME ["/app/config", "/app/database", "/app/media", "/app/models", "/app/asr-models/funasr-gguf"]

# 运行启动脚本
ENTRYPOINT ["/app/entrypoint.sh"]

# Use gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "vid_go.wsgi:application"]