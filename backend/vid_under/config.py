# coding=utf-8
"""视频理解框架配置

支持环境变量覆盖（Docker 热修改）：
  VIDUNDER_MODEL_ROOT    - 模型根目录，默认 PROJECT_DIR/models
  VIDUNDER_N_CTX          - KV cache 上下文长度，默认 4096
  VIDUNDER_N_GPU_LAYERS   - MiniCPM-V GGUF 放 GPU 的层数，默认 99（全 offload 37 层）
  VIDUNDER_GLM_OCR_N_GPU_LAYERS - GLM-OCR GGUF 放 GPU 的层数，默认 99（全 offload）
  VIDUNDER_KV_CACHE_TYPE  - KV cache 量化类型，默认 q4_0
  VIDUNDER_MINICPM_ONNX_PROVIDER - MiniCPM-V vision ONNX 推理设备，默认 cuda，可改 cpu
  VIDUNDER_GLM_OCR_ONNX_PROVIDER - GLM-OCR vision ONNX 推理设备，默认 cuda，可改 cpu
  VIDUNDER_GLM_OCR_ONNX_PRECISION - GLM-OCR ONNX 精度，默认 q4，可改 fp32/auto
  VIDUNDER_GLM_OCR_ONNX_THREADS - GLM-OCR CPU ONNX 线程数，默认 4
  VIDUNDER_GLM_OCR_WORKER_TIMEOUT - GLM-OCR ONNX worker 单次超时秒数，默认 180
  VIDUNDER_HWACCEL        - FFmpeg 抽帧硬解，默认 none，可改 cuda/vaapi
  VIDUNDER_VIDEO_PATH     - 输入视频路径
  VIDUNDER_SRT_PATH       - 输入字幕路径
"""
import os
from pathlib import Path

MODEL_ROOT = Path(os.environ.get("VIDUNDER_MODEL_ROOT", str(Path(__file__).parent / "models")))

PROJECT_DIR = Path(__file__).parent
MEDIA_VIDUNDER = PROJECT_DIR.parent / "media" / "vidunder"
DB_DIR = MEDIA_VIDUNDER / "db"
TOKENS_DIR = DB_DIR / "tokens"
EXPORT_DIR = MODEL_ROOT / "minicpm-v4.5" / "onnx"
GGUF_PATH = MODEL_ROOT / "minicpm-v4.5" / "MiniCPM-V-4_5-Q4_K_M.gguf"

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
GEMINI_API_KEY = os.environ.get("VIDUNDER_GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("VIDUNDER_GEMINI_MODEL", "gemini-3.1-pro-preview")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

NPPS = 70
EMBED_DIM = 4096

EMBED_MODEL_PATH = str(MODEL_ROOT / "embedding" / "bge-small-zh-v1.5")

GLM_OCR_GGUF = str(MODEL_ROOT / "glm-ocr" / "GLM-OCR-Q8_0.gguf")
GLM_OCR_ONNX_DIR = str(MODEL_ROOT / "glm-ocr" / "glm-ocr-onnx")

OPENROUTER_KEY = os.environ.get("VIDUNDER_OPENROUTER_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "google/gemini-2.5-flash"

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
GLM_OCR_N_GPU_LAYERS = int(os.environ.get("VIDUNDER_GLM_OCR_N_GPU_LAYERS", "99"))
N_BATCH = int(os.environ.get("VIDUNDER_N_BATCH", "512"))
KV_CACHE_TYPE = os.environ.get("VIDUNDER_KV_CACHE_TYPE", "q4_0")


def _normalize_onnx_provider(value: str) -> str:
    provider = value.strip().lower()
    if provider in {"cuda_isolated", "isolated_cuda"}:
        return "cuda"
    if provider in {"same_process", "legacy"}:
        return "cpu"
    return provider


ONNX_PROVIDER = os.environ.get(
    "VIDUNDER_MINICPM_ONNX_PROVIDER",
    os.environ.get("VIDUNDER_ONNX_PROVIDER", "cuda"),
)
GLM_OCR_ONNX_PROVIDER = _normalize_onnx_provider(
    os.environ.get(
        "VIDUNDER_GLM_OCR_ONNX_PROVIDER",
        os.environ.get("VIDUNDER_GLM_OCR_MODE", "cuda"),
    )
)
GLM_OCR_ONNX_PRECISION = os.environ.get("VIDUNDER_GLM_OCR_ONNX_PRECISION", "q4")
GLM_OCR_ONNX_THREADS = int(os.environ.get("VIDUNDER_GLM_OCR_ONNX_THREADS", "4"))
GLM_OCR_WORKER_TIMEOUT = int(os.environ.get("VIDUNDER_GLM_OCR_WORKER_TIMEOUT", "180"))
N_PREDICT = 512
VIDEO_PATH = os.environ.get("VIDUNDER_VIDEO_PATH", "")
SRT_PATH = os.environ.get("VIDUNDER_SRT_PATH", "")
SUMMARY_SLIDES_PER_CHAPTER = int(os.environ.get("VIDUNDER_SUMMARY_SLIDES_PER_CHAPTER", "3"))
SUMMARY_LANG = os.environ.get("VIDUNDER_SUMMARY_LANG", "中文")
