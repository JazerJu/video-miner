"""
Silero-VAD (Voice Activity Detection) Python Wrapper
基于ONNX模型的语音活动检测
"""
import os
import numpy as np
import onnxruntime as ort
from typing import List, Tuple, Optional
import torch
import torchaudio
import warnings

warnings.filterwarnings("ignore", category=UserWarning)


class SileroVAD:
    """
    Silero VAD 模型封装类
    使用预训练的ONNX模型进行语音活动检测
    """

    def __init__(self, model_path: Optional[str] = None, use_gpu: bool = False):
        """
        初始化 Silero VAD 模型

        Args:
            model_path: 模型文件路径，如果为None则使用默认路径
            use_gpu: 是否使用GPU加速
        """
        self.sample_rate = 16000
        self.use_gpu = use_gpu
        self.model = None
        self.session = None

        # 设置模型路径
        if model_path is None:
            model_root = os.environ.get("VIDUNDER_MODEL_ROOT", "")
            if model_root:
                model_path = os.path.join(model_root, "vad", "ggml-silero-vad.onnx")
            if not model_root or not os.path.exists(model_path):
                current_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(os.path.dirname(current_dir))
                model_path = os.path.join(project_root, 'models', 'ggml-silero-vad.onnx')

        # 如果ONNX模型不存在，尝试使用PyTorch模型
        if not os.path.exists(model_path):
            print(f"[VAD] ONNX model not found at {model_path}, using PyTorch backend")
            self._init_pytorch_model()
        else:
            print(f"[VAD] Loading ONNX model from {model_path}")
            self._init_onnx_model(model_path)

    def _init_onnx_model(self, model_path: str):
        """初始化ONNX模型"""
        try:
            # 配置ONNX Runtime会话
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if self.use_gpu else ['CPUExecutionProvider']

            self.session = ort.InferenceSession(
                model_path,
                providers=providers,
                sess_options=ort.SessionOptions()
            )
            self.model_type = 'onnx'
            print(f"[VAD] ONNX model loaded successfully with providers: {self.session.get_providers()}")

        except Exception as e:
            print(f"[VAD] Failed to load ONNX model: {e}")
            print(f"[VAD] Falling back to PyTorch backend")
            self._init_pytorch_model()

    def _init_pytorch_model(self):
        """初始化PyTorch模型"""
        try:
            # 加载预训练的Silero VAD模型
            self.model, _ = torch.hub.load(
                'snakers4/silero-vad',
                'silero_vad',
                force_reload=False
            )
            self.model_type = 'pytorch'

            # 如果可用，移动到GPU
            if self.use_gpu and torch.cuda.is_available():
                self.model = self.model.cuda()
                print(f"[VAD] PyTorch model loaded on GPU")
            else:
                print(f"[VAD] PyTorch model loaded on CPU")

        except Exception as e:
            print(f"[VAD] Failed to load PyTorch model: {e}")
            raise RuntimeError(f"Failed to initialize VAD model: {e}")

    def predict(self, audio: np.ndarray, sample_rate: int = 16000) -> float:
        """
        预测音频帧的语音概率

        Args:
            audio: 音频数据 (numpy数组)
            sample_rate: 采样率

        Returns:
            float: 语音活动概率 (0.0-1.0)
        """
        try:
            # 确保音频是正确的采样率
            if sample_rate != self.sample_rate:
                # 重采样音频
                audio = self._resample_audio(audio, sample_rate, self.sample_rate)

            # 确保音频是float32
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            if self.model_type == 'onnx':
                return self._predict_onnx(audio)
            else:
                return self._predict_pytorch(audio)

        except Exception as e:
            print(f"[VAD] Error predicting voice activity: {e}")
            return 0.0

    def _predict_onnx(self, audio: np.ndarray) -> float:
        """使用ONNX模型进行预测"""
        try:
            # 准备输入数据
            if len(audio.shape) == 1:
                audio = np.expand_dims(audio, axis=0)

            # ONNX推理
            input_name = self.session.get_inputs()[0].name
            output = self.session.run(None, {input_name: audio})

            # 提取概率
            probability = float(output[0][0][0]) if len(output[0][0]) > 0 else 0.0
            return max(0.0, min(1.0, probability))  # 确保在0-1范围内

        except Exception as e:
            print(f"[VAD] ONNX prediction error: {e}")
            return 0.0

    def _predict_pytorch(self, audio: np.ndarray) -> float:
        """使用PyTorch模型进行预测"""
        try:
            # 转换为torch tensor
            audio_tensor = torch.from_numpy(audio).float()

            # 如果是GPU模型，移动tensor到GPU
            if self.use_gpu and torch.cuda.is_available() and hasattr(self.model, 'cuda'):
                audio_tensor = audio_tensor.cuda()

            # 确保正确的形状
            if audio_tensor.dim() == 1:
                audio_tensor = audio_tensor.unsqueeze(0)

            # Silero VAD推理
            with torch.no_grad():
                probability = self.model(audio_tensor).item()

            return max(0.0, min(1.0, probability))  # 确保在0-1范围内

        except Exception as e:
            print(f"[VAD] PyTorch prediction error: {e}")
            return 0.0

    def _resample_audio(self, audio: np.ndarray, from_sr: int, to_sr: int) -> np.ndarray:
        """重采样音频"""
        try:
            # 使用scipy或librosa进行重采样
            try:
                import scipy.signal
                num_samples = int(len(audio) * to_sr / from_sr)
                resampled = scipy.signal.resample(audio, num_samples)
                return resampled.astype(np.float32)
            except ImportError:
                try:
                    import librosa
                    resampled = librosa.resample(audio, orig_sr=from_sr, target_sr=to_sr)
                    return resampled.astype(np.float32)
                except ImportError:
                    # 简单线性插值作为后备
                    print(f"[VAD] Warning: Using simple linear interpolation for resampling")
                    old_indices = np.arange(len(audio))
                    new_length = int(len(audio) * to_sr / from_sr)
                    new_indices = np.linspace(0, len(audio) - 1, new_length)
                    resampled = np.interp(new_indices, old_indices, audio)
                    return resampled.astype(np.float32)

        except Exception as e:
            print(f"[VAD] Error resampling audio: {e}")
            return audio

    def detect_speech_segments(self,
                             audio: np.ndarray,
                             sample_rate: int = 16000,
                             threshold: float = 0.5,
                             min_speech_duration_ms: int = 250,
                             min_silence_duration_ms: int = 800,
                             speech_pad_ms: int = 30) -> List[Tuple[float, float]]:
        """
        检测音频中的语音段落

        Args:
            audio: 音频数据
            sample_rate: 采样率
            threshold: VAD阈值 (0.0-1.0)
            min_speech_duration_ms: 最小语音持续时间 (毫秒)
            min_silence_duration_ms: 最小静音持续时间 (毫秒)
            speech_pad_ms: 语音边界填充 (毫秒)

        Returns:
            List[Tuple[float, float]]: 语音段落列表，每个元素为(开始时间, 结束时间)的秒数
        """
        try:
            # 确保音频是正确的采样率
            if sample_rate != self.sample_rate:
                audio = self._resample_audio(audio, sample_rate, self.sample_rate)
                sample_rate = self.sample_rate

            # 计算帧大小
            frame_length = int(0.032 * sample_rate)  # 32ms帧
            hop_length = int(0.008 * sample_rate)   # 8ms跳跃

            # 分帧处理
            frames = []
            for i in range(0, len(audio) - frame_length + 1, hop_length):
                frame = audio[i:i + frame_length]
                frames.append(frame)

            if not frames:
                return []

            # 对每一帧进行VAD预测
            probabilities = []
            for frame in frames:
                prob = self.predict(frame, sample_rate)
                probabilities.append(prob)

            # 转换时间阈值
            min_speech_frames = max(1, int(min_speech_duration_ms / (hop_length * 1000 / sample_rate)))
            min_silence_frames = max(1, int(min_silence_duration_ms / (hop_length * 1000 / sample_rate)))
            speech_pad_frames = int(speech_pad_ms / (hop_length * 1000 / sample_rate))

            # 检测语音段落
            speech_segments = []
            in_speech = False
            speech_start = 0

            for i, prob in enumerate(probabilities):
                is_speech = prob >= threshold

                if is_speech and not in_speech:
                    # 语音开始
                    in_speech = True
                    speech_start = max(0, i - speech_pad_frames) * hop_length / sample_rate

                elif not is_speech and in_speech:
                    # 语音结束
                    speech_end = min(len(probabilities), i + speech_pad_frames) * hop_length / sample_rate
                    duration_ms = (speech_end - speech_start) * 1000

                    # 检查最小语音持续时间
                    if duration_ms >= min_speech_duration_ms:
                        speech_segments.append((speech_start, speech_end))

                    in_speech = False

            # 处理最后一个语音段
            if in_speech:
                speech_end = len(probabilities) * hop_length / sample_rate
                duration_ms = (speech_end - speech_start) * 1000
                if duration_ms >= min_speech_duration_ms:
                    speech_segments.append((speech_start, speech_end))

            # 合并相邻的静音段（如果静音时间太短）
            if len(speech_segments) > 1:
                merged_segments = [speech_segments[0]]
                for current_start, current_end in speech_segments[1:]:
                    last_start, last_end = merged_segments[-1]
                    silence_duration = current_start - last_end

                    if silence_duration * 1000 < min_silence_duration_ms:
                        # 合并段落
                        merged_segments[-1] = (last_start, current_end)
                    else:
                        merged_segments.append((current_start, current_end))

                speech_segments = merged_segments

            print(f"[VAD] Detected {len(speech_segments)} speech segments")
            return speech_segments

        except Exception as e:
            print(f"[VAD] Error detecting speech segments: {e}")
            # 返回整个音频作为单个语音段
            audio_duration = len(audio) / sample_rate
            return [(0.0, audio_duration)]

    def __del__(self):
        """清理资源"""
        if self.session:
            del self.session
        if self.model and hasattr(self.model, 'cpu'):
            del self.model


def create_vad_model(model_path: Optional[str] = None, use_gpu: bool = False) -> SileroVAD:
    """
    创建VAD模型的便捷函数

    Args:
        model_path: 模型文件路径
        use_gpu: 是否使用GPU

    Returns:
        SileroVAD: VAD模型实例
    """
    return SileroVAD(model_path=model_path, use_gpu=use_gpu)


# 全局VAD模型实例（缓存）
_vad_model_instance = None


def get_vad_model(model_path: Optional[str] = None, use_gpu: bool = False) -> SileroVAD:
    """
    获取全局VAD模型实例（单例模式）

    Args:
        model_path: 模型文件路径
        use_gpu: 是否使用GPU

    Returns:
        SileroVAD: VAD模型实例
    """
    global _vad_model_instance

    if _vad_model_instance is None:
        _vad_model_instance = SileroVAD(model_path=model_path, use_gpu=use_gpu)

    return _vad_model_instance


def reset_vad_model():
    """重置全局VAD模型实例"""
    global _vad_model_instance
    if _vad_model_instance is not None:
        del _vad_model_instance
        _vad_model_instance = None