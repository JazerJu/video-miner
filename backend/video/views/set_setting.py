import os
import configparser
from django.conf import settings as dj_settings
from django.views import View
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from utils.wsr.transcription_engine import TranscriptionEngineFactory


SETTINGS_FILE = os.path.join(dj_settings.BASE_DIR, "./config/config.ini")


def _ensure_ini():
    """Create a default settings.ini if it doesn't exist."""
    if not os.path.exists(SETTINGS_FILE):
        cfg = configparser.ConfigParser(interpolation=None)
        cfg["DEFAULT"] = {
            "selected_model_provider": "deepseek",
            "deepseek_api_key": "",
            "deepseek_base_url": "https://api.deepseek.com",
            "deepseek_model": "deepseek-chat",
            "glm_api_key": "",
            "glm_base_url": "https://open.bigmodel.cn/api/paas/v4",
            "glm_model": "glm-4",
            "openai_api_key": "",
            "openai_base_url": "https://api.chatanywhere.tech/v1",
            "openai_model": "gpt-4o",
            "qwen_api_key": "",
            "qwen_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "qwen_model": "qwen-plus",
            "local_api_key": "",
            "local_base_url": "http://localhost:1234/v1",
            "local_model": "",
            "openai_api_key": "",
            "openai_base_url": "https://api.chatanywhere.tech/v1",
            "qwen_api_key": "",
            "qwen_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "local_api_key": "",
            "local_base_url": "http://localhost:1234/v1",
            "split_use_proxy": "false",
            "translate_selected_model_provider": "deepseek",
            "translate_deepseek_api_key": "",
            "translate_deepseek_base_url": "https://api.deepseek.com",
            "translate_deepseek_model": "deepseek-chat",
            "translate_openai_api_key": "",
            "translate_openai_base_url": "https://api.chatanywhere.tech/v1",
            "translate_openai_model": "gpt-4o",
            "translate_glm_api_key": "",
            "translate_glm_base_url": "https://open.bigmodel.cn/api/paas/v4",
            "translate_glm_model": "glm-4",
            "translate_qwen_api_key": "",
            "translate_qwen_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "translate_qwen_model": "qwen-plus",
            "translate_local_api_key": "",
            "translate_local_base_url": "http://localhost:1234/v1",
            "translate_local_model": "",
            "translate_use_proxy": "false",
            "plain_translate": "false",
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
        }
        cfg["Transcription Engine"] = {
            "primary_engine": "faster_whisper",
            "fallback_engine": "",
            "transcription_mode": "local",
            "fwsr_model": "large-v3",
            "use_gpu": "false",
            "elevenlabs_api_key": "",
            "elevenlabs_model": "scribe_v1",
            "include_punctuation": "true",
            "alibaba_api_key": "",
            "alibaba_model": "paraformer-realtime-v2",
            "openai_api_key": "",
            "openai_base_url": "https://api.openai.com/v1",
        }
        cfg["Remote VidGo Service"] = {"host": "", "port": "8000", "use_ssl": "false"}
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

    # Auto-migrate: add default_translate_lang to Video watch
    if cfg.has_section("Video watch") and not cfg.has_option(
        "Video watch", "default_translate_lang"
    ):
        cfg.set("Video watch", "default_translate_lang", "zh")
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


def save_all_settings(settings_dict: dict):
    """Save all settings to config.ini."""
    cfg = configparser.ConfigParser(interpolation=None)

    for section_name, section_data in settings_dict.items():
        if section_name == "DEFAULT":
            cfg["DEFAULT"] = section_data
        else:
            cfg[section_name] = section_data

    with open(SETTINGS_FILE, "w") as fp:
        cfg.write(fp)


client = None


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

            # Update OpenAI client if API settings changed
            if "DEFAULT" in settings_dict:
                cfg = settings_dict["DEFAULT"]
                selected_provider = cfg.get("selected_model_provider", "deepseek")

                # Get provider-specific API key and base URL
                if selected_provider == "deepseek":
                    api_key = cfg.get("deepseek_api_key", "")
                    base_url = cfg.get("deepseek_base_url", "https://api.deepseek.com")
                elif selected_provider == "openai":
                    api_key = cfg.get("openai_api_key", "")
                    base_url = cfg.get("openai_base_url", "https://api.openai.com/v1")
                elif selected_provider == "glm":
                    api_key = cfg.get("glm_api_key", "")
                    base_url = cfg.get(
                        "glm_base_url", "https://open.bigmodel.cn/api/paas/v4"
                    )
                elif selected_provider == "qwen":
                    api_key = cfg.get("qwen_api_key", "")
                    base_url = cfg.get(
                        "qwen_base_url",
                        "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    )
                elif selected_provider == "local":
                    api_key = cfg.get("local_api_key", "")
                    base_url = cfg.get("local_base_url", "http://localhost:1234/v1")
                else:
                    api_key = cfg.get("deepseek_api_key", "")
                    base_url = cfg.get("deepseek_base_url", "https://api.deepseek.com")

                use_proxy_setting = (
                    cfg.get("split_use_proxy", "false").lower() == "true"
                )
                _init_client(
                    api_key,
                    base_url,
                    allow_empty_key=(selected_provider == "local"),
                    use_proxy=use_proxy_setting,
                )

            return JsonResponse(
                {"success": True, "message": "Settings updated successfully"}
            )

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
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
        self, cfg: dict, prefix: str
    ) -> tuple[str, str, str, str]:
        if prefix:
            selected_provider = cfg.get(f"{prefix}_selected_model_provider", "deepseek")
        else:
            selected_provider = cfg.get("selected_model_provider", "deepseek")

        p = prefix + "_" if prefix else ""

        if selected_provider == "deepseek":
            api_key = cfg.get(f"{p}deepseek_api_key", "")
            base_url = cfg.get(f"{p}deepseek_base_url", "https://api.deepseek.com")
            model = cfg.get(f"{p}deepseek_model", "deepseek-chat") or "deepseek-chat"
        elif selected_provider == "openai":
            api_key = cfg.get(f"{p}openai_api_key", "")
            base_url = cfg.get(f"{p}openai_base_url", "https://api.openai.com/v1")
            model = cfg.get(f"{p}openai_model", "gpt-4o") or "gpt-4o"
        elif selected_provider == "glm":
            api_key = cfg.get(f"{p}glm_api_key", "")
            base_url = cfg.get(
                f"{p}glm_base_url", "https://open.bigmodel.cn/api/paas/v4"
            )
            model = cfg.get(f"{p}glm_model", "glm-4-plus") or "glm-4-plus"
        elif selected_provider == "qwen":
            api_key = cfg.get(f"{p}qwen_api_key", "")
            base_url = cfg.get(
                f"{p}qwen_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            model = cfg.get(f"{p}qwen_model", "qwen-plus") or "qwen-plus"
        elif selected_provider == "local":
            api_key = cfg.get(f"{p}local_api_key", "")
            base_url = cfg.get(f"{p}local_base_url", "http://localhost:1234/v1")
            model = cfg.get(f"{p}custom_model_name", "") or cfg.get(
                f"{p}local_model", ""
            )
        else:
            api_key = cfg.get(f"{p}deepseek_api_key", "")
            base_url = cfg.get(f"{p}deepseek_base_url", "https://api.deepseek.com")
            model = "deepseek-chat"
            selected_provider = "deepseek"

        return selected_provider, api_key, base_url, model

    def get(self, request: HttpRequest, *args, **kwargs):
        llm_type = request.GET.get("type", "split")
        prefix = "translate" if llm_type == "translate" else ""
        proxy_key = (
            "translate_use_proxy" if llm_type == "translate" else "split_use_proxy"
        )

        try:
            settings_data = load_all_settings()
            cfg = settings_data.get("DEFAULT", {})

            use_proxy = cfg.get(proxy_key, "false").lower() == "true"
            original_proxy = {}
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

            # local 模式允许空 api_key
            if not base_url:
                result = {
                    "success": False,
                    "error": f"Base URL not configured for provider: {selected_provider}",
                }
                for key, value in original_proxy.items():
                    os.environ[key] = value
                return JsonResponse(result, status=400)
            if not api_key and selected_provider != "local":
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
                allow_empty_key=(selected_provider == "local"),
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
                "primary_engine", "faster_whisper"
            )
            current_model = settings_data.get("Transcription Engine", {}).get(
                "fwsr_model", "large-v3"
            )

            models_dir = os.path.join(dj_settings.BASE_DIR, "models")

            faster_whisper_models = [
                {
                    "name": "tiny",
                    "size": "~39 MB",
                    "languages": "multilingual",
                    "filename": "models--Systran--faster-whisper-tiny",
                },
                {
                    "name": "tiny.en",
                    "size": "~39 MB",
                    "languages": "English only",
                    "filename": "models--Systran--faster-whisper-tiny.en",
                },
                {
                    "name": "base",
                    "size": "~74 MB",
                    "languages": "multilingual",
                    "filename": "models--Systran--faster-whisper-base",
                },
                {
                    "name": "base.en",
                    "size": "~74 MB",
                    "languages": "English only",
                    "filename": "models--Systran--faster-whisper-base.en",
                },
                {
                    "name": "small",
                    "size": "~244 MB",
                    "languages": "multilingual",
                    "filename": "models--Systran--faster-whisper-small",
                },
                {
                    "name": "small.en",
                    "size": "~244 MB",
                    "languages": "English only",
                    "filename": "models--Systran--faster-whisper-small.en",
                },
                {
                    "name": "medium",
                    "size": "~769 MB",
                    "languages": "multilingual",
                    "filename": "models--Systran--faster-whisper-medium",
                },
                {
                    "name": "medium.en",
                    "size": "~769 MB",
                    "languages": "English only",
                    "filename": "models--Systran--faster-whisper-medium.en",
                },
                {
                    "name": "large-v1",
                    "size": "~1.5 GB",
                    "languages": "multilingual",
                    "filename": "models--Systran--faster-whisper-large-v1",
                },
                {
                    "name": "large-v2",
                    "size": "~1.5 GB",
                    "languages": "multilingual",
                    "filename": "models--Systran--faster-whisper-large-v2",
                },
                {
                    "name": "large-v3",
                    "size": "~1.5 GB",
                    "languages": "multilingual",
                    "filename": "models--Systran--faster-whisper-large-v3",
                },
                {
                    "name": "large-v3-turbo",
                    "size": "~1.6 GB",
                    "languages": "multilingual",
                    "filename": "models--Systran--faster-whisper-large-v3-turbo",
                },
                {
                    "name": "distil-large-v2",
                    "size": "~1.5 GB",
                    "languages": "multilingual",
                    "filename": "models--Systran--distil-whisper-large-v2",
                },
                {
                    "name": "distil-large-v3",
                    "size": "~1.5 GB",
                    "languages": "multilingual",
                    "filename": "models--Systran--distil-whisper-large-v3",
                },
            ]

            whisper_cpp_models = [
                {
                    "name": "tiny",
                    "size": "~75 MB",
                    "languages": "multilingual",
                    "filename": "ggml-tiny.bin",
                },
                {
                    "name": "base",
                    "size": "~142 MB",
                    "languages": "multilingual",
                    "filename": "ggml-base.bin",
                },
                {
                    "name": "small",
                    "size": "~466 MB",
                    "languages": "multilingual",
                    "filename": "ggml-small.bin",
                },
                {
                    "name": "medium",
                    "size": "~1.5 GB",
                    "languages": "multilingual",
                    "filename": "ggml-medium.bin",
                },
                {
                    "name": "medium-q5",
                    "size": "~600 MB",
                    "languages": "multilingual (quantized)",
                    "filename": "ggml-medium-q5_0.bin",
                },
                {
                    "name": "large-v2",
                    "size": "~3.1 GB",
                    "languages": "multilingual",
                    "filename": "ggml-large-v2.bin",
                },
                {
                    "name": "large-v3",
                    "size": "~3.1 GB",
                    "languages": "multilingual",
                    "filename": "ggml-large-v3.bin",
                },
                {
                    "name": "large-v3-q5",
                    "size": "~1.3 GB",
                    "languages": "multilingual (quantized)",
                    "filename": "ggml-large-v3-q5_0.bin",
                },
                {
                    "name": "large-v3-turbo",
                    "size": "~1.6 GB",
                    "languages": "multilingual",
                    "filename": "ggml-large-v3-turbo.bin",
                },
            ]

            if current_engine == "faster_whisper":
                available_models = faster_whisper_models
                engine_name = "faster_whisper"
            else:
                available_models = whisper_cpp_models
                engine_name = "whisper_cpp"

            for model in available_models:
                model_path = os.path.join(models_dir, model["filename"])
                if engine_name == "faster_whisper":
                    model["downloaded"] = os.path.exists(model_path) and os.path.isfile(
                        os.path.join(model_path, "model.bin")
                    )
                else:
                    model["downloaded"] = os.path.exists(model_path)
                model["downloading"] = model["name"] in download_progress
                model["engine"] = engine_name
                if model["downloading"]:
                    model["progress"] = download_progress[model["name"]]

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
