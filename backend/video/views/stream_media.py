from django.http import JsonResponse,HttpResponseNotAllowed
from django.views import View
from django.views.decorators.csrf import csrf_exempt
import json, time, copy
import requests
import re
from django.utils.decorators import method_decorator
from utils.stream_downloader.bili_download import get_video_info
from utils.stream_downloader import bili_download
from utils.stream_downloader.youtube_download import YouTubeDownloader
from django.views.decorators.http import require_POST
from ..tasks import download_queue, download_status, download_status_lock
from yt_dlp import YoutubeDL
"""
这个文件用于下载流媒体和查询流媒体信息，作为中间件继承download_status中的变量
区分是油管还是B站，
并调用utils中的stream_download函数下载视频，
返回开始下载/下载成功，失败等task_status。
"""
# **0. Utils function
# 替换标题中的特殊字符 --> 用于文件命名。
def sanitize_filename(title: str) -> str:
    special_chars = r"[ |?？*:\"<>/\\&%#@!()+^~,\';.]"
    return re.sub(special_chars, "-", title)

def _new_download_status():
    return {
        "stages": {
            "video": {"status": "Queued"},
            "audio":   {"status": "Queued"},
            "merge":  {"status": "Queued"},
            "convert": {"status": "Queued"},  # 新增AV1转换阶段
        },
        "overall": 0,
    }

class InfoView(View):
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    @csrf_exempt
    def post(self, request):
        # 1) 先解析 JSON body获取url参数。
        try:
            data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        url = data.get('url')
        if not url:
            return JsonResponse({'error': 'Missing "url" field'}, status=400)

        # 2) 根据不同平台调用不同方法
        if 'bilibili' in url:
            info = self.biliinfo(url)
        elif 'youtube' in url:
            info = self.youtubeinfo(url)
        elif 'podcasts.apple.com' in url:
            info = self.podcastinfo(url)
        else:
            return JsonResponse({'error': 'Unsupported URL'}, status=400)

        # 3) 返回处理结果（必须可 JSON 序列化）
        return JsonResponse(info)
    def biliinfo(self,url):
        """
        通过用户输入的avid或者bvid，
        返回视频的基本信息&合集中总共的视频数。
        """
        print("startbiliinfo")
        bvid, avid, p=bili_download.extract_av_bv_p(url)
        info = bili_download.get_video_info(bvid=bvid, avid=avid)
        bvid = info['bvid']
        owner = info['owner']
        pic_url = info['pic_url']
        title = info['title']
        duration = info['duration']
        # author = info['author']
        cids, data=bili_download.get_cid(bvid=bvid, avid=avid)
        print(bvid,pic_url,title,len(cids))
        return {
            "bvid":bvid,
            "owner":owner,
            "duration":duration,
            "thumbnail":pic_url,
            "title":title,
            "collectionCount":len(cids),
            "video_data":data
            }

    def youtubeinfo(self, url):
        """
        通过用户输入的YouTube URL，
        返回视频的基本信息。
        """
        print("start youtubeinfo")
        downloader = YouTubeDownloader()
        info = downloader.get_video_info(url)
        
        if not info:
            return {"error": "Failed to fetch YouTube video info"}
            
        # 格式化时长 (从秒转换为可读格式)
        duration = info.get('duration', 0)
        
        # 由于 YouTube 视频通常是单个视频，我们创建一个简单的 video_data 结构
        video_data = [{
            "cid": info.get('id', ''),
            "part": info.get('title', 'YouTube Video'),
            "page": 1
        }]
        
        return {
            "bvid": info.get('id', ''),  # YouTube video ID
            "owner": info.get('uploader', ''),
            "duration": duration,
            "thumbnail": info.get('thumbnail', ''),
            "title": info.get('title', ''),
            "collectionCount": 1,  # YouTube 视频通常是单个视频
            "video_data": video_data
        }

    def podcastinfo(self, url):
        """
        通过用户输入的Apple Podcast URL，
        返回播客的基本信息。
        """
        print("start podcastinfo")
        ydl_opts = {
            'quiet': True,
            'no_download': True,  # Only extract info, don't download
        }
        
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                title = info.get('title', '')
                duration = info.get('duration', 0)
                series = info.get('series', '')
                episode = info.get('episode', '')
                description = info.get('description', '')
                thumbnail = info.get('thumbnail', '')
                
                # 创建简单的 audio_data 结构
                audio_data = [{
                    "cid": info.get('id', ''),
                    "part": title,
                    "page": 1
                }]
                
                return {
                    "bvid": info.get('id', ''),  # Podcast episode ID
                    "owner": series or info.get('uploader', ''),
                    "duration": duration,
                    "thumbnail": thumbnail,
                    "title": title,
                    "collectionCount": 1,  # 播客通常是单个音频
                    "video_data": audio_data,
                    "episode": episode,
                    "description": description[:200] + '...' if len(description) > 200 else description
                }
                
        except Exception as e:
            print(f"Error extracting podcast info: {e}")
            return {"error": f"Failed to fetch Apple Podcast info: {str(e)}"}


from django.http import HttpResponseBadRequest
class DownloadActionView(View):
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

        url = payload.get('url')
        if not url:
            return JsonResponse({'error': 'Missing "url" field'}, status=400)
        if "bilibili" in url:
            bvid  = payload.get('bvid')
            cids = payload.get('cids',"1111")
            parts = payload.get('parts')   
            filename = payload.get('filename')
            if not bvid:
                return HttpResponseBadRequest('Missing "bvid"')
            # 调用B站 api下载视频
            return self.enqueue_download_task(request,bvid,cids,parts,filename)
        elif "youtube" in url:
            video_id = payload.get('bvid')  # YouTube video ID stored in bvid field
            filename = payload.get('filename')
            if not video_id:
                return HttpResponseBadRequest('Missing YouTube video ID')
            # 调用YouTube api下载视频
            return self.enqueue_youtube_download_task(request, url, video_id, filename)
        elif "podcasts.apple.com" in url:
            episode_id = payload.get('bvid')  # Podcast episode ID stored in bvid field
            filename = payload.get('filename')
            if not episode_id:
                return HttpResponseBadRequest('Missing Apple Podcast episode ID')
            # 调用Apple Podcast api下载音频
            return self.enqueue_podcast_download_task(request, url, episode_id, filename)
        else:
            return JsonResponse({'error': 'Unsupported URL platform'}, status=400)
    def enqueue_download_task(self, request,bvid, cids: list,parts,filename):
        # sessdata不在这里传入，默认已经最新
        # sessdata=config.sessdata
        # 2. 构造视频完整页面 URL（可选）
        url = f"https://www.bilibili.com/video/{bvid}"

        # 3. 新建 task_id，并在全局状态 dict 里初始化
        task_id = int(time.time() * 1000)
        for idx,cid in enumerate(cids,start=1):
            task_id_per_cid=str(task_id)+str(idx)
            title=f"{filename}-p{idx}-{parts[idx-1]}"
            with download_status_lock:
                download_status[task_id_per_cid] = {
                    "bvid": bvid,
                    "title":title,
                    "url":  url,
                    "cid": cid,
                    **_new_download_status(),
                }
            print(idx,cid,filename)

            # 4. 推送到后台队列
            download_queue.put(task_id_per_cid)
        return JsonResponse({"success": True})

    def enqueue_youtube_download_task(self, request, url, video_id, filename):
        """
        为 YouTube 视频创建下载任务
        """
        # 1. 新建 task_id
        task_id = str(int(time.time() * 1000))

        # 2. 初始化任务状态
        with download_status_lock:
            download_status[task_id] = {
                "video_id": video_id, # youtube的video_id,例如q_sQUK418mM
                "title": filename,
                "url": url,
                "platform": "youtube",
                **_new_download_status(),
            }

        print(f"YouTube download task created: {task_id}, {filename}")

        # 3. 推送到后台队列
        download_queue.put(task_id)

        return JsonResponse({"success": True, "task_id": task_id})

    def enqueue_podcast_download_task(self, request, url, episode_id, filename):
        """
        为 Apple Podcast 音频创建下载任务
        """
        # 1. 新建 task_id
        task_id = str(int(time.time() * 1000))

        # 2. 初始化任务状态
        with download_status_lock:
            download_status[task_id] = {
                "episode_id": episode_id,  # Apple podcast的episode id
                "title": filename,
                "url": url,
                "platform": "apple_podcast",
                **_new_download_status(),
            }

        print(f"Apple Podcast download task created: {task_id}, {filename}")

        # 3. 推送到后台队列
        download_queue.put(task_id)

        return JsonResponse({"success": True, "task_id": task_id})

class DownloadStatusView(View):
    def get(self, request, task_id):
        task = download_status.get(int(task_id))
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)
        return JsonResponse({
            "status": task.status,
            "progress": task.progress,
            "video_id": task.video_id
        })

class AllDownloadStatusView(View):
    """
    GET /stream_media/status/all/
    返回 JSON: {
      "<task_id1>": { "stages": {...}, "finished": ..., "title": ..., ... },
      "<task_id2>": { ... },
      ...
    }
    """
    def get(self, request):
        # 强制把 defaultdict 转成普通 dict，避免序列化问题
        with download_status_lock:
            all_status = {tid: data for tid, data in download_status.items()}
        return JsonResponse(all_status)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class RetryDownloadTaskView(View):
    def post(self, request,task_id):
        old_id = task_id
        with download_status_lock:
            old = download_status.get(old_id)
            if not old:
                return HttpResponseBadRequest("Task not found")

            # 深拷贝旧状态，避免并发污染
            new_status = copy.deepcopy(old)
            # 重置各阶段
            new_status["finished"] = False
            new_status["stages"] = {
                "video":  "Queued",
                "audio": "Queued",
                "merge": "Queued",
                "convert": "Queued"
            }
            # 覆写回 download_status 同一个 key
            download_status[old_id] = new_status
        download_queue.put(old_id)
        return JsonResponse({"task_id": old_id,'message': 'Retry scheduled'})

@method_decorator(csrf_exempt, name="dispatch")
class DeleteDownloadTaskView(View):
    """
    处理 DELETE /stream_media/download/<str:task_id>/
    """
    def delete(self, request, task_id):
        with download_status_lock:
            if task_id not in download_status:
                return JsonResponse({'error': 'Task not found'}, status=404)

            try:
                download_queue.remove(task_id)
            except (ValueError, AttributeError):
                print("error")
                pass

            # 最终从状态表里删掉
            download_status.pop(task_id, None)
        return JsonResponse({'message': 'Download task deleted'})

    def post(self, request, *args, **kwargs):
        # 防止用户误用 POST
        return HttpResponseNotAllowed(['DELETE'])