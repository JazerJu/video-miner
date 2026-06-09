# coding=utf-8
"""视频理解框架配置

支持环境变量覆盖（Docker 热修改）：
  VIDUNDER_N_CTX          - KV cache 上下文长度，默认 4096
  VIDUNDER_N_GPU_LAYERS   - MiniCPM-V GGUF 放 GPU 的层数，默认 36（0-36）
  VIDUNDER_GLM_OCR_N_GPU_LAYERS - GLM-OCR GGUF 放 GPU 的层数，默认 17（0-17）
  VIDUNDER_KV_CACHE_TYPE  - KV cache 量化类型，默认 q4_0
  VIDUNDER_ONNX_PROVIDER  - ONNX 推理设备，默认 cuda，可改 cpu
  VIDUNDER_VIDEO_PATH     - 输入视频路径
  VIDUNDER_SRT_PATH       - 输入字幕路径
"""
import os
from pathlib import Path

# ── 项目路径 ──────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
MEDIA_VIDUNDER = PROJECT_DIR.parent / "media" / "vidunder"
DB_DIR = MEDIA_VIDUNDER / "db"
TOKENS_DIR = DB_DIR / "tokens"
EXPORT_DIR = PROJECT_DIR / "onnx"
GGUF_PATH = PROJECT_DIR / "models" / "MiniCPM-V-4_5-Q4_K_M.gguf"
GGUF_PATH_V46 = PROJECT_DIR / "models" / "MiniCPM-V-4_6-Q4_K_M.gguf"

# ── 分段参数 ──────────────────────────────────────────────
CLIP_SECS = 10
VIDEO_FPS = 2
MAX_SLICE_NUMS = 1

THINKING_BUDGET_FRAMES = {
    "low": 7,
    "medium": 14,
    "high": 21,
}
DEFAULT_THINKING_BUDGET = os.environ.get("VIDUNDER_THINKING_BUDGET", "low")
FRAMES_PER_CLIP = THINKING_BUDGET_FRAMES[DEFAULT_THINKING_BUDGET]

# ── 外部 API ─────────────────────────────────────────────
GEMINI_API_KEY = "REDACTED_GEMINI_KEY"
GEMINI_MODEL = "gemini-3.1-pro-preview"
GEMINI_EMBED_MODEL = "text-embedding-004"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
GEMINI_EMBED_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_EMBED_MODEL}:embedContent?key={GEMINI_API_KEY}"

NPPS = 70
EMBED_DIM = 4096

EMBED_MODEL_PATH = str(PROJECT_DIR / "models" / "bge-small-zh-v1.5")

GLM_OCR_GGUF = str(PROJECT_DIR / "models" / "GLM-OCR-Q8_0.gguf")

OPENROUTER_KEY = "REDACTED_OPENROUTER_KEY"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "google/gemini-2.5-flash"

DOUBAO_API_KEY = "REDACTED_DOUBAO_KEY"
DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_MODEL = "doubao-seed-2-0-pro-260215"

STEP_API_KEY = "REDACTED_STEP_KEY"
STEP_BASE_URL = "https://api.stepfun.com/v1"
STEP_MODEL = "step-3.7-flash"

DEEPSEEK_API_KEY = "REDACTED_DEEPSEEK_KEY"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

MIMO_API_KEY = "REDACTED_MIMO_KEY"
MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5"

# ── LLM 推理参数（环境变量可覆盖）─────────────────────────
N_CTX = int(os.environ.get("VIDUNDER_N_CTX", "4096"))
N_GPU_LAYERS = int(os.environ.get("VIDUNDER_N_GPU_LAYERS", "36"))
GLM_OCR_N_GPU_LAYERS = int(os.environ.get("VIDUNDER_GLM_OCR_N_GPU_LAYERS", "17"))
N_BATCH = int(os.environ.get("VIDUNDER_N_BATCH", "512"))
KV_CACHE_TYPE = os.environ.get("VIDUNDER_KV_CACHE_TYPE", "q4_0")
ONNX_PROVIDER = os.environ.get("VIDUNDER_ONNX_PROVIDER", "cuda")
N_PREDICT = 256
VIDEO_PATH = os.environ.get("VIDUNDER_VIDEO_PATH", "")
SRT_PATH = os.environ.get("VIDUNDER_SRT_PATH", "")
SUMMARY_SLIDES_PER_CHAPTER = int(os.environ.get("VIDUNDER_SUMMARY_SLIDES_PER_CHAPTER", "3"))
SUMMARY_LANG = os.environ.get("VIDUNDER_SUMMARY_LANG", "中文")
