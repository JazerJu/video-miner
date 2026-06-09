# pyright: reportMissingImports=false
"""vidUnder model download API.

Downloads run in background threads and expose polling-friendly byte progress,
matching the Whisper model API style without reusing its subprocess downloader.
"""

import json
import threading
from pathlib import Path
from typing import Any, Literal, TypedDict
from urllib.parse import quote

import requests
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt


PROJECT_DIR = Path(__file__).resolve().parent
HF_PROXY = "http://127.0.0.1:36990"
CHUNK_SIZE = 1024 * 1024
REQUEST_TIMEOUT = (15, 60)


DownloadSource = Literal["hf", "ms"]


class ModelFile(TypedDict):
    repo_path: str
    local_path: str
    size: int


class ModelGroup(TypedDict):
    label: str
    description: str
    files: list[ModelFile]


MODEL_GROUPS: dict[str, ModelGroup] = {
    "minicpm-v4.5": {
        "label": "MiniCPM-V 4.5",
        "description": "Vision encoder + LLM decoder",
        "files": [
            {
                "repo_path": "minicpmv/MiniCPM-V-4_5-Q4_K_M.gguf",
                "local_path": "models/MiniCPM-V-4_5-Q4_K_M.gguf",
                "size": 5026714304,
            },
            {
                "repo_path": "minicpmv/minicpmv_v45_siglip.fp32.onnx",
                "local_path": "onnx/minicpmv_v45_siglip.fp32.onnx",
                "size": 1671404498,
            },
            {
                "repo_path": "minicpmv/minicpmv_v45_resampler_temporal.fp16.onnx",
                "local_path": "onnx/minicpmv_v45_resampler_temporal.fp16.onnx",
                "size": 24169,
            },
            {
                "repo_path": "minicpmv/minicpmv_v45_resampler_temporal.fp16.onnx.data",
                "local_path": "onnx/minicpmv_v45_resampler_temporal.fp16.onnx.data",
                "size": 177864704,
            },
        ],
    },
    "glm-ocr": {
        "label": "GLM-OCR",
        "description": "OCR engine (ONNX vision + GGUF decoder)",
        "files": [
            {
                "repo_path": "glm-ocr/GLM-OCR-Q8_0.gguf",
                "local_path": "models/GLM-OCR-Q8_0.gguf",
                "size": 950433408,
            },
            {
                "repo_path": "glm-ocr/onnx/vision_encoder_q4.onnx",
                "local_path": "glm-ocr-onnx/onnx/vision_encoder_q4.onnx",
                "size": 424697,
            },
            {
                "repo_path": "glm-ocr/onnx/vision_encoder_q4.onnx_data",
                "local_path": "glm-ocr-onnx/onnx/vision_encoder_q4.onnx_data",
                "size": 373217280,
            },
            {
                "repo_path": "glm-ocr/onnx/embed_tokens_q4.onnx",
                "local_path": "glm-ocr-onnx/onnx/embed_tokens_q4.onnx",
                "size": 854,
            },
            {
                "repo_path": "glm-ocr/onnx/embed_tokens_q4.onnx_data",
                "local_path": "glm-ocr-onnx/onnx/embed_tokens_q4.onnx_data",
                "size": 58441728,
            },
            {
                "repo_path": "glm-ocr/onnx/merger_fp16.onnx",
                "local_path": "glm-ocr-onnx/onnx/merger_fp16.onnx",
                "size": 47195673,
            },
            {
                "repo_path": "glm-ocr/tokenizer.json",
                "local_path": "glm-ocr-onnx/tokenizer.json",
                "size": 5420559,
            },
            {
                "repo_path": "glm-ocr/config.json",
                "local_path": "glm-ocr-onnx/config.json",
                "size": 2022,
            },
            {
                "repo_path": "glm-ocr/generation_config.json",
                "local_path": "glm-ocr-onnx/generation_config.json",
                "size": 166,
            },
            {
                "repo_path": "glm-ocr/preprocessor_config.json",
                "local_path": "glm-ocr-onnx/preprocessor_config.json",
                "size": 366,
            },
            {
                "repo_path": "glm-ocr/processor_config.json",
                "local_path": "glm-ocr-onnx/processor_config.json",
                "size": 1495,
            },
            {
                "repo_path": "glm-ocr/tokenizer_config.json",
                "local_path": "glm-ocr-onnx/tokenizer_config.json",
                "size": 5855,
            },
        ],
    },
    "embedding": {
        "label": "BGE Embedding",
        "description": "Text embedding for similarity search",
        "files": [
            {
                "repo_path": "embedding/bge-small-zh-v1.5-onnx/model.onnx",
                "local_path": "models/bge-small-zh-v1.5-onnx/model.onnx",
                "size": 94835369,
            },
            {
                "repo_path": "embedding/bge-small-zh-v1.5-onnx/tokenizer.json",
                "local_path": "models/bge-small-zh-v1.5-onnx/tokenizer.json",
                "size": 439125,
            },
            {
                "repo_path": "embedding/bge-small-zh-v1.5-onnx/config.json",
                "local_path": "models/bge-small-zh-v1.5-onnx/config.json",
                "size": 688,
            },
            {
                "repo_path": "embedding/bge-small-zh-v1.5-onnx/special_tokens_map.json",
                "local_path": "models/bge-small-zh-v1.5-onnx/special_tokens_map.json",
                "size": 695,
            },
            {
                "repo_path": "embedding/bge-small-zh-v1.5-onnx/tokenizer_config.json",
                "local_path": "models/bge-small-zh-v1.5-onnx/tokenizer_config.json",
                "size": 1273,
            },
            {
                "repo_path": "embedding/bge-small-zh-v1.5-onnx/vocab.txt",
                "local_path": "models/bge-small-zh-v1.5-onnx/vocab.txt",
                "size": 109540,
            },
        ],
    },
}


_download_progress: dict[str, dict[str, Any]] = {}
_download_cancel_flags: dict[str, threading.Event] = {}
_download_lock = threading.Lock()


def _json_response(data: dict[str, Any], status: int = 200) -> JsonResponse:
    response = JsonResponse(data, status=status)
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def _model_files(group: ModelGroup) -> list[ModelFile]:
    return [
        {
            "repo_path": file_info["repo_path"],
            "local_path": file_info["local_path"],
            "size": file_info["size"],
        }
        for file_info in group["files"]
    ]


def _file_path(file_info: ModelFile) -> Path:
    return PROJECT_DIR / file_info["local_path"]


def _file_size(file_info: ModelFile) -> int:
    path = _file_path(file_info)
    return path.stat().st_size if path.exists() else 0


def _is_file_complete(file_info: ModelFile) -> bool:
    return _file_size(file_info) == file_info["size"]


def _calculate_model_status(model_name: str) -> dict[str, int | str]:
    group = MODEL_GROUPS[model_name]
    total_size = sum(file_info["size"] for file_info in group["files"])
    downloaded_size = sum(
        file_info["size"]
        for file_info in group["files"]
        if _is_file_complete(file_info)
    )

    if downloaded_size == total_size:
        status = "downloaded"
    elif downloaded_size > 0:
        status = "partial"
    else:
        status = "not_downloaded"

    return {
        "total_size": total_size,
        "downloaded_size": downloaded_size,
        "status": status,
    }


def _source_url(source: DownloadSource, repo_path: str) -> str:
    encoded_path = quote(repo_path, safe="/")
    if source == "hf":
        return f"https://huggingface.co/JazerJu/VideoMiner/resolve/main/{encoded_path}"
    if source == "ms":
        return (
            "https://modelscope.cn/api/v1/models/modelmo/VideoMiner/repo"
            f"?Revision=master&FilePath={encoded_path}"
        )
    raise ValueError(f"Unknown source: {source}")


def _source_proxies(source: DownloadSource) -> dict[str, str] | None:
    if source == "hf":
        return {"http": HF_PROXY, "https": HF_PROXY}
    return None


def _progress_percent(current: int, total: int) -> int:
    if total <= 0:
        return 0
    return min(int(current * 100 / total), 100)


def _initial_file_progress(group: ModelGroup) -> dict[str, dict[str, int | str]]:
    file_progress = {}
    for file_info in group["files"]:
        repo_path = file_info["repo_path"]
        current = file_info["size"] if _is_file_complete(file_info) else 0
        file_progress[repo_path] = {
            "current": current,
            "total": file_info["size"],
            "percent": _progress_percent(current, file_info["size"]),
            "status": "cached" if current else "pending",
            "local_path": file_info["local_path"],
        }
    return file_progress


def _set_progress(model_name: str, **updates: Any) -> None:
    with _download_lock:
        if model_name in _download_progress:
            _download_progress[model_name].update(updates)


def _set_file_progress(model_name: str, repo_path: str, **updates: Any) -> None:
    with _download_lock:
        progress = _download_progress.get(model_name)
        if not progress:
            return
        progress["files"].setdefault(repo_path, {}).update(updates)


def _is_cancelled(model_name: str) -> bool:
    with _download_lock:
        cancel_flag = _download_cancel_flags.get(model_name)
    return bool(cancel_flag and cancel_flag.is_set())


def _raise_if_cancelled(model_name: str) -> None:
    if _is_cancelled(model_name):
        raise DownloadCancelled("Download cancelled")


def _complete_download(model_name: str) -> None:
    with _download_lock:
        progress = _download_progress.get(model_name)
        if progress:
            progress.update(
                {
                    "current": progress["total"],
                    "percent": 100,
                    "status": "downloaded",
                    "current_file": "",
                    "error": "",
                    "cancel_requested": False,
                }
            )


def _cleanup_later(model_name: str, delay_seconds: int = 30) -> None:
    def cleanup() -> None:
        import time

        time.sleep(delay_seconds)
        with _download_lock:
            progress = _download_progress.get(model_name)
            if progress and progress.get("status") == "downloaded":
                _download_progress.pop(model_name, None)
                _download_cancel_flags.pop(model_name, None)

    threading.Thread(target=cleanup, daemon=True).start()


class DownloadCancelled(Exception):
    """Raised when a background download sees its cancellation flag."""


def _download_file(model_name: str, source: DownloadSource, file_info: ModelFile) -> int:
    repo_path = file_info["repo_path"]
    local_path = _file_path(file_info)
    part_path = local_path.with_name(f"{local_path.name}.part")
    expected_size = file_info["size"]

    if _is_file_complete(file_info):
        _set_file_progress(
            model_name,
            repo_path,
            current=expected_size,
            percent=100,
            status="cached",
        )
        return expected_size

    local_path.parent.mkdir(parents=True, exist_ok=True)
    url = _source_url(source, repo_path)
    proxies = _source_proxies(source)

    _set_file_progress(
        model_name,
        repo_path,
        current=0,
        percent=0,
        status="downloading",
    )
    _set_progress(model_name, current_file=repo_path)

    base_current = 0
    with _download_lock:
        progress = _download_progress.get(model_name)
        if progress:
            base_current = progress["current"]

    try:
        response = requests.get(
            url,
            stream=True,
            proxies=proxies,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        downloaded = 0
        with open(part_path, "wb") as output:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                _raise_if_cancelled(model_name)
                if not chunk:
                    continue

                _ = output.write(chunk)
                downloaded += len(chunk)
                file_percent = _progress_percent(downloaded, expected_size)
                total_current = base_current + downloaded

                _set_file_progress(
                    model_name,
                    repo_path,
                    current=downloaded,
                    percent=file_percent,
                    status="downloading",
                )
                total = int(_download_progress[model_name]["total"])
                _set_progress(
                    model_name,
                    current=total_current,
                    percent=_progress_percent(total_current, total),
                )

        actual_size = part_path.stat().st_size
        if actual_size != expected_size:
            raise ValueError(
                f"Size mismatch for {repo_path}: expected {expected_size}, got {actual_size}"
            )

        part_path.replace(local_path)
        _set_file_progress(
            model_name,
            repo_path,
            current=expected_size,
            percent=100,
            status="downloaded",
        )
        return expected_size
    except Exception:
        if part_path.exists():
            part_path.unlink(missing_ok=True)
        raise


def _download_model(model_name: str, source: DownloadSource) -> None:
    group = MODEL_GROUPS[model_name]
    total_size = sum(file_info["size"] for file_info in group["files"])
    cached_size = sum(
        file_info["size"]
        for file_info in group["files"]
        if _is_file_complete(file_info)
    )

    with _download_lock:
        _download_cancel_flags[model_name] = threading.Event()
        _download_progress[model_name] = {
            "current": cached_size,
            "total": total_size,
            "percent": _progress_percent(cached_size, total_size),
            "status": "downloading",
            "current_file": "",
            "source": source,
            "error": "",
            "cancel_requested": False,
            "files": _initial_file_progress(group),
        }

    try:
        current = cached_size
        for file_info in group["files"]:
            _raise_if_cancelled(model_name)
            repo_path = file_info["repo_path"]
            previous_status = _download_progress[model_name]["files"][repo_path][
                "status"
            ]
            completed_size = _download_file(model_name, source, file_info)

            if previous_status == "cached":
                continue

            current += completed_size
            _set_progress(
                model_name,
                current=current,
                percent=_progress_percent(current, total_size),
            )

        _complete_download(model_name)
        _cleanup_later(model_name)
    except DownloadCancelled as exc:
        _set_progress(
            model_name,
            status="cancelled",
            current_file="",
            error=str(exc),
            cancel_requested=True,
        )
    except Exception as exc:
        _set_progress(
            model_name,
            status="error",
            current_file="",
            error=str(exc),
            cancel_requested=False,
        )


def _model_payload(name: str, group: ModelGroup) -> dict[str, Any]:
    status_info = _calculate_model_status(name)
    with _download_lock:
        active_progress = _download_progress.get(name)
        if active_progress:
            status_info["status"] = active_progress.get("status", status_info["status"])
            status_info["downloaded_size"] = active_progress.get(
                "current", status_info["downloaded_size"]
            )

    return {
        "name": name,
        "label": group["label"],
        "description": group["description"],
        "files": _model_files(group),
        "total_size": status_info["total_size"],
        "downloaded_size": status_info["downloaded_size"],
        "status": status_info["status"],
    }


@method_decorator(csrf_exempt, name="dispatch")
class VidUnderModelAPIView(View):
    """List vidUnder model groups with cache/download status."""

    http_method_names = ["get", "options"]

    def get(self, request):
        models = [
            _model_payload(name, group) for name, group in MODEL_GROUPS.items()
        ]
        return _json_response({"success": True, "data": {"models": models}})

    def options(self, request):
        return _json_response({"success": True})


@method_decorator(csrf_exempt, name="dispatch")
class VidUnderModelDownloadAPIView(View):
    """Start or cancel a vidUnder model download."""

    http_method_names = ["post", "delete", "options"]

    def post(self, request):
        try:
            data = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return _json_response({"success": False, "error": "Invalid JSON"}, status=400)

        model_name = data.get("model_name")
        source = data.get("source", "hf")

        if model_name not in MODEL_GROUPS:
            return _json_response(
                {"success": False, "error": f"Unknown model: {model_name}"},
                status=400,
            )
        if source not in {"hf", "ms"}:
            return _json_response(
                {"success": False, "error": f"Unknown source: {source}"},
                status=400,
            )

        status_info = _calculate_model_status(model_name)
        if status_info["status"] == "downloaded":
            return _json_response(
                {"success": True, "message": "Model already downloaded"}
            )

        with _download_lock:
            progress = _download_progress.get(model_name)
            if progress and progress.get("status") == "downloading":
                return _json_response(
                    {"success": False, "error": "Model is already being downloaded"},
                    status=409,
                )

        thread = threading.Thread(
            target=_download_model,
            args=(model_name, source),
            daemon=True,
        )
        thread.start()
        return _json_response({"success": True, "message": "Download started"})

    def delete(self, request):
        try:
            data = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return _json_response({"success": False, "error": "Invalid JSON"}, status=400)

        model_name = data.get("model_name")
        if model_name not in MODEL_GROUPS:
            return _json_response(
                {"success": False, "error": f"Unknown model: {model_name}"},
                status=400,
            )

        with _download_lock:
            progress = _download_progress.get(model_name)
            cancel_flag = _download_cancel_flags.get(model_name)
            if not progress or progress.get("status") != "downloading" or not cancel_flag:
                return _json_response(
                    {"success": False, "error": "Model is not downloading"},
                    status=409,
                )
            cancel_flag.set()
            progress["cancel_requested"] = True

        return _json_response({"success": True, "message": "Cancellation requested"})

    def options(self, request):
        return _json_response({"success": True})


@method_decorator(csrf_exempt, name="dispatch")
class VidUnderModelProgressAPIView(View):
    """Return current vidUnder model download progress for polling clients."""

    http_method_names = ["get", "options"]

    def get(self, request):
        with _download_lock:
            progress = {
                model_name: dict(model_progress)
                for model_name, model_progress in _download_progress.items()
            }
        return _json_response({"success": True, "progress": progress})

    def options(self, request):
        return _json_response({"success": True})
