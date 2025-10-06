"""
TTS (Text-to-Speech) Voiceover Generation API Views
"""

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
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
        "voice": "longxiaochun_v2"  // 音色ID，默认'longxiaochun_v2'
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
