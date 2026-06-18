import os
import configparser
from typing import Any
from datetime import datetime, timezone
from django.conf import settings as dj_settings
from django.views import View
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
import time
import urllib.parse
import requests
from asr_utils.transcription_engine import TranscriptionEngineFactory


SETTINGS_FILE = os.path.join(dj_settings.BASE_DIR, "./config/config.ini")
HOTWORD_FILE = os.path.join(dj_settings.BASE_DIR, "./config/hotword.txt")


def _read_default_hotwords() -> str:
    if os.path.exists(HOTWORD_FILE):
        with open(HOTWORD_FILE, encoding="utf-8") as f:
            return f.read().strip()
    return ""


def _ensure_ini():
    """Create a default settings.ini if it doesn't exist."""
    if not os.path.exists(SETTINGS_FILE):
        cfg = configparser.ConfigParser(interpolation=None)
        cfg["DEFAULT"] = {
            "selected_model_provider": "deepseek",
            "deepseek_api_key": "",
            "deepseek_base_url": "https://api.deepseek.com/v1",
            "deepseek_model": "deepseek-chat",
            "openai_api_key": "",
            "openai_base_url": "https://api.openai.com/v1",
            "openai_model": "gpt-4o",
            "qwen_api_key": "",
            "qwen_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "qwen_model": "qwen-plus",
            "ollama_api_key": "",
            "ollama_base_url": "http://127.0.0.1:11434",
            "ollama_model": "llama3",
            "lmstudio_api_key": "",
            "lmstudio_base_url": "http://127.0.0.1:1234/v1",
            "lmstudio_model": "",
            "moonshot_api_key": "",
            "moonshot_base_url": "https://api.moonshot.cn/v1",
            "moonshot_model": "moonshot-v1-8k",
            "volcano_api_key": "",
            "volcano_base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "volcano_model": "doubao-seed-2-0-lite-260428",
            "openrouter_api_key": "",
            "openrouter_base_url": "https://openrouter.ai/api/v1",
            "openrouter_model": "google/gemini-3-flash",
            "cerebras_api_key": "",
            "cerebras_base_url": "https://api.cerebras.ai/v1",
            "cerebras_model": "llama3.1-8b",
            "local_api_key": "",
            "local_base_url": "http://localhost:1234/v1",
            "local_model": "",
            "split_use_proxy": "false",
            "split_num_threads": "8",
            "enable_split": "true",
            "enable_split": "true",
            "translate_selected_model_provider": "deepseek",
            "translate_deepseek_api_key": "",
            "translate_deepseek_base_url": "https://api.deepseek.com/v1",
            "translate_deepseek_model": "deepseek-chat",
            "translate_openai_api_key": "",
            "translate_openai_base_url": "https://api.openai.com/v1",
            "translate_openai_model": "gpt-4o",
            "translate_qwen_api_key": "",
            "translate_qwen_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "translate_qwen_model": "qwen-plus",
            "translate_ollama_api_key": "",
            "translate_ollama_base_url": "http://127.0.0.1:11434",
            "translate_ollama_model": "llama3",
            "translate_lmstudio_api_key": "",
            "translate_lmstudio_base_url": "http://127.0.0.1:1234/v1",
            "translate_lmstudio_model": "",
            "translate_moonshot_api_key": "",
            "translate_moonshot_base_url": "https://api.moonshot.cn/v1",
            "translate_moonshot_model": "moonshot-v1-8k",
            "translate_volcano_api_key": "",
            "translate_volcano_base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "translate_volcano_model": "doubao-seed-2-0-lite-260428",
            "translate_openrouter_api_key": "",
            "translate_openrouter_base_url": "https://openrouter.ai/api/v1",
            "translate_openrouter_model": "google/gemini-3-flash",
            "translate_cerebras_api_key": "",
            "translate_cerebras_base_url": "https://api.cerebras.ai/v1",
            "translate_cerebras_model": "llama3.1-8b",
            "translate_local_api_key": "",
            "translate_local_base_url": "http://localhost:1234/v1",
            "translate_local_model": "",
            "translate_use_proxy": "false",
            "translate_num_threads": "8",
            "enable_translate": "true",
            "plain_translate": "false",
            "hotwords": _read_default_hotwords(),
        }
        cfg["Video watch"] = {"raw_language": "zh", "default_translate_lang": "zh"}
        cfg["Subtitle settings"] = {
            "font_family": "宋体",
            "preview_text": "这是字幕预设文本",
            "font_color": "#ea9749",
            "font_size": "18",
            "font_weight": "400",
            "background_color": "#000000",
            "border_radius": "4",
            "text_shadow": "false",
            "text_stroke": "false",
            "text_stroke_color": "#000000",
            "text_stroke_width": "2",
            "background_style": "semi-transparent",
            "bottom_distance": "80",
        }
        cfg["Foreign Subtitle settings"] = {
            "foreign_font_family": "Arial",
            "foreign_preview_text": "This is foreign subtitle preview",
            "foreign_font_color": "#ffffff",
            "foreign_font_size": "16",
            "foreign_font_weight": "400",
            "foreign_background_color": "#000000",
            "foreign_border_radius": "4",
            "foreign_text_shadow": "false",
            "foreign_text_stroke": "false",
            "foreign_text_stroke_color": "#000000",
            "foreign_text_stroke_width": "2",
            "foreign_background_style": "semi-transparent",
            "foreign_bottom_distance": "120",
        }
        cfg["Media Credentials"] = {
            "bilibili_sessdata": "",
            "proxy_url": "",
            "download_use_proxy": "false",
            "bili_download_use_proxy": "false",
        }
        cfg["Transcription Engine"] = {
            "primary_engine": "funasr_gguf",
            "fallback_engine": "",
            "transcription_mode": "local",
            "elevenlabs_api_key": "",
            "elevenlabs_model": "scribe_v1",
            "include_punctuation": "true",
            "vad_backend": "silero",
        }
        cfg["Video Understanding"] = {
            "vu_thinking_budget": "low",
            "vu_n_gpu_layers": "36",
            "vu_glm_ocr_n_gpu_layers": "17",
            "vu_corner_provider": "gemini",
            "vu_corner_gemini_api_key": "",
            "vu_corner_gemini_base_url": "https://openrouter.ai/api/v1",
            "vu_corner_gemini_model": "google/gemini-2.5-flash",
            "vu_corner_mimo_api_key": "",
            "vu_corner_mimo_base_url": "",
            "vu_corner_mimo_model": "mimo-v2.5",
            "vu_corner_openai_api_key": "",
            "vu_corner_openai_base_url": "",
            "vu_corner_openai_model": "",
            "vu_summary_api_key": "",
            "vu_summary_base_url": "https://api.deepseek.com",
        "vu_summary_model": "deepseek-chat",
        "vu_corner_use_proxy": "false",
        "vu_summary_use_proxy": "false",
        "vu_knowledge_use_proxy": "false",
            "vu_corner_use_proxy": "false",
            "vu_summary_use_proxy": "false",
            "vu_knowledge_use_proxy": "false",
            "vu_download_use_proxy": "false",
            "vu_use_proxy": "false",
            "vu_knowledge_provider": "doubao",
            "vu_knowledge_api_key": "",
            "vu_knowledge_base_url": "",
            "vu_knowledge_model": "",
        }
        with open(SETTINGS_FILE, "w") as fp:
            cfg.write(fp)


def load_all_settings():
    """Return all settings from config.ini as a dictionary."""
    _ensure_ini()
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(SETTINGS_FILE)

    # Auto-migrate: use_proxy → split_use_proxy + translate_use_proxy
    modified = False
    if cfg.has_option("DEFAULT", "use_proxy") and not cfg.has_option(
        "DEFAULT", "split_use_proxy"
    ):
        old_val = cfg.get("DEFAULT", "use_proxy")
        cfg.set("DEFAULT", "split_use_proxy", old_val)
        cfg.set("DEFAULT", "translate_use_proxy", old_val)
        cfg.remove_option("DEFAULT", "use_proxy")
        modified = True

    if not cfg.has_option("DEFAULT", "split_use_proxy"):
        cfg.set("DEFAULT", "split_use_proxy", "false")
        modified = True

    if not cfg.has_option("DEFAULT", "translate_use_proxy"):
        cfg.set("DEFAULT", "translate_use_proxy", "false")
        modified = True

    if not cfg.has_option("DEFAULT", "plain_translate"):
        cfg.set("DEFAULT", "plain_translate", "false")
        modified = True

    # Auto-migrate: fill hotwords from hotword.txt if empty
    hotwords_val = cfg.get("DEFAULT", "hotwords", fallback="").strip()
    if not hotwords_val:
        default = _read_default_hotwords()
        if default:
            cfg.set("DEFAULT", "hotwords", default)
            modified = True

    # Auto-migrate: add translate LLM fields if missing
    if not cfg.has_option("DEFAULT", "translate_selected_model_provider"):
        # Copy from split LLM as defaults
        cfg.set(
            "DEFAULT",
            "translate_selected_model_provider",
            cfg.get("DEFAULT", "selected_model_provider", fallback="deepseek"),
        )
        for provider in ["deepseek", "openai", "glm", "qwen", "local"]:
            for suffix in ["api_key", "base_url"]:
                src_key = f"{provider}_{suffix}"
                dst_key = f"translate_{provider}_{suffix}"
                if not cfg.has_option("DEFAULT", dst_key):
                    cfg.set(
                        "DEFAULT",
                        dst_key,
                        cfg.get("DEFAULT", src_key, fallback=""),
                    )
    # Auto-migrate: stream_download_proxy → proxy_url + download_use_proxy
    if cfg.has_section("Media Credentials"):
        if cfg.has_option("Media Credentials", "stream_download_proxy"):
            old_proxy = cfg.get("Media Credentials", "stream_download_proxy").strip()
            if old_proxy and not cfg.has_option("Media Credentials", "proxy_url"):
                cfg.set("Media Credentials", "proxy_url", old_proxy)
                cfg.set("Media Credentials", "download_use_proxy", "true")
            cfg.remove_option("Media Credentials", "stream_download_proxy")
            modified = True
        if not cfg.has_option("Media Credentials", "proxy_url"):
            cfg.set("Media Credentials", "proxy_url", "")
            modified = True
        if not cfg.has_option("Media Credentials", "download_use_proxy"):
            cfg.set("Media Credentials", "download_use_proxy", "false")
            modified = True
        if not cfg.has_option("Media Credentials", "bili_download_use_proxy"):
            cfg.set("Media Credentials", "bili_download_use_proxy", "false")
            modified = True

    # Auto-migrate: add default_translate_lang to Video watch
    if cfg.has_section("Video watch") and not cfg.has_option(
        "Video watch", "default_translate_lang"
    ):
        cfg.set("Video watch", "default_translate_lang", "zh")
        modified = True

    # Auto-migrate: ensure [Video Understanding] section exists
    vu_defaults = {
        "vu_thinking_budget": "low",
        "vu_n_gpu_layers": "36",
        "vu_glm_ocr_n_gpu_layers": "17",
        "vu_corner_provider": "gemini",
        "vu_corner_gemini_api_key": "",
        "vu_corner_gemini_base_url": "https://openrouter.ai/api/v1",
        "vu_corner_gemini_model": "google/gemini-2.5-flash",
        "vu_corner_mimo_api_key": "",
        "vu_corner_mimo_base_url": "",
        "vu_corner_mimo_model": "mimo-v2.5",
            "vu_corner_openai_api_key": "",
            "vu_corner_openai_base_url": "",
            "vu_corner_openai_model": "",
        "vu_summary_api_key": "",
        "vu_summary_base_url": "https://api.deepseek.com",
        "vu_summary_model": "deepseek-chat",
        "vu_knowledge_provider": "doubao",
        "vu_knowledge_api_key": "",
        "vu_knowledge_base_url": "",
        "vu_knowledge_model": "",
        "vu_download_use_proxy": "false",
    }
    if not cfg.has_section("Video Understanding"):
        cfg.add_section("Video Understanding")
        for k, v in vu_defaults.items():
            cfg.set("Video Understanding", k, v)
        modified = True
    else:
        # Ensure all keys exist even if section exists
        for k, v in vu_defaults.items():
            if not cfg.has_option("Video Understanding", k):
                cfg.set("Video Understanding", k, v)
                modified = True

    # Auto-migrate: add vad_backend to Transcription Engine if missing
    if cfg.has_section("Transcription Engine") and not cfg.has_option(
        "Transcription Engine", "vad_backend"
    ):
        cfg.set("Transcription Engine", "vad_backend", "silero")
        modified = True

    # Save config if sections were added
    if modified:
        with open(SETTINGS_FILE, "w") as fp:
            cfg.write(fp)

    result = {}
    for section_name in cfg.sections():
        result[section_name] = dict(cfg[section_name])

    # Add DEFAULT section
    result["DEFAULT"] = dict(cfg["DEFAULT"])

    return result


def save_all_settings(settings_dict: dict[str, Any]):
    """Save all settings to config.ini."""
    cfg = configparser.ConfigParser(interpolation=None)

    for section_name, section_data in settings_dict.items():
        if section_name == "DEFAULT":
            cfg["DEFAULT"] = section_data
        else:
            cfg[section_name] = section_data

    with open(SETTINGS_FILE, "w") as fp:
        cfg.write(fp)


def _get_media_credentials(settings_data: dict[str, Any]) -> dict[str, Any]:
    media_settings = settings_data.setdefault("Media Credentials", {})
    if not isinstance(media_settings, dict):
        media_settings = {}
        settings_data["Media Credentials"] = media_settings
    return media_settings


def _normalize_bilibili_sessdata(value: str) -> str:
    """Accept raw SESSDATA or a full Cookie header and return only SESSDATA."""
    value = (value or "").strip().strip('"').strip("'")
    if not value:
        return ""

    if "SESSDATA=" not in value:
        return value

    for part in value.split(";"):
        key, sep, cookie_value = part.strip().partition("=")
        if sep and key.strip().lower() == "sessdata":
            return cookie_value.strip()
    return value


def _bilibili_sessdata_status(value: str) -> dict[str, Any]:
    value = (value or "").strip()
    status: dict[str, Any] = {
        "configured": bool(value),
        "length": len(value),
        "expires_at": None,
        "expired": None,
    }

    if not value:
        return status

    decoded = urllib.parse.unquote(value)
    parts = decoded.split(",")
    if len(parts) >= 2:
        try:
            expiry = int(parts[1])
        except ValueError:
            expiry = 0
        if expiry > 0:
            status["expires_at"] = datetime.fromtimestamp(
                expiry, tz=timezone.utc
            ).isoformat()
            status["expired"] = expiry <= int(time.time())

    return status


def _bilibili_proxy_config(settings_data: dict[str, Any]) -> dict[str, str | None]:
    media_settings = settings_data.get("Media Credentials", {})
    if not isinstance(media_settings, dict):
        return {"http": None, "https": None}

    use_proxy = (
        str(media_settings.get("bili_download_use_proxy", "false")).lower() == "true"
    )
    if not use_proxy:
        return {"http": None, "https": None}

    proxy_url = str(media_settings.get("proxy_url", "")).strip()
    if proxy_url:
        return {"http": proxy_url, "https": proxy_url}

    return {
        "http": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        "https": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
    }


def _validate_bilibili_sessdata(
    value: str,
    settings_data: dict[str, Any],
) -> dict[str, Any]:
    status = _bilibili_sessdata_status(value)
    validation: dict[str, Any] = {
        "checked": False,
        "valid": False,
        "is_login": False,
        "username": None,
        "uid": None,
        "bili_code": None,
        "message": "",
        "error": None,
    }
    status["validation"] = validation

    if not status["configured"]:
        validation["message"] = "SESSDATA is not configured"
        return status

    if status["expired"] is True:
        validation["checked"] = True
        validation["message"] = "SESSDATA appears expired"
        return status

    headers = {
        "Accept": "application/json",
        "Cookie": f"SESSDATA={value}",
        "Referer": "https://www.bilibili.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    try:
        response = requests.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers=headers,
            proxies=_bilibili_proxy_config(settings_data),
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        validation["checked"] = True
        validation["error"] = str(exc)
        validation["message"] = "Failed to validate SESSDATA against Bilibili"
        return status

    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        data = {}

    is_login = bool(data.get("isLogin"))
    uid = data.get("mid")
    username = data.get("uname") or data.get("name")
    validation.update(
        {
            "checked": True,
            "valid": is_login and bool(uid),
            "is_login": is_login,
            "username": username or None,
            "uid": uid or None,
            "bili_code": payload.get("code") if isinstance(payload, dict) else None,
            "message": (
                "SESSDATA is valid"
                if is_login and uid
                else (payload.get("message") or "SESSDATA is not logged in")
            ),
        }
    )

    return status


client: Any | None = None


def _init_client(
    api_key: str, base_url: str, allow_empty_key: bool = False, use_proxy: bool = True
):
    """(Re)initialise global OpenAI client instance."""
    global client
    from openai import OpenAI
    import httpx

    if base_url:
        key = api_key if api_key or not allow_empty_key else "dummy-key"
        if use_proxy:
            client = OpenAI(api_key=key, base_url=base_url)
        else:
            http_client = httpx.Client(proxy=None, timeout=60, trust_env=False)
            client = OpenAI(api_key=key, base_url=base_url, http_client=http_client)
    else:
        client = None


@method_decorator(csrf_exempt, name="dispatch")
class ConfigAPIView(View):
    """API endpoints for getting and setting all configuration."""

    http_method_names = ["get", "post"]

    def get(self, request: HttpRequest, *args, **kwargs):
        """Get all configuration settings."""
        try:
            settings_data = load_all_settings()
            return JsonResponse({"success": True, "data": settings_data})
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)

    def post(self, request: HttpRequest, *args, **kwargs):
        """Update all configuration settings."""
        try:
            if request.content_type == "application/json":
                data = json.loads(request.body)
            else:
                return JsonResponse(
                    {"error": "Content-Type must be application/json"}, status=400
                )

            settings_dict = data.get("settings", {})
            if not settings_dict:
                return JsonResponse({"error": "Settings data is required"}, status=400)

            save_all_settings(settings_dict)

            if "DEFAULT" in settings_dict:
                cfg = settings_dict["DEFAULT"]
                selected_provider = cfg.get("selected_model_provider", "deepseek")
                api_key = cfg.get(f"{selected_provider}_api_key", "")
                base_url = cfg.get(f"{selected_provider}_base_url", "")

                from utils.llm_client import ClientPool
                use_proxy = cfg.get("split_use_proxy", "false").lower() == "true"
                proxy_url = cfg.get("proxy_url", "")

                ClientPool.clear()
                _init_client(
                    api_key,
                    base_url,
                    allow_empty_key=(selected_provider in ["local", "ollama", "lmstudio"]),
                    use_proxy=use_proxy,
                )

            return JsonResponse(
                {"success": True, "message": "Settings updated successfully"}
            )

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class BilibiliSessDataAPIView(View):
    """Dedicated API for Bilibili SESSDATA without exposing full config."""

    http_method_names = ["get", "post", "delete"]

    def get(self, request: HttpRequest, *args, **kwargs):
        try:
            settings_data = load_all_settings()
            media_settings = _get_media_credentials(settings_data)
            sessdata = media_settings.get("bilibili_sessdata", "")
            should_validate = str(
                request.GET.get("validate", "")
            ).lower() in {"1", "true", "yes"}
            data = (
                _validate_bilibili_sessdata(sessdata, settings_data)
                if should_validate
                else _bilibili_sessdata_status(sessdata)
            )
            return JsonResponse(
                {"success": True, "data": data}
            )
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)

    def post(self, request: HttpRequest, *args, **kwargs):
        try:
            if request.content_type != "application/json":
                return JsonResponse(
                    {"error": "Content-Type must be application/json"}, status=400
                )

            data = json.loads(request.body)
            sessdata = _normalize_bilibili_sessdata(
                data.get("sessdata") or data.get("bilibili_sessdata") or ""
            )
            if not sessdata:
                return JsonResponse({"error": "sessdata is required"}, status=400)

            settings_data = load_all_settings()
            media_settings = _get_media_credentials(settings_data)
            media_settings["bilibili_sessdata"] = sessdata
            save_all_settings(settings_data)

            return JsonResponse(
                {
                    "success": True,
                    "message": "Bilibili SESSDATA updated",
                    "data": _bilibili_sessdata_status(sessdata),
                }
            )

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)

    def delete(self, request: HttpRequest, *args, **kwargs):
        try:
            settings_data = load_all_settings()
            media_settings = _get_media_credentials(settings_data)
            media_settings["bilibili_sessdata"] = ""
            save_all_settings(settings_data)
            return JsonResponse(
                {
                    "success": True,
                    "message": "Bilibili SESSDATA cleared",
                    "data": _bilibili_sessdata_status(""),
                }
            )
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class TranscriptionEnginesAPIView(View):
    """API endpoint for getting available transcription engines."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, *args, **kwargs):
        """Get available transcription engines and their info."""
        try:
            # Load current settings to check engine availability
            settings_data = load_all_settings()

            # Get engine info
            engine_info = TranscriptionEngineFactory.get_engine_info()

            # Get available engines based on current config
            available_engines = TranscriptionEngineFactory.get_available_engines(
                settings_data
            )

            # Combine info with availability status
            engines_with_status = {}
            for engine_type, info in engine_info.items():
                engines_with_status[engine_type] = {
                    **info,
                    "available": engine_type in available_engines,
                }

            return JsonResponse(
                {
                    "success": True,
                    "data": {
                        "engines": engines_with_status,
                        "available_engines": available_engines,
                    },
                }
            )

        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class LLMTestAPIView(View):
    """API endpoint to test LLM connection by sending a simple prompt."""

    http_method_names = ["get"]

    def _resolve_provider_config(
        self, cfg: dict[str, str], prefix: str
    ) -> tuple[str, str, str, str]:
        if prefix:
            selected_provider = cfg.get(f"{prefix}_selected_model_provider", "deepseek")
        else:
            selected_provider = cfg.get("selected_model_provider", "deepseek")

        p = prefix + "_" if prefix else ""
        api_key = cfg.get(f"{p}{selected_provider}_api_key", "")
        base_url = cfg.get(f"{p}{selected_provider}_base_url", "")
        model = cfg.get(f"{p}{selected_provider}_model", "")

        from utils.llm_client import PROVIDER_DEFAULTS
        defaults = PROVIDER_DEFAULTS.get(selected_provider, PROVIDER_DEFAULTS['local'])
        if not base_url:
            base_url = defaults['url']
        if not model:
            model = defaults['default_model']

        return selected_provider, api_key, base_url, model

    def get(self, request: HttpRequest, *args, **kwargs):
        llm_type = request.GET.get("type", "split")
        prefix = "translate" if llm_type == "translate" else ""
        proxy_key = (
            "translate_use_proxy" if llm_type == "translate" else "split_use_proxy"
        )

        original_proxy: dict[str, str] = {}

        try:
            settings_data = load_all_settings()
            cfg = settings_data.get("DEFAULT", {})

            use_proxy = cfg.get(proxy_key, "false").lower() == "true"
            if not use_proxy:
                for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
                    if key in os.environ:
                        original_proxy[key] = os.environ.pop(key)
            else:
                if "HTTP_PROXY" in os.environ:
                    os.environ["http_proxy"] = os.environ["HTTP_PROXY"]
                if "HTTPS_PROXY" in os.environ:
                    os.environ["https_proxy"] = os.environ["HTTPS_PROXY"]

            selected_provider, api_key, base_url, model = self._resolve_provider_config(
                cfg, prefix
            )

            if not base_url:
                result = {
                    "success": False,
                    "error": f"Base URL not configured for provider: {selected_provider}",
                }
                for key, value in original_proxy.items():
                    os.environ[key] = value
                return JsonResponse(result, status=400)
            if not api_key and selected_provider not in ["local", "ollama", "lmstudio"]:
                result = {
                    "success": False,
                    "error": f"API key not configured for provider: {selected_provider}",
                }
                for key, value in original_proxy.items():
                    os.environ[key] = value
                return JsonResponse(result, status=400)

            _init_client(
                api_key,
                base_url,
                allow_empty_key=(selected_provider in ["local", "ollama", "lmstudio"]),
                use_proxy=use_proxy,
            )

            if not model:
                result = {
                    "success": False,
                    "error": f"Model not configured for provider: {selected_provider}",
                }
                for key, value in original_proxy.items():
                    os.environ[key] = value
                return JsonResponse(result, status=400)

            if client is None:
                raise RuntimeError("LLM client initialization failed")

            # Send test prompt
            prompt = 'Hello, please respond with "Connection successful!"'
            print(
                f"[LLM-TEST] Provider: {selected_provider}, Model: {model}, URL: {base_url}"
            )
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=60,
                )
                content = response.choices[0].message.content
                result = {"success": True, "response": content}
            except Exception as e:
                print(f"[LLM-TEST] Error: {type(e).__name__}: {e}")
                result = {"success": False, "error": f"{type(e).__name__}: {e}"}
            finally:
                # Restore original proxy settings
                for key, value in original_proxy.items():
                    os.environ[key] = value
            if not result.get("success"):
                return JsonResponse(result, status=500)
            return JsonResponse(result)
        except Exception as exc:
            # Restore original proxy settings on error
            for key, value in original_proxy.items():
                os.environ[key] = value
            return JsonResponse({"success": False, "error": str(exc)}, status=500)


# Global dictionary to track download progress
download_progress = {}


@method_decorator(csrf_exempt, name="dispatch")
class WhisperModelAPIView(View):
    """API endpoints for Whisper model management."""

    http_method_names = ["get", "post"]

    def get(self, request: HttpRequest, *args, **kwargs):
        """Get available models and download status."""
        try:
            # Get current engine to determine which models to show
            settings_data = load_all_settings()
            current_engine = settings_data.get("Transcription Engine", {}).get(
                "primary_engine", "funasr_gguf"
            )
            current_model = ""

            available_models = []
            engine_name = current_engine

            return JsonResponse(
                {
                    "success": True,
                    "data": {
                        "models": available_models,
                        "current_model": current_model,
                        "current_engine": current_engine,
                    },
                }
            )

        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)

    def post(self, request: HttpRequest, *args, **kwargs):
        """Download a Whisper model."""
        try:
            if request.content_type == "application/json":
                data = json.loads(request.body)
            else:
                return JsonResponse(
                    {"error": "Content-Type must be application/json"}, status=400
                )

            model_name = data.get("model_name")

            if not model_name:
                return JsonResponse({"error": "model_name is required"}, status=400)

            # Check if already downloading
            if model_name in download_progress:
                return JsonResponse(
                    {"error": "Model is already being downloaded"}, status=409
                )

            # Start download in background thread
            import threading
            import subprocess

            def download_model():
                try:
                    import time

                    download_progress[model_name] = 0
                    models_dir = os.path.join(dj_settings.BASE_DIR, "models")
                    os.makedirs(models_dir, exist_ok=True)

                    # Use bash script to download whisper.cpp GGML models
                    script_path = os.path.join(
                        dj_settings.BASE_DIR, "scripts", "download_whisper_models.sh"
                    )

                    print(
                        f"[whisper.cpp] Starting download of {model_name} using {script_path}"
                    )

                    # Set WHISPER_MODEL_DIR environment variable
                    env = os.environ.copy()
                    env["WHISPER_MODEL_DIR"] = models_dir

                    # Execute bash script with model name as argument
                    result = subprocess.run(
                        ["bash", script_path, model_name],
                        env=env,
                        capture_output=True,
                        text=True,
                        check=True,
                    )

                    print(f"[whisper.cpp] Download output: {result.stdout}")

                    if result.stderr:
                        print(f"[whisper.cpp] Download stderr: {result.stderr}")

                    download_progress[model_name] = 100
                    print(f"[whisper.cpp] Download completed for {model_name}")

                    # Keep the download status for a while so frontend can see completion
                    time.sleep(3)
                    if model_name in download_progress:
                        del download_progress[model_name]

                except subprocess.CalledProcessError as e:
                    print(
                        f"[whisper.cpp] Model download script failed for {model_name}: {e.stderr}"
                    )
                    if model_name in download_progress:
                        download_progress[model_name] = -1  # Error state
                except Exception as e:
                    print(f"Model download failed for {model_name}: {e}")
                    if model_name in download_progress:
                        download_progress[model_name] = -1  # Error state

            thread = threading.Thread(target=download_model)
            thread.daemon = True
            thread.start()

            return JsonResponse(
                {"success": True, "message": f"Started downloading {model_name}"}
            )

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)


# Add a new API endpoint for getting download progress
class WhisperModelProgressAPIView(View):
    """API endpoint specifically for getting model download progress."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, *args, **kwargs):
        """Get current download progress for all models."""
        try:
            return JsonResponse({"success": True, "progress": dict(download_progress)})
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)


# Add a new API endpoint for checking model folder size
class WhisperModelSizeAPIView(View):
    """API endpoint for checking model folder size."""

    http_method_names = ["post"]

    def post(self, request: HttpRequest, *args, **kwargs):
        """Get the actual size of a model folder."""
        try:
            if request.content_type == "application/json":
                data = json.loads(request.body)
            else:
                return JsonResponse(
                    {"error": "Content-Type must be application/json"}, status=400
                )

            model_name = data.get("model_name")
            if not model_name:
                return JsonResponse({"error": "model_name is required"}, status=400)

            # Calculate folder size
            models_dir = os.path.join(dj_settings.BASE_DIR, "models")
            model_path = models_dir

            if not os.path.exists(model_path):
                return JsonResponse(
                    {
                        "success": True,
                        "size": 0,
                        "size_mb": 0,
                        "size_human": "0 B",
                        "exists": False,
                    }
                )

            # Calculate total size of all files in the folder
            total_size = 0
            file_count = 0
            for root, dirs, files in os.walk(model_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
                        file_count += 1

            # Human readable size
            def format_size(bytes_size):
                for unit in ["B", "KB", "MB", "GB"]:
                    if bytes_size < 1024.0:
                        return f"{bytes_size:.1f} {unit}"
                    bytes_size /= 1024.0
                return f"{bytes_size:.1f} TB"

            return JsonResponse(
                {
                    "success": True,
                    "size": total_size,
                    "size_mb": total_size / (1024 * 1024),
                    "size_human": format_size(total_size),
                    "file_count": file_count,
                    "exists": True,
                }
            )

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)
