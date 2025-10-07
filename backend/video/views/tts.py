"""
TTS (Text-to-Speech) Voiceover Generation API Views
"""

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from ..models import Video
from ..tasks import tts_queue, tts_task_status
import json
import os
import time
import uuid


@method_decorator(csrf_exempt, name='dispatch')
class TTSGenerateView(View):
    """
    POST /api/tts/generate/<video_id>
    创建TTS配音生成任务

    Request body:
    {
        "language": "zh",  // zh/en/jp, 默认'zh'
        "voice": "longxiaochun_v2",  // 音色ID，默认'longxiaochun_v2'
        "use_audio_clone": false,  // 是否使用音频克隆功能
        "audio_reference_url": "https://bucket.oss-region.aliyuncs.com/path/to/audio.mp3",  // 音频参考URL
        "reference_text": "参考音频的文本内容"  // 参考音频的文本内容
    }

    Response:
    {
        "success": true,
        "task_id": "tts_xxx",
        "message": "TTS task created"
    }

    Error response:
    {
        "error": "no subtitle for this video"
    }
    """
    def post(self, request, video_id):
        try:
            # 解析请求参数
            try:
                data = json.loads(request.body) if request.body else {}
            except json.JSONDecodeError:
                data = {}

            # 获取参数，使用默认值
            language = data.get('language', 'zh')
            voice = data.get('voice', 'longxiaochun_v2')
            use_audio_clone = data.get('use_audio_clone', False)
            audio_reference_url = data.get('audio_reference_url', None)
            reference_text = data.get('reference_text', None)

            # 如果使用音频克隆但没有提供音频URL，则返回错误
            if use_audio_clone and not audio_reference_url:
                return JsonResponse(
                    {"error": "Audio reference URL is required when using audio clone"},
                    status=400
                )

            # 验证language参数
            if language not in ['zh', 'en', 'jp']:
                return JsonResponse(
                    {"error": f"Invalid language: {language}. Must be zh/en/jp"},
                    status=400
                )

            # 检查视频是否存在
            try:
                video = Video.objects.get(pk=video_id)
            except Video.DoesNotExist:
                return JsonResponse(
                    {"error": f"Video not found: {video_id}"},
                    status=404
                )

            # 检查字幕文件是否存在
            srt_filename = f"{video_id}_{language}.srt"
            srt_path = os.path.join('media/saved_srt', srt_filename)

            if not os.path.exists(srt_path):
                return JsonResponse(
                    {"error": "no subtitle for this video"},
                    status=400
                )

            # 生成任务ID
            task_id = f"tts_{uuid.uuid4().hex[:12]}"

            # 创建任务状态
            tts_task_status[task_id].update({
                "task_id": task_id,
                "video_id": video_id,
                "video_name": video.name,
                "language": language,
                "voice": voice,
                "status": "Queued",
                "progress": 0,
                "total_segments": 0,
                "completed_segments": 0,
                "output_file": "",
                "error_message": "",
                "created_at": time.time(),
                "use_audio_clone": use_audio_clone,
                "audio_reference_url": audio_reference_url,
                "reference_text": reference_text,
            })

            # 添加到任务队列
            tts_queue.put(task_id)

            print(f"[TTS API] Task created: {task_id} for video {video_id}, language: {language}, voice: {voice}")

            return JsonResponse({
                "success": True,
                "task_id": task_id,
                "message": "TTS task created successfully"
            })

        except Exception as e:
            print(f"[TTS API] Error creating task: {e}")
            return JsonResponse(
                {"error": str(e)},
                status=500
            )


class AllTTSStatusView(View):
    """
    GET /api/tts/status
    获取所有TTS任务状态

    Response:
    {
        "success": true,
        "data": {
            "tts_xxx": {
                "task_id": "tts_xxx",
                "video_id": 123,
                "video_name": "Example Video",
                "language": "zh",
                "voice": "longxiaochun_v2",
                "status": "Running",
                "progress": 45,
                "total_segments": 100,
                "completed_segments": 45,
                "output_file": "abc123_zh.mp4",
                "error_message": "",
                "created_at": 1234567890
            },
            ...
        }
    }
    """
    def get(self, request):
        try:
            # 将defaultdict转为普通dict返回
            status_data = dict(tts_task_status)
            return JsonResponse({
                "success": True,
                "data": status_data
            })

        except Exception as e:
            print(f"[TTS API] Error fetching all status: {e}")
            return JsonResponse(
                {
                    "success": False,
                    "error": str(e)
                },
                status=500
            )


class TTSStatusView(View):
    """
    GET /api/tts/<task_id>/status
    获取单个TTS任务状态

    Response:
    {
        "task_id": "tts_xxx",
        "video_id": 123,
        "status": "Completed",
        "progress": 100,
        ...
    }
    """
    def get(self, request, task_id):
        try:
            if task_id not in tts_task_status:
                return JsonResponse(
                    {"error": f"Task not found: {task_id}"},
                    status=404
                )

            task_data = dict(tts_task_status[task_id])
            return JsonResponse(task_data)

        except Exception as e:
            print(f"[TTS API] Error fetching task status: {e}")
            return JsonResponse(
                {"error": str(e)},
                status=500
            )


@method_decorator(csrf_exempt, name='dispatch')
class DeleteTTSTaskView(View):
    """
    DELETE /api/tts/<task_id>/delete
    删除TTS任务（仅删除任务状态，不删除生成的文件）

    Response:
    {
        "success": true,
        "message": "Task deleted"
    }
    """
    def delete(self, request, task_id):
        try:
            if task_id not in tts_task_status:
                return JsonResponse(
                    {"error": f"Task not found: {task_id}"},
                    status=404
                )

            # 删除任务状态
            del tts_task_status[task_id]

            print(f"[TTS API] Task deleted: {task_id}")

            return JsonResponse({
                "success": True,
                "message": "Task deleted successfully"
            })

        except Exception as e:
            print(f"[TTS API] Error deleting task: {e}")
            return JsonResponse(
                {"error": str(e)},
                status=500
            )


@method_decorator(csrf_exempt, name='dispatch')
class RetryTTSTaskView(View):
    """
    POST /api/tts/<task_id>/retry
    重试失败的TTS任务

    Response:
    {
        "success": true,
        "message": "Task requeued"
    }
    """
    def post(self, request, task_id):
        try:
            if task_id not in tts_task_status:
                return JsonResponse(
                    {"error": f"Task not found: {task_id}"},
                    status=404
                )

            task = tts_task_status[task_id]

            # 只允许重试Failed状态的任务
            if task["status"] != "Failed":
                return JsonResponse(
                    {"error": f"Cannot retry task with status: {task['status']}"},
                    status=400
                )

            # 重置任务状态
            task["status"] = "Queued"
            task["progress"] = 0
            task["completed_segments"] = 0
            task["error_message"] = ""

            # 重新加入队列
            tts_queue.put(task_id)

            print(f"[TTS API] Task requeued: {task_id}")

            return JsonResponse({
                "success": True,
                "message": "Task requeued successfully"
            })

        except Exception as e:
            print(f"[TTS API] Error retrying task: {e}")
            return JsonResponse(
                {"error": str(e)},
                status=500
            )


class VideoLanguageTracksView(View):
    """
    GET /api/video/<video_id>/languages
    获取视频的可用语言轨道列表

    Response:
    {
        "success": true,
        "data": {
            "video_id": 123,
            "video_name": "Example Video",
            "languages": [
                {
                    "code": "en",
                    "name": "English",
                    "type": "original",
                    "url": "/media/saved_video/492426528762527d073f40b1faf37d85.mp4"
                },
                {
                    "code": "zh",
                    "name": "中文",
                    "type": "tts",
                    "url": "/media/saved_video/492426528762527d073f40b1faf37d85_zh.mp4"
                }
            ]
        }
    }
    """

    def get(self, request, video_id):
        try:
            # 获取视频对象
            video = Video.objects.get(pk=video_id)

            # 语言代码映射
            language_names = {
                'en': 'English',
                'zh': '中文',
                'jp': 'Japanese'
            }

            languages = []

            # 添加原始语言轨道
            if video.raw_lang and video.url:
                original_url = f"/media/saved_video/{video.url}"
                # 检查文件是否存在
                full_path = os.path.join(settings.MEDIA_ROOT, 'saved_video', video.url)
                if os.path.exists(full_path):
                    languages.append({
                        'code': video.raw_lang,
                        'name': language_names.get(video.raw_lang, video.raw_lang.upper()),
                        'type': 'original',
                        'url': original_url
                    })

            # 扫描 TTS 生成的语言文件
            base_name = os.path.splitext(video.url)[0] if video.url else str(video.id)
            saved_video_dir = os.path.join(settings.MEDIA_ROOT, 'saved_video')

            if os.path.exists(saved_video_dir):
                for filename in os.listdir(saved_video_dir):
                    # 查找格式为 <base_name>_<lang>.mp4 的文件
                    if filename.startswith(base_name) and filename.endswith('.mp4'):
                        # 提取语言代码 (例如: video_zh.mp4 -> zh)
                        parts = filename[len(base_name):].lstrip('_').split('.')
                        if len(parts) >= 2:
                            lang_code = parts[0]
                            if lang_code in language_names and lang_code != video.raw_lang:
                                tts_url = f"/media/saved_video/{filename}"
                                languages.append({
                                    'code': lang_code,
                                    'name': language_names[lang_code],
                                    'type': 'tts',
                                    'url': tts_url
                                })

            return JsonResponse({
                'success': True,
                'data': {
                    'video_id': video_id,
                    'video_name': video.name,
                    'languages': languages
                }
            })

        except Video.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Video not found'
            }, status=404)

        except Exception as e:
            print(f"[Language Tracks API] Error: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
