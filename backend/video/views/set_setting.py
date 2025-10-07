import os
import configparser
from django.conf import settings as dj_settings
from django.views import View
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from openai import OpenAI
import json
from utils.wsr.transcription_engine import TranscriptionEngineFactory 


SETTINGS_FILE = os.path.join(dj_settings.BASE_DIR, './config/config.ini')


def _ensure_ini():
    """Create a default settings.ini if it doesn't exist."""
    if not os.path.exists(SETTINGS_FILE):
        cfg = configparser.ConfigParser(interpolation=None)
        cfg['DEFAULT'] = {
            'selected_model_provider': 'deepseek',
            'enable_thinking': 'true',
            'use_proxy': 'false',
            'deepseek_api_key': 'sk-17047f89de904759a241f4086bd5a9bf',
            'deepseek_base_url': 'https://api.deepseek.com',
            'glm_api_key': 'sk-17047f89de904759a241f4086bd5a9bf',
            'glm_base_url': 'https://api.deepseek.com',
            'openai_api_key': 'sk-qTbd1AR4oMuP71ziRngmk3i0djrWVfLtuisvYKCH5B9jLz9g',
            'openai_base_url': 'https://api.chatanywhere.tech/v1',
            'qwen_api_key': 'sk-944471ea4aef486ca2a82b2adf26c0cc',
            'qwen_base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        }
        cfg['Video watch'] = {
            'raw_language': 'zh'
        }
        cfg['Subtitle settings'] = {
            'font_family': '宋体',
            'preview_text': '这是字幕预设文本',
            'font_color': '#ea9749',
            'font_size': '18',
            'font_weight': '400',
            'background_color': '#000000',
            'border_radius': '4',
            'text_shadow': 'false',
            'text_stroke': 'false',
            'text_stroke_color': '#000000',
            'text_stroke_width': '2',
            'background_style': 'semi-transparent',
            'bottom_distance': '80'
        }
        cfg['Foreign Subtitle settings'] = {
            'foreign_font_family': 'Arial',
            'foreign_preview_text': 'This is foreign subtitle preview',
            'foreign_font_color': '#ffffff',
            'foreign_font_size': '16',
            'foreign_font_weight': '400',
            'foreign_background_color': '#000000',
            'foreign_border_radius': '4',
            'foreign_text_shadow': 'false',
            'foreign_text_stroke': 'false',
            'foreign_text_stroke_color': '#000000',
            'foreign_text_stroke_width': '2',
            'foreign_background_style': 'semi-transparent',
            'foreign_bottom_distance': '120'
        }
        cfg['Media Credentials'] = {
            'bilibili_sessdata': ''
        }
        cfg['Transcription Engine'] = {
            'primary_engine': 'whisper_cpp',
            'fallback_engine': '',
            'transcription_mode': 'local',
            'fwsr_model': 'large-v3',
            'use_gpu': 'false',
            'elevenlabs_api_key': '',
            'elevenlabs_model': 'scribe_v1',
            'include_punctuation': 'true',
            'alibaba_api_key': '',
            'alibaba_model': 'paraformer-realtime-v2',
            'openai_api_key': '',
            'openai_base_url': 'https://api.openai.com/v1'
        }
        cfg['Remote VidGo Service'] = {
            'host': '',
            'port': '8000',
            'use_ssl': 'false'
        }
        cfg['TTS settings'] = {
            'dashscope_api_key': '',
            'default_voice': 'longxiaochun_v2',
            'default_model': 'cosyvoice-v2',
            'request_timeout': '30',
            'max_retries': '5',
            'enable_checkpointing': 'true',
            'checkpoint_interval': '10',
            'time_stretch_algorithm': 'librosa',
            'time_stretch_quality': 'high',
            'max_compression_ratio': '2.0'
        }
        cfg['OSS Service'] = {
            'oss_access_key_id': '',
            'oss_access_key_secret': '',
            'oss_endpoint': 'oss-cn-beijing.aliyuncs.com',
            'oss_bucket': 'vidgo-test',
            'oss_region': 'cn-beijing'
        }
        with open(SETTINGS_FILE, 'w') as fp:
            cfg.write(fp)


def load_all_settings():
    """Return all settings from config.ini as a dictionary."""
    _ensure_ini()
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(SETTINGS_FILE)

    # Auto-add missing sections to existing config files
    modified = False

    # Check for TTS settings section
    if not cfg.has_section('TTS settings'):
        cfg['TTS settings'] = {
            'dashscope_api_key': '',
            'default_voice': 'longxiaochun_v2',
            'default_model': 'cosyvoice-v2',
            'request_timeout': '30',
            'max_retries': '5',
            'enable_checkpointing': 'true',
            'checkpoint_interval': '10',
            'time_stretch_algorithm': 'librosa',
            'time_stretch_quality': 'high',
            'max_compression_ratio': '2.0'
        }
        modified = True

    # Check for OSS settings section
    if not cfg.has_section('OSS Service'):
        cfg['OSS Service'] = {
            'oss_access_key_id': '',
            'oss_access_key_secret': '',
            'oss_endpoint': 'oss-cn-beijing.aliyuncs.com',
            'oss_bucket': 'vidgo-test',
            'oss_region': 'cn-beijing'
        }
        modified = True

    # Save config if sections were added
    if modified:
        with open(SETTINGS_FILE, 'w') as fp:
            cfg.write(fp)

    result = {}
    for section_name in cfg.sections():
        result[section_name] = dict(cfg[section_name])

    # Add DEFAULT section
    result['DEFAULT'] = dict(cfg['DEFAULT'])

    return result


def save_all_settings(settings_dict: dict):
    """Save all settings to config.ini."""
    cfg = configparser.ConfigParser(interpolation=None)
    
    for section_name, section_data in settings_dict.items():
        if section_name == 'DEFAULT':
            cfg['DEFAULT'] = section_data
        else:
            cfg[section_name] = section_data
    
    with open(SETTINGS_FILE, 'w') as fp:
        cfg.write(fp)


client = None


def _init_client(api_key: str, base_url: str):
    """(Re)initialise global OpenAI client instance."""
    global client
    if api_key and base_url:
        client = OpenAI(api_key=api_key, base_url=base_url)
    else:
        client = None


@method_decorator(csrf_exempt, name='dispatch')
class ConfigAPIView(View):
    """API endpoints for getting and setting all configuration."""
    
    http_method_names = ['get', 'post']
    
    def get(self, request: HttpRequest, *args, **kwargs):
        """Get all configuration settings."""
        try:
            settings_data = load_all_settings()
            return JsonResponse({'success': True, 'data': settings_data})
        except Exception as exc:
            return JsonResponse({'error': str(exc)}, status=500)
    
    def post(self, request: HttpRequest, *args, **kwargs):
        """Update all configuration settings."""
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                return JsonResponse({'error': 'Content-Type must be application/json'}, status=400)
            
            settings_dict = data.get('settings', {})
            if not settings_dict:
                return JsonResponse({'error': 'Settings data is required'}, status=400)
            
            save_all_settings(settings_dict)
            
            # Update OpenAI client if API settings changed
            if 'DEFAULT' in settings_dict:
                cfg = settings_dict['DEFAULT']
                selected_provider = cfg.get('selected_model_provider', 'deepseek')
                
                # Get provider-specific API key and base URL
                if selected_provider == 'deepseek':
                    api_key = cfg.get('deepseek_api_key', '')
                    base_url = cfg.get('deepseek_base_url', 'https://api.deepseek.com')
                elif selected_provider == 'openai':
                    api_key = cfg.get('openai_api_key', '')
                    base_url = cfg.get('openai_base_url', 'https://api.openai.com/v1')
                elif selected_provider == 'glm':
                    api_key = cfg.get('glm_api_key', '')
                    base_url = cfg.get('glm_base_url', 'https://open.bigmodel.cn/api/paas/v4')
                elif selected_provider == 'qwen':
                    api_key = cfg.get('qwen_api_key', '')
                    base_url = cfg.get('qwen_base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
                else:
                    api_key = cfg.get('deepseek_api_key', '')
                    base_url = cfg.get('deepseek_base_url', 'https://api.deepseek.com')
                
                _init_client(api_key, base_url)
            
            return JsonResponse({'success': True, 'message': 'Settings updated successfully'})
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as exc:
            return JsonResponse({'error': str(exc)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class TranscriptionEnginesAPIView(View):
    """API endpoint for getting available transcription engines."""
    
    http_method_names = ['get']
    
    def get(self, request: HttpRequest, *args, **kwargs):
        """Get available transcription engines and their info."""
        try:
            # Load current settings to check engine availability
            settings_data = load_all_settings()
            
            # Get engine info
            engine_info = TranscriptionEngineFactory.get_engine_info()
            
            # Get available engines based on current config
            available_engines = TranscriptionEngineFactory.get_available_engines(settings_data)
            
            # Combine info with availability status
            engines_with_status = {}
            for engine_type, info in engine_info.items():
                engines_with_status[engine_type] = {
                    **info,
                    'available': engine_type in available_engines
                }
            
            return JsonResponse({
                'success': True, 
                'data': {
                    'engines': engines_with_status,
                    'available_engines': available_engines
                }
            })
            
        except Exception as exc:
            return JsonResponse({'error': str(exc)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class LLMTestAPIView(View):
    """API endpoint to test LLM connection by sending a simple prompt."""
    http_method_names = ['get']

    def get(self, request: HttpRequest, *args, **kwargs):
        try:
            # Load current settings and initialize client
            settings_data = load_all_settings()
            cfg = settings_data.get('DEFAULT', {})
            
            # Get selected model provider
            selected_provider = cfg.get('selected_model_provider', 'deepseek')
            
            # Get provider-specific API key and base URL
            if selected_provider == 'deepseek':
                api_key = cfg.get('deepseek_api_key', '')
                base_url = cfg.get('deepseek_base_url', 'https://api.deepseek.com')
                model = 'deepseek-chat'
            elif selected_provider == 'openai':
                api_key = cfg.get('openai_api_key', '')
                base_url = cfg.get('openai_base_url', 'https://api.openai.com/v1')
                model = 'gpt-4o'
            elif selected_provider == 'glm':
                api_key = cfg.get('glm_api_key', '')
                base_url = cfg.get('glm_base_url', 'https://open.bigmodel.cn/api/paas/v4')
                model = 'glm-4-plus'
            elif selected_provider == 'qwen':
                api_key = cfg.get('qwen_api_key', '')
                base_url = cfg.get('qwen_base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
                model = 'qwen-plus'
            else:
                # Default to deepseek
                api_key = cfg.get('deepseek_api_key', '')
                base_url = cfg.get('deepseek_base_url', 'https://api.deepseek.com')
                model = 'deepseek-chat'
            
            if not api_key or not base_url:
                return JsonResponse({'success': False, 'error': f'API key or base URL not configured for provider: {selected_provider}'}, status=400)
            
            _init_client(api_key, base_url)
            
            # Send test prompt
            prompt = 'Hello, please respond with "Connection successful!"'
            print(f'Sending test prompt to model {model} at {base_url}')
            response = client.chat.completions.create(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                timeout=60
            )
            content = response.choices[0].message.content
            return JsonResponse({'success': True, 'response': content})
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# Global dictionary to track download progress
download_progress = {}

@method_decorator(csrf_exempt, name='dispatch')
class WhisperModelAPIView(View):
    """API endpoints for Whisper model management."""
    
    http_method_names = ['get', 'post']
    
    def get(self, request: HttpRequest, *args, **kwargs):
        """Get available models and download status."""
        try:
            # Get current engine to determine which models to show
            settings_data = load_all_settings()
            current_engine = settings_data.get('Transcription Engine', {}).get('primary_engine', 'whisper_cpp')
            current_model = settings_data.get('Transcription Engine', {}).get('fwsr_model', 'large-v3')

            models_dir = os.path.join(dj_settings.BASE_DIR, 'models')

            # Define models for whisper.cpp (GGML format)
            whisper_cpp_models = [
                {'name': 'tiny', 'size': '~75 MB', 'languages': 'multilingual', 'filename': 'ggml-tiny.bin'},
                {'name': 'base', 'size': '~142 MB', 'languages': 'multilingual', 'filename': 'ggml-base.bin'},
                {'name': 'small', 'size': '~466 MB', 'languages': 'multilingual', 'filename': 'ggml-small.bin'},
                {'name': 'medium', 'size': '~1.5 GB', 'languages': 'multilingual', 'filename': 'ggml-medium.bin'},
                {'name': 'medium-q5', 'size': '~600 MB', 'languages': 'multilingual (quantized)', 'filename': 'ggml-medium-q5_0.bin'},
                {'name': 'large-v2', 'size': '~3.1 GB', 'languages': 'multilingual', 'filename': 'ggml-large-v2.bin'},
                {'name': 'large-v3', 'size': '~3.1 GB', 'languages': 'multilingual', 'filename': 'ggml-large-v3.bin'},
                {'name': 'large-v3-q5', 'size': '~1.3 GB', 'languages': 'multilingual (quantized)', 'filename': 'ggml-large-v3-q5_0.bin'},
                {'name': 'large-v3-turbo', 'size': '~1.6 GB', 'languages': 'multilingual', 'filename': 'ggml-large-v3-turbo.bin'},
            ]

            # whisper.cpp only
            available_models = whisper_cpp_models
            # Check for .bin files
            for model in available_models:
                model_path = os.path.join(models_dir, model['filename'])
                model['downloaded'] = os.path.exists(model_path)
                model['downloading'] = model['name'] in download_progress
                model['engine'] = 'whisper_cpp'
                if model['downloading']:
                    model['progress'] = download_progress[model['name']]

            return JsonResponse({
                'success': True,
                'data': {
                    'models': available_models,
                    'current_model': current_model,
                    'current_engine': current_engine
                }
            })

        except Exception as exc:
            return JsonResponse({'error': str(exc)}, status=500)
    
    def post(self, request: HttpRequest, *args, **kwargs):
        """Download a Whisper model."""
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                return JsonResponse({'error': 'Content-Type must be application/json'}, status=400)

            model_name = data.get('model_name')

            if not model_name:
                return JsonResponse({'error': 'model_name is required'}, status=400)

            # Check if already downloading
            if model_name in download_progress:
                return JsonResponse({'error': 'Model is already being downloaded'}, status=409)

            # Start download in background thread
            import threading
            import subprocess

            def download_model():
                try:
                    import time

                    download_progress[model_name] = 0
                    models_dir = os.path.join(dj_settings.BASE_DIR, 'models')
                    os.makedirs(models_dir, exist_ok=True)

                    # Use bash script to download whisper.cpp GGML models
                    script_path = os.path.join(dj_settings.BASE_DIR, 'scripts', 'download_whisper_models.sh')

                    print(f"[whisper.cpp] Starting download of {model_name} using {script_path}")

                    # Set WHISPER_MODEL_DIR environment variable
                    env = os.environ.copy()
                    env['WHISPER_MODEL_DIR'] = models_dir

                    # Execute bash script with model name as argument
                    result = subprocess.run(
                        ['bash', script_path, model_name],
                        env=env,
                        capture_output=True,
                        text=True,
                        check=True
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
                    print(f"[whisper.cpp] Model download script failed for {model_name}: {e.stderr}")
                    if model_name in download_progress:
                        download_progress[model_name] = -1  # Error state
                except Exception as e:
                    print(f"Model download failed for {model_name}: {e}")
                    if model_name in download_progress:
                        download_progress[model_name] = -1  # Error state

            thread = threading.Thread(target=download_model)
            thread.daemon = True
            thread.start()

            return JsonResponse({'success': True, 'message': f'Started downloading {model_name}'})
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as exc:
            return JsonResponse({'error': str(exc)}, status=500)

# Add a new API endpoint for getting download progress
class WhisperModelProgressAPIView(View):
    """API endpoint specifically for getting model download progress."""
    
    http_method_names = ['get']
    
    def get(self, request: HttpRequest, *args, **kwargs):
        """Get current download progress for all models."""
        try:
            return JsonResponse({
                'success': True,
                'progress': dict(download_progress)
            })
        except Exception as exc:
            return JsonResponse({'error': str(exc)}, status=500)

# Add a new API endpoint for checking model folder size
class WhisperModelSizeAPIView(View):
    """API endpoint for checking model folder size."""
    
    http_method_names = ['post']
    
    def post(self, request: HttpRequest, *args, **kwargs):
        """Get the actual size of a model folder."""
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                return JsonResponse({'error': 'Content-Type must be application/json'}, status=400)
            
            model_name = data.get('model_name')
            if not model_name:
                return JsonResponse({'error': 'model_name is required'}, status=400)
            
            # Calculate folder size
            models_dir = os.path.join(dj_settings.BASE_DIR, 'models')
            model_path = models_dir
            
            if not os.path.exists(model_path):
                return JsonResponse({
                    'success': True,
                    'size': 0,
                    'size_mb': 0,
                    'size_human': '0 B',
                    'exists': False
                })
            
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
                for unit in ['B', 'KB', 'MB', 'GB']:
                    if bytes_size < 1024.0:
                        return f"{bytes_size:.1f} {unit}"
                    bytes_size /= 1024.0
                return f"{bytes_size:.1f} TB"
            
            return JsonResponse({
                'success': True,
                'size': total_size,
                'size_mb': total_size / (1024 * 1024),
                'size_human': format_size(total_size),
                'file_count': file_count,
                'exists': True
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as exc:
            return JsonResponse({'error': str(exc)}, status=500)
