# coding=utf-8
"""视频理解框架配置

支持环境变量覆盖（Docker 热修改）：
  VIDUNDER_N_CTX          - KV cache 上下文长度，默认 4096
  VIDUNDER_N_GPU_LAYERS   - GGUF 放 GPU 的层数，默认 99（全部），0=纯 CPU
  VIDUNDER_KV_CACHE_TYPE  - KV cache 量化类型，默认 q4_0
  VIDUNDER_MINICPM_ONNX_PROVIDER - MiniCPM-V vision ONNX 推理设备，默认 cuda，可改 cpu
  VIDUNDER_VIDEO_PATH     - 输入视频路径
  VIDUNDER_SRT_PATH       - 输入字幕路径
"""
import os
from pathlib import Path

# ── 项目路径 ──────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
DB_DIR = PROJECT_DIR / "db"
TOKENS_DIR = DB_DIR / "tokens"

# ── 视频输入 ──────────────────────────────────────────────
VIDEO_PATH = os.environ.get("VIDUNDER_VIDEO_PATH", "/data/其他模型/小型语言模型/lecture5-720p-en.mp4")
SRT_PATH = os.environ.get("VIDUNDER_SRT_PATH", "/data/其他模型/小型语言模型/lecture5-720p-en.sentence.srt")

# ── MiniCPM-V 模型路径 ──────────────────────────────────
EXPORT_DIR = PROJECT_DIR / "onnx"
GGUF_PATH = PROJECT_DIR / "models" / "MiniCPM-V-4_5-Q4_K_M.gguf"

# ── 分段参数 ──────────────────────────────────────────────
CLIP_SECS = 10
VIDEO_FPS = 2
FRAMES_PER_CLIP = 7
MAX_SLICE_NUMS = 1

# ── 外部 API ─────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("VIDUNDER_GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3.1-pro-preview"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

NPPS = 70
EMBED_DIM = 4096

EMBED_MODEL_PATH = str(PROJECT_DIR / "models" / "bge-small-zh-v1.5")

GLM_OCR_GGUF = str(PROJECT_DIR / "models" / "GLM-OCR-Q8_0.gguf")

OPENROUTER_KEY = os.environ.get("VIDUNDER_OPENROUTER_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DOUBAO_API_KEY = os.environ.get("VIDUNDER_DOUBAO_API_KEY", "")
DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_MODEL = "doubao-seed-2-0-pro-260215"

STEP_API_KEY = os.environ.get("VIDUNDER_STEP_API_KEY", "")
STEP_BASE_URL = "https://api.stepfun.com/v1"
STEP_MODEL = "step-3.7-flash"

DEEPSEEK_API_KEY = os.environ.get("VIDUNDER_DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

MIMO_API_KEY = os.environ.get("VIDUNDER_MIMO_API_KEY", "")
MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5"

# ── LLM 推理参数（环境变量可覆盖）─────────────────────────
N_CTX = int(os.environ.get("VIDUNDER_N_CTX", "4096"))
N_GPU_LAYERS = int(os.environ.get("VIDUNDER_N_GPU_LAYERS", "99"))
N_BATCH = int(os.environ.get("VIDUNDER_N_BATCH", "512"))
KV_CACHE_TYPE = os.environ.get("VIDUNDER_KV_CACHE_TYPE", "q4_0")
ONNX_PROVIDER = os.environ.get(
    "VIDUNDER_MINICPM_ONNX_PROVIDER",
    os.environ.get("VIDUNDER_ONNX_PROVIDER", "cuda"),
)
N_PREDICT = 256
