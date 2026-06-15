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
RUN npm run build-only

# Stage 1: Python dependencies builder (ubuntu22.04 native Python)
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04 AS python-builder

# 设置清华源 (Ubuntu)
RUN sed -i 's@archive.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list \
    && sed -i 's@security.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-venv python3.10-dev python3-pip \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# 设置pip清华源和HuggingFace镜像
RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/ \
    && pip3 config set global.trusted-host pypi.tuna.tsinghua.edu.cn

ENV HF_ENDPOINT=https://hf-mirror.com

WORKDIR /app
COPY backend/requirements.txt .

# Install dependencies to system directory
RUN pip3 install --no-cache-dir --upgrade pip \
    && pip3 install --no-cache-dir -r requirements.txt \
    && pip3 install --no-cache-dir "yt-dlp[default]" \
    && pip3 uninstall -y pip sympy \
    && find /usr/local/lib/ -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib/ -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf /usr/local/cuda /usr/local/nvidia /usr/local/cuda-*

# Stage 2: Runtime
# FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04 AS runtime

# 设置清华源 (Ubuntu)
RUN sed -i 's@archive.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list \
    && sed -i 's@security.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list

# Install only runtime dependencies (no dev packages)
# 根据是否存在 package-lock.json 来决定用 npm ci 还是 npm install。
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-venv \
    ffmpeg \
    libsndfile1 \
    sqlite3 \
    nodejs \
    libgomp1 \
    tzdata \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

RUN rm -f /usr/local/cuda/lib64/libcusparse.so* \
         /usr/local/cuda/lib64/libcusolver*.so* \
         /usr/local/cuda/lib64/libnpp*.so*

WORKDIR /app

# Create runtime user before COPY --chown so name resolution works at build time.
RUN useradd --create-home --uid 1000 vidgo \
    && mkdir -p /app/config /app/media /app/models /app/database /app/work_dir \
    && chown -R vidgo:vidgo /app/config /app/media /app/models /app/database /app/work_dir

# 仅复制配置的备份文件到镜像固定位置（**不是**挂载点）
COPY backend/config/config.ini.backup /app/config.ini.backup

# Copy Python packages from builder (system-wide installation)
COPY --from=python-builder /usr/local /usr/local

# Copy frontend build from compile-frontend stage
COPY --from=compile-frontend /app/backend/static /app/static

# Copy backend code only
COPY --chown=vidgo:vidgo backend/ .
# 复制启动脚本
COPY --chown=vidgo:vidgo docker/entrypoint.sh /app/entrypoint.sh

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
    VIDUNDER_MODEL_ROOT=/app/models \
    VIDUNDER_ASR_MODELS_ROOT=/app/models \
    VIDUNDER_N_CTX=4096 \
    VIDUNDER_N_GPU_LAYERS=99 \
    VIDUNDER_GLM_OCR_N_GPU_LAYERS=17 \
    VIDUNDER_N_BATCH=512 \
    VIDUNDER_KV_CACHE_TYPE=q4_0 \
    VIDUNDER_ONNX_PROVIDER=cuda \
    VIDUNDER_THINKING_BUDGET=low \
    VIDUNDER_HWACCEL=none \
    FUNASR_GGUF_DIR=/app/asr_utils/fun-asr-stack \
    GLM_ASR_STACK_ROOT=/app/asr_utils/glm-asr-stack \
    GLM_ASR_MODEL_CACHE=/app/models/glm-asr \
    GLM_ASR_MODEL=/app/models/glm-asr/glm-asr-nano-2512 \
    GLM_ASR_MODEL_DIR=/app/models/glm-asr/glm-asr-nano-2512 \
    GLM_ASR_FA_MODEL=/app/models/glm-asr/qwen3-forcealigner-0.6b \
    GLM_ASR_MEL=/app/asr_utils/glm-asr-stack/resources/mel_filters.bin \
    GLMASR_VRAM_UTIL=0.9 \
    GLMASR_MAX_SEQS=256 \
    GLMASR_MAX_BATCHED_TOKENS=10000 \
    GLMASR_MAX_NEW_TOKENS=256 \
    GLMASR_ENCODER_FA_PIPELINED=1 \
    GLMASR_ENCODER_FA_VLLM=1 \
    GLMASR_ENCODER_FA_LONG_MIN_SEQ=1 \
    GLMASR_ENCODER_FA_MIN_SEQ=1 \
    LD_LIBRARY_PATH=/app/vid_under/bin:/usr/local/cuda/lib64

VOLUME ["/app/config", "/app/database", "/app/media", "/app/models"]

# 运行启动脚本
ENTRYPOINT ["/app/entrypoint.sh"]

# Use gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "vid_go.wsgi:application"]
