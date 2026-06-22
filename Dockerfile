# Global ARG for Python version
ARG PYTHON_VERSION=3.12

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

# Stage 1: Python dependencies builder (Ubuntu 24.04 native Python 3.12)
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04 AS python-builder
ARG PYTHON_VERSION=3.12

# 设置清华源 (Ubuntu)
RUN set -eux; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i 's@archive.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list; \
        sed -i 's@security.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list; \
    fi; \
    if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then \
        sed -i 's@http://archive.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list.d/ubuntu.sources; \
        sed -i 's@http://security.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list.d/ubuntu.sources; \
    fi

RUN apt-get update && apt-get install -y --no-install-recommends \
    python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev python3-pip \
    && ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python3 \
    && ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# 设置pip清华源和HuggingFace镜像
RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/ \
    && pip3 config set global.trusted-host pypi.tuna.tsinghua.edu.cn

ENV HF_ENDPOINT=https://hf-mirror.com
ENV PIP_BREAK_SYSTEM_PACKAGES=1

WORKDIR /app
COPY backend/requirements.txt .

# Install dependencies to system directory
RUN set -eux; \
    python3 -m pip install --break-system-packages --no-cache-dir -r requirements.txt; \
    python3 -m pip install --break-system-packages --no-cache-dir "yt-dlp[default]"; \
    python3 -c 'import onnxruntime as ort; print("onnxruntime", ort.__version__, ort.get_available_providers()); assert ort.__version__ == "1.26.0", ort.__version__'; \
    python3 -m pip uninstall --break-system-packages -y sympy || true; \
    find /usr/local/lib/ -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true; \
    find /usr/local/lib/ -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true; \
    rm -rf /usr/local/cuda /usr/local/nvidia /usr/local/cuda-*

# Stage 2: Runtime
# FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04 AS runtime
ARG PYTHON_VERSION=3.12

# 设置清华源 (Ubuntu)
RUN set -eux; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i 's@archive.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list; \
        sed -i 's@security.ubuntu.com@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list; \
    fi; \
    if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then \
        sed -i 's@http://archive.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list.d/ubuntu.sources; \
        sed -i 's@http://security.ubuntu.com/ubuntu/@https://mirrors.tuna.tsinghua.edu.cn/ubuntu/@g' /etc/apt/sources.list.d/ubuntu.sources; \
    fi

# Install only runtime dependencies (no dev packages)
# 根据是否存在 package-lock.json 来决定用 npm ci 还是 npm install。
RUN apt-get update && apt-get install -y --no-install-recommends \
    python${PYTHON_VERSION} python${PYTHON_VERSION}-venv \
    ffmpeg \
    libsndfile1 \
    sqlite3 \
    nodejs \
    libgomp1 \
    tzdata \
    && ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python3 \
    && ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

RUN rm -f /usr/local/cuda/lib64/libcusparse.so* \
         /usr/local/cuda/lib64/libcusolver*.so* \
         /usr/local/cuda/lib64/libnpp*.so*

WORKDIR /app

# Create runtime user before COPY --chown so name resolution works at build time.
# CUDA Ubuntu 24.04 images already carry ubuntu:1000; reuse that UID as vidgo.
RUN set -eux; \
    if getent passwd vidgo >/dev/null; then \
        true; \
    elif getent passwd 1000 >/dev/null; then \
        old_user="$(getent passwd 1000 | cut -d: -f1)"; \
        old_group="$(getent group 1000 | cut -d: -f1)"; \
        if [ "$old_group" != "vidgo" ]; then groupmod -n vidgo "$old_group"; fi; \
        usermod -l vidgo -d /home/vidgo -m "$old_user"; \
    else \
        groupadd --gid 1000 vidgo; \
        useradd --create-home --uid 1000 --gid 1000 vidgo; \
    fi; \
    mkdir -p /app/config /app/media /app/models /app/database /app/work_dir /app/cache \
    && chown -R vidgo:vidgo /app/config /app/media /app/models /app/database /app/work_dir /app/cache

# 仅复制配置的备份文件到镜像固定位置（**不是**挂载点）
COPY backend/config/config.ini.backup /app/config.ini.backup

# Copy Python packages from builder (system-wide installation)
COPY --from=python-builder /usr/local /usr/local

# Copy frontend build from compile-frontend stage
COPY --from=compile-frontend /app/backend/static /app/static

# Copy backend code only
COPY --chown=vidgo:vidgo backend/ .

# The source tree carries local absolute symlinks in FunASR's llama.cpp bin
# directory. Replace them with the image's bundled shared libraries so the
# runtime is self-contained after Docker COPY dereferences or preserves links.
RUN set -eux; \
    funasr_bin=/app/asr_utils/fun-asr-stack/fun_asr_gguf/inference/bin; \
    mkdir -p "$funasr_bin"; \
    rm -f "$funasr_bin"/libggml-base.so* \
          "$funasr_bin"/libggml-cpu.so* \
          "$funasr_bin"/libggml-cuda.so* \
          "$funasr_bin"/libggml.so* \
          "$funasr_bin"/libllama.so*; \
    cp -a /app/vid_under/bin/libggml-base.so* \
          /app/vid_under/bin/libggml-cpu.so* \
          /app/vid_under/bin/libggml-cuda.so* \
          /app/vid_under/bin/libggml.so* \
          /app/vid_under/bin/libllama.so* \
          "$funasr_bin"/; \
    chown -R vidgo:vidgo "$funasr_bin"

# 复制启动脚本
COPY --chown=vidgo:vidgo docker/entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh
USER vidgo
# default web port plus optional MCP sidecar port
EXPOSE 8080 8787

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
    VIDUNDER_GLM_OCR_N_GPU_LAYERS=99 \
    VIDUNDER_GLM_OCR_ONNX_PROVIDER=cuda \
    VIDUNDER_GLM_OCR_ONNX_PRECISION=q4 \
    VIDUNDER_N_BATCH=512 \
    VIDUNDER_KV_CACHE_TYPE=q4_0 \
    VIDUNDER_MINICPM_ONNX_PROVIDER=cuda \
    VIDUNDER_THINKING_BUDGET=low \
    VIDUNDER_SUMMARY_SLIDES_PER_CHAPTER=3 \
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
    LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6 \
    LD_LIBRARY_PATH=/app/vid_under/bin:/usr/local/cuda/lib64

VOLUME ["/app/config", "/app/database", "/app/media", "/app/models"]

# 运行启动脚本
ENTRYPOINT ["/app/entrypoint.sh"]

# Use gunicorn for production. The entrypoint expands this to the default
# single-worker gthread layout unless env vars override it.
CMD ["gunicorn"]
