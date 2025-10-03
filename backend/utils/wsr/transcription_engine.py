# utils/wsr/transcription_engine.py
"""
Unified transcription engine interface for VidGo
Supports multiple transcription engines with standardized interface
"""

from typing import Callable, Optional, Dict, Any
from abc import ABC, abstractmethod
import os
import requests
import time
import tempfile
import uuid


class TranscriptionEngine(ABC):
    """Abstract base class for all transcription engines"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    @abstractmethod
    def transcribe_audio(self, audio_file_path: str, progress_cb: Callable[[str], None], language: Optional[str] = None) -> str:
        """
        Transcribe audio file to SRT format
        
        Args:
            audio_file_path: Path to audio file
            progress_cb: Progress callback function
            language: Optional language hint for transcription
            
        Returns:
            SRT format string with word-level timestamps
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this engine is available and properly configured"""
        pass
    
    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return engine name"""
        pass


class FasterWhisperEngine(TranscriptionEngine):
    """Faster-Whisper local transcription engine"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
    def transcribe_audio(self, audio_file_path: str, progress_cb: Callable[[str], None], language: Optional[str] = None) -> str:
        try:
            from .fast_wsr import transcribe_audio
            return transcribe_audio(audio_file_path, progress_cb, language)
        except Exception as e:
            raise Exception(f"Faster-Whisper transcription failed: {str(e)}")
    
    def is_available(self) -> bool:
        try:
            from .fast_wsr import get_model
            # Try to load model to verify availability
            model = get_model()
            return model is not None
        except Exception:
            return False
    
    @property
    def engine_name(self) -> str:
        return "faster_whisper"


class ElevenLabsEngine(TranscriptionEngine):
    """ElevenLabs Speech-to-Text API engine"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Get ElevenLabs settings from config
        transcription_settings = config.get('Transcription Engine', {})
        self.api_key = transcription_settings.get('elevenlabs_api_key', '')
        
    def transcribe_audio(self, audio_file_path: str, progress_cb: Callable[[str], None], language: Optional[str] = None) -> str:
        try:
            progress_cb("Running")
            from .elevenlab_wsr import elevenlabs_stt_to_word_srt
            
            if not self.api_key:
                raise Exception("ElevenLabs API key not configured")
            
            transcription_settings = self.config.get('Transcription Engine', {})
            srt_content = elevenlabs_stt_to_word_srt(
                audio_path=audio_file_path,
                api_key=self.api_key,
                model_id=transcription_settings.get('elevenlabs_model', 'scribe_v1'),
                include_punctuation=transcription_settings.get('include_punctuation', 'false').lower() == 'true'
            )
            
            progress_cb("Completed")
            return srt_content
            
        except Exception as e:
            progress_cb("Failed")
            raise Exception(f"ElevenLabs transcription failed: {str(e)}")
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    @property
    def engine_name(self) -> str:
        return "elevenlabs"


class AlibabaEngine(TranscriptionEngine):
    """Alibaba DashScope Paraformer API engine"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Get Alibaba settings from config
        transcription_settings = config.get('Transcription Engine', {})
        self.api_key = transcription_settings.get('alibaba_api_key', '')
        
    def transcribe_audio(self, audio_file_path: str, progress_cb: Callable[[str], None], language: Optional[str] = None) -> str:
        try:
            progress_cb("Running")
            
            if not self.api_key:
                raise Exception("Alibaba API key not configured")
            
            # Import and configure DashScope
            import dashscope
            from dashscope.audio.asr import Recognition
            from http import HTTPStatus
            
            dashscope.api_key = self.api_key
            
            # Create recognition instance
            transcription_settings = self.config.get('Transcription Engine', {})
            recognition = Recognition(
                model=transcription_settings.get('alibaba_model', 'paraformer-realtime-v2'),
                format='mp3',
                sample_rate=16000,
                language_hints=['zh', 'en'],
                enable_words=True,
                enable_punctuation=True,
                callback=None,
            )
            
            # Perform recognition
            result = recognition.call(audio_file_path)
            
            if result.status_code == HTTPStatus.OK:
                # Convert to SRT format
                from .ali_wsr import json_to_word_srt
                srt_content = json_to_word_srt(result.get_sentence())
                progress_cb("Completed")
                return srt_content
            else:
                raise Exception(f"Alibaba recognition failed: {result.message}")
                
        except Exception as e:
            progress_cb("Failed")
            raise Exception(f"Alibaba transcription failed: {str(e)}")
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    @property
    def engine_name(self) -> str:
        return "alibaba"


class OpenAIWhisperEngine(TranscriptionEngine):
    """OpenAI Whisper API engine"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Get OpenAI settings from config
        transcription_settings = config.get('Transcription Engine', {})
        self.api_key = transcription_settings.get('openai_api_key', '')
        self.base_url = transcription_settings.get('openai_base_url', 'https://api.openai.com/v1')
        
    def transcribe_audio(self, audio_file_path: str, progress_cb: Callable[[str], None], language: Optional[str] = None) -> str:
        try:
            progress_cb("Running")
            
            if not self.api_key:
                raise Exception("OpenAI API key not configured")
            
            from openai import OpenAI
            
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            
            with open(audio_file_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
            
            # Convert to SRT format
            srt_content = self._convert_to_srt(transcription.words)
            progress_cb("Completed")
            return srt_content
            
        except Exception as e:
            progress_cb("Failed")
            raise Exception(f"OpenAI Whisper transcription failed: {str(e)}")
    
    def _convert_to_srt(self, words) -> str:
        """Convert OpenAI word timestamps to SRT format"""
        from utils.video.time_convert import seconds_to_srt_time
        
        srt_content = ""
        idx = 1
        
        for word in words:
            if word.word.strip():
                srt_content += f"{idx}\n{seconds_to_srt_time(word.start)} --> " \
                            f"{seconds_to_srt_time(word.end)}\n{word.word.strip()}\n\n"
                idx += 1
        print("srt_content:",srt_content)
        return srt_content
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    @property
    def engine_name(self) -> str:
        return "openai_whisper"


class WhisperCppEngine(TranscriptionEngine):
    """Whisper.cpp local transcription engine (CPU/CUDA)"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

    def transcribe_audio(self, audio_file_path: str, progress_cb: Callable[[str], None], language: Optional[str] = None) -> str:
        try:
            from .whisper_cpp_wsr import transcribe_audio
            return transcribe_audio(audio_file_path, progress_cb, language)
        except Exception as e:
            raise Exception(f"Whisper.cpp transcription failed: {str(e)}")

    def is_available(self) -> bool:
        try:
            from .whisper_cpp_wsr import get_whisper_cpp_paths
            from pathlib import Path
            paths = get_whisper_cpp_paths()
            # Check if binary exists
            return Path(paths["binary"]).exists()
        except Exception:
            return False

    @property
    def engine_name(self) -> str:
        return "whisper_cpp"


class RemoteVidGoEngine(TranscriptionEngine):
    """Remote VidGo transcription service engine"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        remote_config = config.get('Remote VidGo Service', {})
        self.host = remote_config.get('host', '').strip()
        self.port = remote_config.get('port', '8000')
        self.use_ssl = remote_config.get('use_ssl', 'false').lower() == 'true'
        
        # Build base URL
        if self.host:
            protocol = 'https' if self.use_ssl else 'http'
            if self.use_ssl and self.host and '.' in self.host and self.port == '443':
                # SSL with domain using standard port
                self.base_url = f"{protocol}://{self.host}"
            elif self.use_ssl and self.host and '.' in self.host and self.port != '443':
                # SSL with domain using custom port
                self.base_url = f"{protocol}://{self.host}:{self.port}"
            else:
                # Non-SSL or IP address
                self.base_url = f"{protocol}://{self.host}:{self.port}"
        else:
            self.base_url = None
    
    def transcribe_audio(self, audio_file_path: str, progress_cb: Callable[[str], None], language: Optional[str] = None) -> str:
        if not self.is_available():
            raise Exception("Remote VidGo service is not properly configured")
        
        try:
            progress_cb("Running")
            
            # Submit audio file for transcription
            submit_url = f"{self.base_url}/api/external_transcription/submit"
            
            with open(audio_file_path, 'rb') as audio_file:
                files = {'audio_file': audio_file}
                response = requests.post(submit_url, files=files, timeout=30)
            
            if response.status_code != 200:
                raise Exception(f"Failed to submit transcription task: {response.text}")
            
            task_data = response.json()
            task_id = task_data['task_id']
            
            # Poll for completion
            status_url = f"{self.base_url}/api/external_transcription/{task_id}/status"
            max_wait_time = 1800  # 30 minutes
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                status_response = requests.get(status_url, timeout=30)
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    status = status_data['status']
                    
                    if status == 'completed':
                        # Download result
                        result_url = f"{self.base_url}/api/external_transcription/{task_id}/result"
                        result_response = requests.get(result_url, timeout=30)
                        
                        if result_response.status_code == 200:
                            progress_cb("Completed")
                            
                            # Clean up remote task
                            try:
                                delete_url = f"{self.base_url}/api/external_transcription/{task_id}/delete"
                                requests.delete(delete_url, timeout=10)
                            except:
                                pass  # Ignore cleanup errors
                            
                            return result_response.text
                        else:
                            raise Exception(f"Failed to download transcription result: {result_response.text}")
                    
                    elif status == 'failed':
                        error_msg = status_data.get('error_message', 'Unknown error')
                        raise Exception(f"Remote transcription failed: {error_msg}")
                    
                    elif status in ['queued', 'running']:
                        # Continue waiting
                        time.sleep(5)
                        continue
                    else:
                        raise Exception(f"Unknown status from remote service: {status}")
                else:
                    raise Exception(f"Failed to check transcription status: {status_response.text}")
            
            # Timeout
            raise Exception("Remote transcription timed out after 30 minutes")
            
        except requests.RequestException as e:
            progress_cb("Failed")
            raise Exception(f"Network error connecting to remote VidGo service: {str(e)}")
        except Exception as e:
            progress_cb("Failed")
            raise
    
    def is_available(self) -> bool:
        """Check if remote VidGo service is available and properly configured"""
        if not self.host or not self.base_url:
            return False
        
        try:
            # Test connectivity with a simple request to the list endpoint
            list_url = f"{self.base_url}/api/external_transcription/list"
            response = requests.get(list_url, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    @property
    def engine_name(self) -> str:
        return "remote_vidgo"


class TranscriptionEngineFactory:
    """Factory class for creating transcription engines"""
    
    _engines = {
        'faster_whisper': FasterWhisperEngine,
        'whisper_cpp': WhisperCppEngine,
        'elevenlabs': ElevenLabsEngine,
        'alibaba': AlibabaEngine,
        'openai_whisper': OpenAIWhisperEngine,
        'remote_vidgo': RemoteVidGoEngine,
    }
    
    @classmethod
    def create_engine(cls, engine_type: str, config: Dict[str, Any]) -> TranscriptionEngine:
        """Create a transcription engine instance"""
        if engine_type not in cls._engines:
            available_engines = ', '.join(cls._engines.keys())
            raise ValueError(f"Unknown engine type '{engine_type}'. Available: {available_engines}")
        
        engine_class = cls._engines[engine_type]
        return engine_class(config)
    
    @classmethod
    def get_available_engines(cls, config: Dict[str, Any]) -> list:
        """Get list of available and properly configured engines"""
        available = []
        for engine_type in cls._engines:
            try:
                engine = cls.create_engine(engine_type, config)
                if engine.is_available():
                    available.append(engine_type)
            except Exception:
                continue
        return available
    
    @classmethod
    def get_engine_info(cls) -> Dict[str, Dict[str, Any]]:
        """Get information about all supported engines"""
        return {
            'faster_whisper': {
                'name': 'Faster-Whisper (Local)',
                'type': 'local',
                'languages': 'Multi-language',
                'requires_api_key': False,
                'speed': 'Fast',
                'quality': 'High'
            },
            'whisper_cpp': {
                'name': 'Whisper.cpp (Official C++ Implementation)',
                'description': 'CPU/CUDA optimized, zero Python dependencies, smallest Docker image',
                'type': 'local',
                'languages': 'Multi-language',
                'requires_api_key': False,
                'speed': 'Very Fast (CPU), Ultra Fast (CUDA)',
                'quality': 'High'
            },
            'elevenlabs': {
                'name': 'ElevenLabs Speech-to-Text',
                'type': 'api',
                'languages': 'Multi-language',
                'requires_api_key': True,
                'speed': 'Fast',
                'quality': 'High'
            },
            'alibaba': {
                'name': 'Alibaba DashScope',
                'type': 'api',
                'languages': 'Chinese/English',
                'requires_api_key': True,
                'speed': 'Fast',
                'quality': 'High'
            },
            'openai_whisper': {
                'name': 'OpenAI Whisper API',
                'type': 'api',
                'languages': 'Multi-language',
                'requires_api_key': True,
                'speed': 'Medium',
                'quality': 'High'
            },
            'remote_vidgo': {
                'name': 'Remote VidGo Subtitle Service',
                'description': 'Users can deploy VidGo instances on high-performance hosts and call backend subtitle recognition services via IP/domain links.',
                'type': 'remote',
                'languages': 'Multi-language',
                'requires_api_key': False,
                'requires_config': True,
                'speed': 'Fast',
                'quality': 'High'
            }
        }


def load_transcription_settings():
    """Load transcription engine settings using existing load_all_settings function"""
    try:
        from video.views.set_setting import load_all_settings
        return load_all_settings()
    except Exception as e:
        print(f"Error loading transcription settings: {e}")
        return {}


def transcribe_with_engine(
    engine_type: str, 
    audio_file_path: str, 
    progress_cb: Callable[[str], None],
    fallback_engine: Optional[str] = None,
    language: Optional[str] = None
) -> str:
    """
    Transcribe audio using specified engine with optional fallback
    
    Args:
        engine_type: Primary engine to use
        audio_file_path: Path to audio file
        progress_cb: Progress callback
        fallback_engine: Fallback engine if primary fails
        
    Returns:
        SRT content string
    """
    # Load configuration from config.ini
    config = load_transcription_settings()
    
    try:
        # Try primary engine
        engine = TranscriptionEngineFactory.create_engine(engine_type, config)
        if not engine.is_available():
            raise Exception(f"Engine '{engine_type}' is not available or not properly configured")
        
        print(f"Using transcription engine: {engine.engine_name}")
        return engine.transcribe_audio(audio_file_path, progress_cb, language)
        
    except Exception as primary_error:
        print(f"Primary engine '{engine_type}' failed: {primary_error}")
        
        if fallback_engine and fallback_engine != engine_type:
            try:
                print(f"Trying fallback engine: {fallback_engine}")
                fallback_engine_instance = TranscriptionEngineFactory.create_engine(fallback_engine, config)
                if fallback_engine_instance.is_available():
                    return fallback_engine_instance.transcribe_audio(audio_file_path, progress_cb, language)
                else:
                    raise Exception(f"Fallback engine '{fallback_engine}' is not available")
            except Exception as fallback_error:
                raise Exception(f"Both primary and fallback engines failed. Primary: {primary_error}, Fallback: {fallback_error}")
        else:
            raise primary_error