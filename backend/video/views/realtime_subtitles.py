"""
实时字幕生成视图 - 支持逐句返回转录结果
Real-time subtitle generation with sentence-by-sentence streaming
"""
from django.http import JsonResponse, StreamingHttpResponse
from django.views import View
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
import time
import threading
from ..models import Video
from ..tasks import realtime_subtitle_status
from utils.wsr.transcription_engine import transcribe_with_engine
from .videos import get_transcription_audio_path


def generate_realtime_subtitles(task_id: str, video_id: int, language: str = None):
    """
    实时生成字幕的后台任务 - 逐句输出结果

    Args:
        task_id: 任务ID
        video_id: 视频ID
        language: 源语言代码 (en/zh/jp/None for auto-detect)
    """
    task_status = realtime_subtitle_status[task_id]
    task_status["status"] = "Running"

    try:
        # 获取音频文件路径
        audio_path = get_transcription_audio_path(video_id)

        # 实时进度回调
        def progress_callback(progress):
            if isinstance(progress, str):
                # Running/Completed 状态
                task_status["status"] = progress if progress != "Running" else "Running"
            else:
                # 百分比进度（暂不使用）
                pass

        # 逐句回调 - 每生成一个字幕条目就添加到列表
        def sentence_callback(entry_index, start_time, end_time, text):
            """
            每当生成一个字幕条目时调用

            Args:
                entry_index: 条目索引（从1开始）
                start_time: 开始时间（SRT格式 "HH:MM:SS,mmm"）
                end_time: 结束时间
                text: 字幕文本
            """
            entry = {
                "index": entry_index,
                "start": start_time,
                "end": end_time,
                "text": text
            }

            task_status["subtitle_entries"].append(entry)
            task_status["completed_entries"] = len(task_status["subtitle_entries"])
            task_status["current_entry"] = entry

            print(f"[RealtimeSubtitle] Task {task_id}: Entry {entry_index} - {text[:30]}...")

        # 调用转录引擎（需要修改 transcribe_with_engine 支持逐句回调）
        print(f"[RealtimeSubtitle] Starting transcription for task {task_id}, video {video_id}")

        # 🔧 临时方案：使用现有引擎，转录完成后模拟逐句输出
        # TODO: 修改 whisper_cpp_wsr.py 支持真正的实时回调
        srt_content = transcribe_with_engine(
            engine_type='whisper_cpp',
            audio_file_path=audio_path,
            progress_cb=progress_callback,
            language=language
        )

        # 解析SRT并逐句添加
        entries = parse_srt_entries(srt_content)
        task_status["total_entries"] = len(entries)

        for idx, entry in enumerate(entries, start=1):
            sentence_callback(
                entry_index=idx,
                start_time=entry["start"],
                end_time=entry["end"],
                text=entry["text"]
            )
            # 模拟逐句延迟（实际应该由引擎实时回调）
            time.sleep(0.05)

        task_status["status"] = "Completed"
        print(f"[RealtimeSubtitle] Task {task_id} completed: {len(entries)} entries")

    except Exception as e:
        task_status["status"] = "Failed"
        task_status["error_message"] = str(e)
        print(f"[RealtimeSubtitle] Task {task_id} failed: {e}")


def parse_srt_entries(srt_content: str):
    """
    解析SRT内容为字幕条目列表

    Returns:
        List of {"start": "00:00:01,000", "end": "00:00:03,000", "text": "..."}
    """
    import re
    entries = []
    lines = srt_content.strip().split('\n')

    i = 0
    while i < len(lines):
        # Skip empty lines
        if not lines[i].strip():
            i += 1
            continue

        try:
            # Line 1: Index
            index = int(lines[i].strip())

            # Line 2: Timestamp
            i += 1
            timestamp_line = lines[i].strip()
            match = re.match(r'(.+?)\s*-->\s*(.+)', timestamp_line)
            if not match:
                i += 1
                continue

            start, end = match.groups()

            # Line 3+: Text
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i])
                i += 1

            text = '\n'.join(text_lines)

            entries.append({
                "start": start.strip(),
                "end": end.strip(),
                "text": text
            })

        except (ValueError, IndexError):
            i += 1
            continue

    return entries


@method_decorator(csrf_exempt, name='dispatch')
class RealtimeSubtitleView(View):
    """
    实时字幕生成API视图

    POST /api/realtime_subtitle/start/<video_id>?lang=en
        - 启动实时字幕生成任务
        - 返回: {"task_id": "...", "status": "Queued"}

    GET /api/realtime_subtitle/status/<task_id>
        - 获取任务状态和已生成的字幕条目
        - 返回: {"status": "Running", "completed_entries": 10, "subtitle_entries": [...]}

    GET /api/realtime_subtitle/stream/<task_id>
        - Server-Sent Events (SSE) 流式返回字幕
        - 实时推送每个新生成的字幕条目
    """

    def post(self, request, video_id):
        """启动实时字幕生成任务"""
        # 获取语言参数
        language = request.GET.get('lang', '').lower()
        if language and language not in ['en', 'zh', 'jp']:
            return JsonResponse({"error": "Invalid language code"}, status=400)

        # 验证视频是否存在
        video = get_object_or_404(Video, pk=video_id)

        # 生成任务ID
        task_id = f"realtime_{video_id}_{int(time.time())}"

        # 初始化任务状态
        realtime_subtitle_status[task_id] = {
            "task_id": task_id,
            "video_id": video_id,
            "filename": video.name,
            "status": "Queued",
            "total_entries": 0,
            "completed_entries": 0,
            "current_entry": None,
            "subtitle_entries": [],
            "error_message": "",
            "created_at": int(time.time()),
        }

        # 启动后台转录线程
        thread = threading.Thread(
            target=generate_realtime_subtitles,
            args=(task_id, video_id, language or None),
            daemon=True
        )
        thread.start()

        return JsonResponse({
            "task_id": task_id,
            "status": "Queued",
            "message": "Real-time subtitle generation started"
        })

    def get(self, request, task_id):
        """获取任务状态"""
        if task_id not in realtime_subtitle_status:
            return JsonResponse({"error": "Task not found"}, status=404)

        task = realtime_subtitle_status[task_id]

        # 返回任务状态和已生成的字幕条目
        return JsonResponse({
            "task_id": task["task_id"],
            "video_id": task["video_id"],
            "filename": task["filename"],
            "status": task["status"],
            "total_entries": task["total_entries"],
            "completed_entries": task["completed_entries"],
            "current_entry": task["current_entry"],
            "subtitle_entries": task["subtitle_entries"],
            "error_message": task["error_message"],
        })


@method_decorator(csrf_exempt, name='dispatch')
class RealtimeSubtitleStreamView(View):
    """
    Server-Sent Events (SSE) 流式字幕推送

    Usage (JavaScript):
        const eventSource = new EventSource('/api/realtime_subtitle/stream/<task_id>');
        eventSource.onmessage = (event) => {
            const entry = JSON.parse(event.data);
            console.log(entry.text);
        };
    """

    def get(self, request, task_id):
        """SSE流式返回字幕条目"""
        if task_id not in realtime_subtitle_status:
            return JsonResponse({"error": "Task not found"}, status=404)

        def event_stream():
            """生成SSE事件流"""
            task = realtime_subtitle_status[task_id]
            last_sent_count = 0

            while True:
                current_count = len(task["subtitle_entries"])

                # 发送新增的字幕条目
                if current_count > last_sent_count:
                    for entry in task["subtitle_entries"][last_sent_count:current_count]:
                        yield f"data: {json.dumps(entry)}\n\n"
                    last_sent_count = current_count

                # 任务完成或失败时结束流
                if task["status"] in ["Completed", "Failed"]:
                    yield f"event: end\ndata: {json.dumps({'status': task['status']})}\n\n"
                    break

                time.sleep(0.1)  # 100ms 轮询间隔

        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # Disable Nginx buffering
        return response
