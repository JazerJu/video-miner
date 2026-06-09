from django.http import JsonResponse,HttpResponse,HttpResponseNotAllowed,HttpResponseNotFound,Http404,FileResponse,HttpResponseBadRequest
from ..models import Category, Video
from django.views import View
from django.conf import settings  # 确保这个在顶部
from django.shortcuts import get_object_or_404,render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from urllib.parse import unquote
import json,copy 
import os
import time
from ..tasks import subtitle_task_queue, subtitle_task_status

def _new_subtitle_task():
    """
    创建新字幕任务的初始状态结构
    必须与 tasks.py 中的 subtitle_task_status defaultdict 结构一致
    """
    return {
        "stages": {
            "transcribe": "Queued",
            "optimize":   "Queued",
            "translate":  "Queued",
        },
        "stage_progress": {
            "transcribe": 0,
            "optimize": 0,
            "translate": 0,
        },
        "stage_weights": {
            "transcribe": 0.40,
            "optimize": 0.30,
            "translate": 0.30,
        },
        "stage_detail": {
            "transcribe": "",
            "optimize": "",
            "translate": "",
        },
        "total_progress": 0,
        "optimize_total_chunks": 0,
        "optimize_completed_chunks": 0,
        "translate_total_chunks": 0,
        "translate_completed_chunks": 0,
    }


SAVE_DIR = 'media/saved_srt'
class SubtitleActionView(View):
    def dispatch(self, request, *args, **kwargs):
        self.action = kwargs.pop('action', None)
        print(self.action)
        # 从查询字符串中获取语言: /…/upload/?lang=en
        self.lang = request.GET.get("lang", "").lower()
        if not self.lang:
            return JsonResponse({"error": "No language code"}, status=400)
        self.lang = self.lang.lower()
        if self.lang not in {"en", "zh", "jp", "de", "system_define"}:
            return JsonResponse({"error": "Unsupported language code"}, status=400)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, video_id):
        if self.action == 'upload':
            return self.upload(request, video_id)
        elif self.action == 'delete':
            return self.delete(request, video_id)
        return HttpResponseNotAllowed(['POST'])
    # 通过"GET"语法获取字幕。
    def get(self, request, video_id):
        if self.action == 'query':
            return self.query(request, video_id)
        return HttpResponseNotAllowed(['GET'])
    
    def upload(self, request, video_id):
        # 验证请求数据格式
        if request.content_type != 'application/json':
            return JsonResponse(
                {"error": "Invalid content type, must be application/json"},
                status=400
            )

        try:
            # 解析 JSON 数据
            data = json.loads(request.body)
            srt_content = data.get('srtContent')
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON format"}, status=400)
        
        # 验证字幕文件
        if not srt_content:
            return JsonResponse(
                {"error": "Missing 'srtContent' in request body"},
                status=400
            )
        try:
            video = get_object_or_404(Video, pk=video_id)
            os.makedirs(SAVE_DIR, exist_ok=True)
            
            # 生成安全文件名
            file_name = f"{video_id}_{self.lang}.srt"
            file_path = os.path.abspath(os.path.join(SAVE_DIR, file_name))
            
            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as srt_file:
                srt_file.write(srt_content)
            
            # 更新数据库记录
            video.srt_path = file_name
            video.content_updated_at = timezone.now()
            video.save(update_fields=["srt_path", "content_updated_at"])
            
            # logger.info(f"Updated subtitles for video {video_id}")
            return JsonResponse({
                "message": "Subtitles saved and path updated successfully",
                "path": video.srt_path,
                "success":True,
            }, status=201)  # 201 Created 更符合语义
        except Exception as e:
            # logger.error(f"Unexpected error: {str(e)}")
            return JsonResponse({"error": "Internal server error"}, status=500)
    
    
    def query(self,request,video_id):
        video = get_object_or_404(Video, pk=video_id)
        print(video_id)
        if not video.srt_path:
            raise Http404("No subtitles available for this video")
        
        # 构建完整文件路径
        file_name = f"{video_id}_{self.lang}.srt"
        file_path = os.path.abspath(os.path.join(SAVE_DIR, file_name))
        # print(file_path)

        # 检查文件类型
        if not file_path.endswith('.srt'):
            raise Http404("Invalid subtitle format")
        # 安全验证路径
        if not os.path.exists(file_path):
            raise Http404("Subtitle file not found")
        
        # 发送文件响应
        return FileResponse(
            open(file_path, 'rb'),
            filename=os.path.basename(file_path),
            as_attachment=False,
            content_type='text/plain; charset=utf-8'
        )

    def delete(self,request,video_id):
        pass


##** 字幕生成任务 **##
class SubtitleGenerationAddView(View):
    def dispatch(self, request, *args, **kwargs):
        self.action = kwargs.pop('action', None)
        print(self.action)
        return super().dispatch(request, *args, **kwargs)
    def post(self, request):
        print(json.loads(request.body))
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return HttpResponseBadRequest('Invalid JSON')

        video_id_list = payload.get('video_id_list')
        video_name_list = payload.get('video_name_list')
        src_lang = payload.get('src_lang')
        trans_lang = payload.get('trans_lang')
        emphasize_dst = payload.get('emphasize_dst', '')
        if not video_id_list:
            return JsonResponse({'error': 'Missing "video_id_list" field'}, status=400)
        if not video_name_list:
            return HttpResponseBadRequest('Missing "video_name_list"')
        # 生成字幕的Task
        print("src_lang,trans_lang:",src_lang,trans_lang)
        return self.enqueue_subtitle_task(request,video_id_list,video_name_list,src_lang,trans_lang,emphasize_dst)
    def enqueue_subtitle_task(self, request, video_id_list: list, video_name_list: list,src_lang,trans_lang,emphasize_dst):
        # 把视频生成字幕（翻译可选）的任务加入队列
        for idx,vid in enumerate(video_id_list,start=1):
            title=f"{video_name_list[idx-1]}"
            
            # 在数据库中更新视频的raw_lang字段
            try:
                video = Video.objects.get(pk=vid)
                if src_lang in ['en', 'zh', 'jp', 'de']:
                    video.raw_lang = src_lang
                    video.save(update_fields=['raw_lang'])
            except Video.DoesNotExist:
                pass  # 即使找不到视频也继续创建任务
            
            subtitle_task_status[vid] = {
                "filename": title,
                "src_lang": src_lang,
                "trans_lang": trans_lang,
                "emphasize_dst": emphasize_dst,
                "video_id":vid,
                **_new_subtitle_task()
            }
            subtitle_task_queue.put(str(vid))

        return JsonResponse({"success": True})

# 重试 / 删除
class SubtitleGenerationTaskView(View):
    def dispatch(self, request, *args, **kwargs):
        self.action = kwargs.pop('action', None)
        print(self.action)
        return super().dispatch(request, *args, **kwargs)
    def post(self, request, video_id):
        if self.action == 'retry':
            return self.retry(request, video_id)
        elif self.action == 'delete':
            return self.delete(request, video_id)
        return HttpResponseNotAllowed(['POST'])
    def retry(self, request, video_id):
        old_id = video_id
        old = subtitle_task_status.get(old_id)
        if not old:
            return HttpResponseBadRequest("Task not found")

        # 深拷贝旧状态，避免并发污染
        new_status = copy.deepcopy(old)
        if new_status.get("translation_only"):
            new_status["stages"] = {
                "transcribe": "Skipped",
                "optimize": "Skipped",
                "translate": "Queued",
            }
            new_status["stage_progress"] = {
                "transcribe": 100,
                "optimize": 100,
                "translate": 0,
            }
            new_status["total_progress"] = 70
        else:
            new_status["stages"] = {
                "transcribe": "Queued",
                "optimize": "Queued",
                "translate": "Queued",
            }
            new_status["stage_progress"] = {
                "transcribe": 0,
                "optimize": 0,
                "translate": 0,
            }
            new_status["total_progress"] = 0
        new_status["stage_detail"] = {
            "transcribe": "",
            "optimize": "",
            "translate": "",
        }
        # 覆写回 download_status 同一个 key
        subtitle_task_status[old_id] = new_status
        subtitle_task_queue.put(str(old_id))
        return JsonResponse({"task_id": old_id,'message': 'Retry scheduled'})
    # DELETE 方法 
    def delete(self, request, video_id):
        # 确保 URL action 是 delete，否则拒绝
        if self.action != 'delete':
            return HttpResponseNotAllowed(['DELETE'])

        if video_id not in subtitle_task_status:
            return JsonResponse({'error': 'Task not found'}, status=404)

        # 尝试从队列中移除（视你的队列实现而定）
        try:
            subtitle_task_queue.remove(video_id)
        except (ValueError, AttributeError):
            print("error")
            pass  

        subtitle_task_status.pop(video_id, None)
        return JsonResponse({'message': 'Download task deleted'})
        

class SubtitleGenerationInfoView(View):
    def get(self, request, task_id):
        task = subtitle_task_status.get(int(task_id))
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)
        return JsonResponse({
            "status": task.status,
            "progress": task.progress,
            "video_id": task.video_id
        })

class AllSubtitleGenerationInfoView(View):
    """
    GET /subtitle_generation/status/all/
    返回 JSON: {
      "<task_id1>": { "stages": {...}, "finished": ..., "title": ..., ... },
      "<task_id2>": { ... },
      ...
    }
    """
    def get(self, request):
        # 强制把 defaultdict 转成普通 dict，避免序列化问题
        all_status = {tid: data for tid, data in subtitle_task_status.items()}
        return JsonResponse(all_status)


@method_decorator(csrf_exempt, name="dispatch")
class SubtitleTranslationAddView(View):
    """Generate translation subtitles only, based on existing original subtitles"""
    
    def post(self, request):
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return HttpResponseBadRequest('Invalid JSON')

        video_id_list = payload.get('video_id_list')
        video_name_list = payload.get('video_name_list')
        target_lang = payload.get('target_lang')
        emphasize_dst = payload.get('emphasize_dst', '')
        
        if not video_id_list:
            return JsonResponse({'error': 'Missing "video_id_list" field'}, status=400)
        if not video_name_list:
            return HttpResponseBadRequest('Missing "video_name_list"')
        if not target_lang or target_lang not in ['zh', 'en', 'jp', 'de']:
            return JsonResponse({'error': 'Invalid target language'}, status=400)
        
        # 检查所有视频是否存在原始字幕
        for vid in video_id_list:
            try:
                video = Video.objects.get(pk=vid)
                # 检查原始字幕文件是否存在
                original_lang = video.raw_lang or 'en'
                file_name = f"{vid}_{original_lang}.srt"
                file_path = os.path.abspath(os.path.join(SAVE_DIR, file_name))
                
                if not os.path.exists(file_path):
                    return JsonResponse({
                        'error': f'Original subtitle not found for video {video.name}. Please generate original subtitles first.'
                    }, status=400)
                    
            except Video.DoesNotExist:
                return JsonResponse({'error': f'Video with ID {vid} not found'}, status=404)
        
        # 生成翻译任务
        return self.enqueue_translation_task(request, video_id_list, video_name_list, target_lang, emphasize_dst)
    
    def enqueue_translation_task(self, request, video_id_list: list, video_name_list: list, target_lang: str, emphasize_dst: str):
        # 添加仅翻译任务到队列
        for idx, vid in enumerate(video_id_list, start=1):
            title = f"{video_name_list[idx-1]}"
            
            subtitle_task_status[vid] = {
                "filename": title,
                "src_lang": "existing",  # 表示使用现有字幕
                "trans_lang": target_lang,
                "emphasize_dst": emphasize_dst,
                "video_id": vid,
                "translation_only": True,  # 标志表示仅翻译模式
                "stages": {
                    "transcribe": "Skipped",  # 跳过转录
                    "optimize": "Skipped",    # 跳过优化
                    "translate": "Queued",    # 仅执行翻译
                },
                # 🆕 进度追踪字段
                "stage_progress": {
                    "transcribe": 100,  # 跳过阶段显示100%
                    "optimize": 100,    # 跳过阶段显示100%
                    "translate": 0,
                },
                "stage_weights": {
                    "transcribe": 0.40,
                    "optimize": 0.30,
                    "translate": 0.30,
                },
                "total_progress": 70,  # transcribe(40%) + optimize(30%) = 70%已完成
                "optimize_total_chunks": 0,
                "optimize_completed_chunks": 0,
                "translate_total_chunks": 0,
                "translate_completed_chunks": 0,
            }
            subtitle_task_queue.put(str(vid))

        return JsonResponse({"success": True, "message": f"Translation tasks queued for {len(video_id_list)} videos"})
