from faster_whisper import WhisperModel
from tqdm import tqdm
from typing import Optional, Tuple, List
from utils.video.time_convert import seconds_to_srt_time
import os


_MODEL: Optional[WhisperModel] = None

def get_configured_model_name() -> str:
    """从config.ini读取配置的模型名称"""
    try:
        from video.views.set_setting import load_all_settings
        settings_data = load_all_settings()
        return settings_data.get('Transcription Engine', {}).get('fwsr_model', 'large-v3')
    except:
        return 'large-v3'  # 默认模型

def get_model() -> WhisperModel:
    """
    返回一个全局 WhisperModel 实例。
    第一次调用时才会真正 load；之后都会复用。
    线程安全需求不高时，这样就够了；如需并发可加锁。
    """
    global _MODEL
    if _MODEL is None:
        # 1️⃣ 获取配置的模型名称
        model_name = get_configured_model_name()
        
        # 2️⃣ 确定模型路径：优先环境变量，否则基于当前工作目录构建路径
        model_dir = os.getenv("WHISPER_MODEL_DIR")
        if not model_dir:
            # 获取当前文件的目录，然后构建相对路径到 models
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 从 utils/wsr/ 回到项目根目录
            project_root = os.path.dirname(os.path.dirname(current_dir))
            model_dir = os.path.join(project_root, "models")
        
        print(f"Using model: {model_name}, directory: {model_dir}")
        
        # 警告：蒸馏模型对中文支持可能有限
        if "distil" in model_name.lower():
            print(f"[WARNING] Using distilled model '{model_name}' - English-only model")
            print(f"[WARNING] distil-large-v3 only supports English transcription. Use 'large-v3' or 'medium' for Chinese.")
        
        # 3️⃣ 设备与精度：按需修改
        _MODEL = WhisperModel(
            model_size_or_path=model_name,
            download_root=model_dir,
            device="cuda",          # "cpu" / "cuda"
            compute_type="float16", # "int8" / "int8_float16" / "float16" / ...
        )
    return _MODEL

from typing import Callable
def get_multilingual_transcription_params():
    """获取适合中英文混杂的转录参数"""
    return {
        'language': None,  # 让模型自动检测语言
        'word_timestamps': True,
        
        # 核心参数
        'temperature': [0.0, 0.2],  # 先尝试确定性，失败后稍加随机性
        'beam_size': 5,
        'patience': 1.0,
        'length_penalty': 1.0,  # 中性长度惩罚

        # 重复控制（对中文很重要）
        'repetition_penalty': 1.05,
        'no_repeat_ngram_size': 0,  # 中文可能有重复字符
        
        # 质量控制
        'compression_ratio_threshold': 2.4,
        'log_prob_threshold': -1.0,  # 稍微宽松，适应混合语言
        'no_speech_threshold': 0.8,
        
        # 上下文
        'condition_on_previous_text': True,
        'prompt_reset_on_temperature': 0.5,
        
        # 音频处理
        'vad_filter': True,
        'vad_parameters': {
            'threshold': 0.3,
            'min_speech_duration_ms': 100,
            'min_silence_duration_ms': 50
        },
        
        # 时间戳相关
        'max_initial_timestamp': 1.0,
        'prepend_punctuations': "\"'“¿([{-",
        'append_punctuations': "\"'.。,，!！?？:：”)]}、",
    }


# 识别音频文件，并启用逐字时间戳
def transcribe_audio(audio_file_path: str,
                     progress_cb: Callable[[float], None],
                     language: str = None) -> str:
    progress_cb("Running")
    # 识别音频文件，并启用逐字时间戳
    model = get_model()  # 懒加载
    params = get_multilingual_transcription_params()
    
    # 如果用户指定了语言，则覆盖语言参数
    if language and language != "None":
        params['language'] = language
        print(f"[faster_whisper] Using user-specified language: {language}")
        # 对中文进行特殊优化
        if language == "zh":
            print(f"[faster_whisper] Applying Chinese-specific optimizations")
            # 使用更保守的参数确保中文识别
            params['temperature'] = [0.0]  # 只使用确定性解码
            params['beam_size'] = 8  # 增加beam size
            params['repetition_penalty'] = 1.1  # 稍微提高重复惩罚
            params['log_prob_threshold'] = -0.8  # 提高质量阈值
    else:
        print(f"[faster_whisper] Using auto-detection (language=None)")
    
    print(f"[faster_whisper] Final parameters: language={params.get('language')}, temperature={params.get('temperature')}")
    print(audio_file_path,model)
    # 显式验证参数
    print(f"[faster_whisper] DEBUG - About to call model.transcribe with:")
    print(f"[faster_whisper] DEBUG - audio_file_path: {audio_file_path}")
    print(f"[faster_whisper] DEBUG - language param: {params.get('language', 'NOT_SET')}")
    
    segments, info = model.transcribe(
        audio_file_path,
        **params
    )
    
    # 记录语言检测和转录信息
    print(f"[faster_whisper] Language detection result: {info.language}")
    print(f"[faster_whisper] Language probability: {info.language_probability:.3f}")
    print(f"[faster_whisper] Parameters used - language: {params.get('language', 'None (auto-detect)')}")
    
    # 音频总时长，用于计算进度
    total_duration = round(info.duration, 2) or 1  
    print(f"[faster_whisper] === Audio Analysis ===")
    print(f"[faster_whisper] Total audio duration: {total_duration:.2f}s")
    print(f"[faster_whisper] Starting real-time transcription...")
    
    # VAD分析变量
    total_speech_duration = 0.0
    speech_segments_info = []
    
    # 字幕生成变量
    srt_content = ""
    idx = 1
    segment_count = 0
    
    # 实时处理segments生成器（这里才开始真正的转录工作）
    print(f"[faster_whisper] === Real-time Transcription Progress ===")
    
    try:
        for segment in segments:  # 这里开始实时转录，每个segment转录完成后立即处理
            segment_count += 1
            
            # 计算当前转录进度（基于时间）
            current_time = segment.end
            progress_percent = min((current_time / total_duration) * 100, 100)
            
            # 记录语音段信息（VAD结果）
            segment_duration = segment.end - segment.start
            total_speech_duration += segment_duration
            
            speech_segments_info.append({
                'start': round(segment.start, 2),
                'end': round(segment.end, 2),
                'duration': round(segment_duration, 2),
                'text': segment.text.strip()
            })
            
            # 生成字幕条目
            word_count = 0
            if segment.words:
                for word in segment.words:
                    srt_content += f"{idx}\n{seconds_to_srt_time(word.start)} --> " \
                                   f"{seconds_to_srt_time(word.end)}\n{word.word.strip()}\n\n"
                    idx += 1
                    word_count += 1
            else:
                # 如果关闭词级时间戳，打印segment级别
                srt_content += f"{idx}\n{seconds_to_srt_time(segment.start)} --> " \
                               f"{seconds_to_srt_time(segment.end)}\n{segment.text.strip()}\n\n"
                idx += 1
                word_count = 1
            
            # 实时输出转录进度
            print(f"[faster_whisper] Segment {segment_count:3d}: "
                  f"{segment.start:6.2f}s - {segment.end:6.2f}s "
                  f"({segment_duration:5.2f}s) | "
                  f"Progress: {progress_percent:5.1f}% | "
                  f"{word_count:2d} words | "
                  f"'{segment.text.strip()[:45]}{'...' if len(segment.text.strip()) > 45 else ''}'")
            
            # 每10个segment输出一次汇总
            if segment_count % 10 == 0:
                current_speech_ratio = (total_speech_duration / current_time) * 100 if current_time > 0 else 0
                print(f"[faster_whisper] === Progress Summary ===")
                print(f"[faster_whisper] Processed: {segment_count} segments, "
                      f"Duration: {current_time:.2f}s/{total_duration:.2f}s ({progress_percent:.1f}%), "
                      f"Speech ratio: {current_speech_ratio:.1f}%")
                      
    except Exception as e:
        print(f"[faster_whisper] Error during transcription: {e}")
        raise
    
    # VAD分析总结
    speech_ratio = (total_speech_duration / total_duration) * 100 if total_duration > 0 else 0
    avg_segment_length = total_speech_duration / len(speech_segments_info) if speech_segments_info else 0
    
    print(f"\n[faster_whisper] === VAD Analysis Summary ===")
    print(f"[faster_whisper] Total audio duration: {total_duration:.2f}s")
    print(f"[faster_whisper] Speech segments detected: {len(speech_segments_info)}")
    print(f"[faster_whisper] Total speech duration: {total_speech_duration:.2f}s")
    print(f"[faster_whisper] Speech-to-total ratio: {speech_ratio:.1f}%")
    print(f"[faster_whisper] Average segment length: {avg_segment_length:.2f}s")
    print(f"[faster_whisper] Silence duration: {total_duration - total_speech_duration:.2f}s ({100-speech_ratio:.1f}%)")
    
    # 语音时间轴概览（显示前几个和后几个segment）
    print(f"\n[faster_whisper] === Speech Timeline Overview ===")
    display_count = min(3, len(speech_segments_info))
    
    for i in range(display_count):
        seg = speech_segments_info[i]
        print(f"[faster_whisper] Timeline {i+1:2d}: {seg['start']:6.2f}s - {seg['end']:6.2f}s "
              f"({seg['duration']:5.2f}s) | {seg['text'][:35]}{'...' if len(seg['text']) > 35 else ''}")
    
    if len(speech_segments_info) > 6:
        print(f"[faster_whisper] ... ({len(speech_segments_info) - 6} middle segments omitted) ...")
        
        for i in range(max(display_count, len(speech_segments_info) - 3), len(speech_segments_info)):
            seg = speech_segments_info[i]
            print(f"[faster_whisper] Timeline {i+1:2d}: {seg['start']:6.2f}s - {seg['end']:6.2f}s "
                  f"({seg['duration']:5.2f}s) | {seg['text'][:35]}{'...' if len(seg['text']) > 35 else ''}")
    
    # 最终统计
    print(f"\n[faster_whisper] === Final Results ===")
    print(f"[faster_whisper] Generated {idx-1} subtitle entries from {segment_count} speech segments")
    print(f"[faster_whisper] Transcription completed successfully")
    
    progress_cb("Completed")
    return srt_content
