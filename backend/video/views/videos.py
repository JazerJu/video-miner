# views/videos.py
from django.http import JsonResponse,HttpResponse,HttpResponseNotAllowed,HttpResponseNotFound,Http404,FileResponse,HttpRequest
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings  # 确保这个在顶部
from django.shortcuts import get_object_or_404,render
from django.urls import reverse
from .base import JsonView
from django.views import View
from ..models import Video, Category, Collection, VideoAttachment
from ..utils import calc_diff_time
from django.contrib.auth import get_user_model
from functools import wraps

User = get_user_model()

def requires_delete_permission(func):
    """Decorator to check if user has permission to delete videos"""
    @wraps(func)
    def wrapper(self, request, *args, **kwargs):
        # 检查用户是否已认证
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return JsonResponse({'success': False, 'error': 'Authentication required'}, status=401)
        
        # 检查用户是否为root或拥有高级权限
        if not (request.user.is_root or request.user.premium_authority):
            return JsonResponse({'success': False, 'error': 'Insufficient permissions. Only premium users can delete videos'}, status=403)
        
        return func(self, request, *args, **kwargs)
    return wrapper

def get_user_combined_hidden_categories(request):
    """Get combined hidden categories for the current user"""
    if hasattr(request, 'user') and request.user.is_authenticated:
        return request.user.get_combined_hidden_categories()
    
    # 对于未认证用户，检查hidden_categories参数
    hidden_category_ids = []
    if 'hidden_categories' in request.GET:
        try:
            hidden_categories_param = request.GET['hidden_categories']
            if hidden_categories_param:
                hidden_category_ids = [int(x.strip()) for x in hidden_categories_param.split(',') if x.strip()]
        except (ValueError, TypeError):
            hidden_category_ids = []
    
    return hidden_category_ids
import hashlib
import os
import json
import urllib
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.utils.decorators import method_decorator
import cv2
import subprocess
from PIL import Image

from ..services.audio_processing import (
    is_audio_file,
    get_media_path_info,
    has_waveform_peaks,
    detect_video_audio_format,
    extract_audio_from_video_file,
    is_hls_compatible,
    extract_hls_from_video_file,
    get_audio_file_for_transcription,
    get_transcription_audio_path,
    get_video_file_paths,
)

# 删除视频的缩略图文件  
def delete_video_thumbnail(video):
    """删除视频关联的缩略图文件"""
    if not video.thumbnail_url:
        return
    
    try:
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnail')
        thumbnail_path = os.path.join(thumbnail_dir, video.thumbnail_url)
        
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            print(f"Deleted thumbnail: {video.thumbnail_url}")
        else:
            print(f"[WARN] Thumbnail file not found: {thumbnail_path}")
    except Exception as e:
        print(f"[ERROR] Failed to delete thumbnail {video.thumbnail_url}: {e}")

def delete_all_related_files(video):
    """删除视频的所有相关文件"""
    deleted_files = []
    errors = []
    
    # 获取不含扩展名的基础文件名用于模式匹配
    base_filename = os.path.splitext(video.url)[0] if video.url else None
    video_id_str = str(video.id)
    
    # 1. 删除主视频/音频文件
    if video.url:
        try:
            directory_name, _ = get_media_path_info(video.url)
            save_dir = os.path.join(settings.MEDIA_ROOT, directory_name)
            file_path = os.path.join(save_dir, video.url)
            
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted_files.append(f"{directory_name}/{video.url}")
            else:
                print(f"[WARN] Main file not found: {file_path}")
        except Exception as e:
            errors.append(f"Main file deletion failed: {e}")
    
    # 2. 删除缩略图 
    if video.thumbnail_url:
        try:
            thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnail')
            thumbnail_path = os.path.join(thumbnail_dir, video.thumbnail_url)
            
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                deleted_files.append(f"thumbnail/{video.thumbnail_url}")
            else:
                print(f"[WARN] Thumbnail not found: {thumbnail_path}")
        except Exception as e:
            errors.append(f"Thumbnail deletion failed: {e}")
    
    # 3. 删除字幕文件
    if video.srt_path:
        try:
            srt_dir = os.path.join(settings.MEDIA_ROOT, 'saved_srt')
            srt_path = os.path.join(srt_dir, video.srt_path)
            
            if os.path.exists(srt_path):
                os.remove(srt_path)
                deleted_files.append(f"saved_srt/{video.srt_path}")
            else:
                print(f"[WARN] SRT file not found: {srt_path}")
        except Exception as e:
            errors.append(f"SRT file deletion failed: {e}")
    
    # 4. 删除翻译字幕文件
    if video.translated_srt_path:
        try:
            translated_srt_dir = os.path.join(settings.MEDIA_ROOT, 'saved_srt')
            translated_srt_path = os.path.join(translated_srt_dir, video.translated_srt_path)
            
            if os.path.exists(translated_srt_path):
                os.remove(translated_srt_path)
                deleted_files.append(f"saved_srt/{video.translated_srt_path}")
            else:
                print(f"[WARN] Translated SRT file not found: {translated_srt_path}")
        except Exception as e:
            errors.append(f"Translated SRT file deletion failed: {e}")
    
    # 5. 删除波形数据（基于视频文件名模式）
    if base_filename:
        try:
            waveform_dir = os.path.join(settings.MEDIA_ROOT, 'waveform_data')
            if os.path.exists(waveform_dir):
                # 查找匹配基础文件名的波形文件
                waveform_pattern = f"{base_filename}.json"
                waveform_path = os.path.join(waveform_dir, waveform_pattern)
                
                if os.path.exists(waveform_path):
                    os.remove(waveform_path)
                    deleted_files.append(f"waveform_data/{waveform_pattern}")
                else:
                    print(f"[WARN] Waveform file not found: {waveform_path}")
        except Exception as e:
            errors.append(f"Waveform file deletion failed: {e}")
    
    # 6. 删除saved_audio/中相同基础文件名的音频文件
    if base_filename:
        try:
            audio_dir = os.path.join(settings.MEDIA_ROOT, 'saved_audio')
            if os.path.exists(audio_dir):
                # 查找匹配基础文件名的音频文件
                audio_extensions = ['.mp3', '.m4a', '.aac', '.wav', '.flac', '.alac']
                for ext in audio_extensions:
                    audio_filename = f"{base_filename}{ext}"
                    audio_path = os.path.join(audio_dir, audio_filename)
                    
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                        deleted_files.append(f"saved_audio/{audio_filename}")
                        print(f"[INFO] Deleted audio file: {audio_filename}")
        except Exception as e:
            errors.append(f"Audio file deletion failed: {e}")
    
    # 7. 删除流视频文件（查找相同基础名称的文件）
    if base_filename:
        try:
            stream_dir = os.path.join(settings.MEDIA_ROOT, 'stream_video')
            if os.path.exists(stream_dir):
                # 查找stream_video中匹配基础文件名的任意文件
                for file in os.listdir(stream_dir):
                    if file.startswith(base_filename):
                        stream_path = os.path.join(stream_dir, file)
                        if os.path.isfile(stream_path):
                            os.remove(stream_path)
                            deleted_files.append(f"stream_video/{file}")
        except Exception as e:
            errors.append(f"Stream video deletion failed: {e}")
    
    # 8. 删除截图文件（查找包含视频ID的文件）
    try:
        screenshot_dir = os.path.join(settings.MEDIA_ROOT, 'screenshot')
        if os.path.exists(screenshot_dir):
            # 查找包含视频ID的截图文件
            for file in os.listdir(screenshot_dir):
                if video_id_str in file or (base_filename and base_filename in file):
                    screenshot_path = os.path.join(screenshot_dir, file)
                    if os.path.isfile(screenshot_path):
                        os.remove(screenshot_path)
                        deleted_files.append(f"screenshot/{file}")
    except Exception as e:
        errors.append(f"Screenshot deletion failed: {e}")
    
    # 9. 删除该视频的附件文件
    try:
        from ..models import VideoAttachment
        attachments = VideoAttachment.objects.filter(video=video)
        for attachment in attachments:
            try:
                if attachment.delete_file():  # 使用模型的delete_file方法
                    deleted_files.append(f"attachments/{attachment.file_path}")
                else:
                    print(f"[WARN] Attachment file not found: {attachment.file_path}")
            except Exception as e:
                errors.append(f"Attachment {attachment.id} deletion failed: {e}")
    except Exception as e:
        errors.append(f"Attachment query failed: {e}")
    
    # 记录结果
    if deleted_files:
        print(f"[INFO] Deleted {len(deleted_files)} files for video {video.id}: {deleted_files}")
    if errors:
        print(f"[ERROR] {len(errors)} deletion errors for video {video.id}: {errors}")
    
    return deleted_files, errors

# 记录视频的最后打开时间
def record_video_last_open(video_id):
    print("record video last open time")
    # 当触发watch_video这个函数时，自动记录视频的最后打开时间
    time_open=timezone.now()
    try:
        video = Video.objects.get(pk=video_id)
        video.last_modified = time_open
        video.save(update_fields=['last_modified'])
    except:
        return time_open

# 记录合集的最后打开时间
def record_collection_last_open(video_id):
    print("record collection last open time")
    time_open = timezone.now()
    try:
        video = Video.objects.get(pk=video_id)
        # 检查视频是否属于某个合集
        if video.collection:
            collection = video.collection
            collection.last_modified = time_open
            collection.save(update_fields=['last_modified'])
            print(f"Updated collection {collection.name} last_modified")
        else:
            print("Video is not in any collection (loose video)")
    except Video.DoesNotExist:
        print(f"Video with id {video_id} not found")
    except Exception as e:
        print(f"Error updating collection last_modified: {e}")
    return time_open

from collections import defaultdict
from django.db.models import Prefetch
from django.utils import timezone

# 获取完整的全部视频信息，提取 Folder --> Collection --> Video 的三级视频数据。
class VideoDataView(JsonView):
    # 需要补全三种情况：
    # 1. 有 Folder(Category) 且在 Collection 里的视频；
    # 2. 有 Folder 但不在 Collection 里的散装(loose)视频；
    # 3. 既没有 Folder 也没有 Collection 的“未归档”视频。
    # ------------ 辅助 JSON ------------
    def video_json(self, v):
        return {
            "id": v.id,
            "name": v.name,
            "thumbnail": f"img/{v.thumbnail_url}",
            "url": v.url,
            "length": v.video_length,
            "last_modified": calc_diff_time(v.last_modified or timezone.now()),
        }

    def collection_json(self, col):
        return {
            "id": col.id,
            "name": col.name,
            "thumbnail": f"img/{col.thumbnail_url}",
            "videos": [self.video_json(v) for v in col.videos.all()],
            "last_modified": calc_diff_time(col.last_modified or timezone.now()),
        }

    def category_json(self, cat):
        """cat.categories  =  该分类下 *不在任何 Collection* 的散装视频"""
        loose_videos = cat.categories.all()      # ← 注意 related_name
        return {
            "id": cat.id,
            "name": cat.name,
            "collections": [
                self.collection_json(c) for c in cat.collections.all()
            ],
            "loose_videos": [self.video_json(v) for v in loose_videos],
        }

    # ------------ 主入口 ------------
    def get(self, request):
        # 获取用户的组合隐藏分类ID列表（系统设置 + 用户自定义）
        hidden_category_ids = get_user_combined_hidden_categories(request)
        
        # ① 预加载：Category → Collection → Video（Collection 外的散装视频单独 Prefetch）
        # 过滤掉隐藏的分类
        cats_query = Category.objects.exclude(id__in=hidden_category_ids) if hidden_category_ids else Category.objects
        cats = (
            cats_query
            .prefetch_related(
                Prefetch(
                    "collections",                        # Folder → Collections
                    queryset=Collection.objects.prefetch_related("videos"),
                ),
                Prefetch(                                # Folder → "散装"Videos
                    "categories",
                    queryset=Video.objects.filter(collection__isnull=True),
                ),
            )
            .order_by("id")
        )

        payload = [self.category_json(cat) for cat in cats]

        # ② "未归档"——既没有 Folder 也没有 Collection
        # 过滤掉属于隐藏分类的未归档项目
        uncated_cols = (
            Collection.objects
            .filter(category__isnull=True)
            .prefetch_related("videos")
        )
        uncated_vids_query = Video.objects.filter(category__isnull=True, collection__isnull=True)
        if hidden_category_ids:
            # 排除属于隐藏分类的视频（如果视频的分类在隐藏列表中）
            uncated_vids = uncated_vids_query.exclude(category_id__in=hidden_category_ids)
        else:
            uncated_vids = uncated_vids_query

        if uncated_cols.exists() or uncated_vids.exists():
            payload.append({
                "id": 0,
                "name": "未归档",
                "collections": [self.collection_json(c) for c in uncated_cols],
                "loose_videos": [self.video_json(v) for v in uncated_vids],
            })
        # print(payload)
        return self.json_ok({"data": payload})


# 获取最近访问的视频列表，按last_modified属性，时间倒序排序，最多返回50个视频
class LastVideoDataView(JsonView):
    """
    获取最近访问的视频列表
    GET /video_last_data → 返回按last_modified时间倒序排序的最多50个视频
    返回格式与VideoDataView中的video_json相同，但不返回分类和Collection信息
    """
    
    def video_json(self, v):
        """
        视频信息JSON格式化 - 与VideoDataView保持一致
        但直接返回timestamp字符串用于前端排序
        """
        return {
            "id": v.id,
            "name": v.name,
            "thumbnail": f"img/{v.thumbnail_url}",
            "url": v.url,
            "length": v.video_length,
            "last_modified": calc_diff_time(v.last_modified if v.last_modified else timezone.now()),
            "description": v.description,
        }
    
    def get(self, request):
        """
        获取最近访问的视频
        按last_modified倒序排序，返回最多50个视频
        """
        try:
            # 获取用户的组合隐藏分类ID列表（系统设置 + 用户自定义）
            hidden_category_ids = get_user_combined_hidden_categories(request)
            
            # 查询所有视频，按last_modified倒序排序，取前50个
            # 过滤掉属于隐藏分类的视频
            recent_videos_query = Video.objects.all()
            if hidden_category_ids:
                recent_videos_query = recent_videos_query.exclude(category_id__in=hidden_category_ids)
            
            recent_videos = (
                recent_videos_query
                .order_by('-last_modified', '-id')  # 二级排序确保一致性
                [:50]  # 最多50个视频
            )
            
            # 转换为JSON格式
            videos_data = [self.video_json(video) for video in recent_videos]
            
            return self.json_ok({
                "success": True,
                "videos": videos_data,
                "count": len(videos_data)
            })
            
        except Exception as e:
            print(f"LastVideoDataView error: {str(e)}")
            return self.json_err(f'获取最近视频失败: {str(e)}', status=500)

# 通过视频文件名获取视频信息
class VideoInfoView(JsonView):
    """GET /videos/ → grouped list for the dashboard"""
    def get(self, request,filename):
        """
        通过视频文件名获取视频信息
        :param request: HTTP 请求对象
        :param filename: 视频文件名
        :return: JSON 响应，包含视频信息或错误信息
        """
        try:
            video = Video.objects.get(url=filename)
            # 根据文件扩展名获取正确的媒体路径
            directory_name, url_prefix = get_media_path_info(video.url)
            return self.json_ok({
                'id': video.id,
                'name': video.name,
                'url': f'/media/{url_prefix}/{video.url}',
                'thumbnailUrl': video.thumbnail_url,
                'description': video.description,
                'videoLength': video.video_length,
                'lastModified': calc_diff_time(video.last_modified),
                'rawLang': video.raw_lang  # 添加raw_lang字段
            })
        except Video.DoesNotExist:
            return self.json_err('Video not found', status=404)

@method_decorator(csrf_protect, name="dispatch")
class VideoActionView(View):
    def dispatch(self, request, *args, **kwargs):
        self.action = kwargs.pop('action', None)
        # print(self.action)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, video_id):
        if self.action == 'upload':
            return self.upload(request, video_id)
        elif self.action == 'delete':
            return self.delete(request, video_id)
        elif self.action == 'rename':
            return self.rename(request, video_id)
        elif self.action == 'rename_description':
            return self.rename_description(request, video_id)
        elif self.action == 'move_category': # 移动分类
            return self.move_category(request, video_id)
        elif self.action == 'move_to_collection': # 移动到合集
            return self.move_to_collection(request, video_id)
        elif self.action == 'update_thumbnail':
            return self.update_thumbnail(request, video_id)
        elif self.action == 'save_chapters':
            return self.save_chapters(request, video_id)
        elif self.action == 'load_chapters':
            return self.load_chapters(request, video_id)
        elif self.action == 'get_screenshot':
            return self.get_screenshot(request, video_id)
        elif self.action == 'save_notes':
            return self.save_notes(request, video_id)
        elif self.action == 'upload_note_image':
            return self.upload_note_image(request, video_id)
        elif self.action == 'upload_attachment':
            return self.upload_attachment(request, video_id)
        elif self.action == 'update_raw_lang':
            return self.update_raw_lang(request, video_id)
        elif self.action == 'extract_audio':
            return self.extract_audio(request, video_id)
        elif self.action == 'generate_waveform_peaks':
            return self.generate_waveform_peaks(request, video_id)
        # 其它动作不允许 POST
        return HttpResponseNotAllowed(['POST'])

    def get(self, request, video_id):
        if self.action == 'query':
            return self.query(request, video_id)
        elif self.action == 'watch':
            return self.watch(request, video_id)
        elif self.action == 'load_chapters':
            return self.load_chapters(request, video_id)
        elif self.action == 'get_screenshot':
            return self.get_screenshot(request, video_id)
        elif self.action == 'load_notes':
            return self.load_notes(request, video_id)
        elif self.action == 'list_attachments':
            return self.list_attachments(request, video_id)
        elif self.action == 'serve_attachment':
            return self.serve_attachment(request, video_id)
        elif self.action == 'collection':
            return self.get_video_collection(request, video_id)
        elif self.action == 'has_audio':
            return self.has_audio_file(request, video_id)
        elif self.action == 'has_waveform_peaks':
            return self.has_waveform_peaks(request, video_id)
        elif self.action == 'get_dimensions':
            return self.get_dimensions(request, video_id)

    def upload(self, request, video_id):
        # 检查是否有文件上传
        file = None
        is_audio = False
        
        if 'video_file' in request.FILES:
            file = request.FILES['video_file']
        elif 'audio_file' in request.FILES:
            file = request.FILES['audio_file']
            is_audio = True
        else:
            return JsonResponse({'error': 'No video or audio file provided'}, status=400)

        if not file.name:
            return JsonResponse({'error': 'No selected file'}, status=400)

        try:
            # 文件类型检查和处理
            file_extension = os.path.splitext(file.name)[1].lower()
            original_extension = file_extension
            
            # 支持的格式定义
            video_formats = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
            audio_formats = ['.mp3', '.m4a', '.aac', '.wav', '.flac', '.alac']
            browser_compatible_audio = ['.mp3', '.m4a', '.aac', '.wav']
            
            if not (file_extension in video_formats or file_extension in audio_formats):
                return JsonResponse({
                    'error': f'Unsupported file format: {file_extension}',
                    'supported_formats': video_formats + audio_formats
                }, status=400)

            # 根据文件类型决定保存目录
            if is_audio or file_extension in audio_formats:
                save_dir = os.path.join(settings.MEDIA_ROOT, 'saved_audio')
                is_audio = True
            else:
                save_dir = os.path.join(settings.MEDIA_ROOT, 'saved_video')
            
            os.makedirs(save_dir, exist_ok=True)

            # 计算文件的 MD5 值
            md5_hash = hashlib.md5()
            for chunk in file.chunks():
                md5_hash.update(chunk)
            md5_value = md5_hash.hexdigest()

            # 如果是 FLAC，需要转换为浏览器兼容格式
            needs_conversion = is_audio and file_extension == '.flac'
            final_extension = '.m4a' if needs_conversion else file_extension
            
            # 使用 MD5 值作为文件名
            filename = f"{md5_value}{final_extension}"
            temp_file_path = os.path.join(save_dir, f"temp_{md5_value}{original_extension}")
            final_file_path = os.path.join(save_dir, filename)
            print("filename",filename)
            # 检查是否已经存在相同的文件
            existing_files = os.listdir(save_dir)
            file_exists = any(md5_value in fname for fname in existing_files)
            if file_exists:
                return JsonResponse(
                    {'error': 'File already exists', 'file_path': final_file_path},
                    status=409,
                )

            # 保存临时文件
            save_path = temp_file_path if needs_conversion else final_file_path
            with open(save_path, 'wb+') as destination:
                for chunk in file.chunks():
                    destination.write(chunk)
            # 音频部分处理
            # 如果是 FLAC，使用 FFmpeg 转换为 M4A (AAC)
            if needs_conversion:
                print(f"Converting FLAC to M4A: {temp_file_path} -> {final_file_path}")
                convert_cmd = [
                    'ffmpeg', '-i', temp_file_path,
                    '-c:a', 'aac',  # 使用AAC编码器
                    '-b:a', '256k',  # 高质量音频比特率
                    '-y',  # 覆盖输出文件
                    final_file_path
                ]
                
                try:
                    result = subprocess.run(convert_cmd, capture_output=True, text=True, check=True)
                    print(f"Conversion successful: {result.returncode}")
                    # 删除临时文件
                    os.remove(temp_file_path)
                except subprocess.CalledProcessError as e:
                    print(f"FFmpeg conversion failed: {e}")
                    # 如果转换失败，回退到原文件
                    os.rename(temp_file_path, final_file_path.replace('.m4a', '.flac'))
                    filename = f"{md5_value}.flac"
                    final_file_path = os.path.join(save_dir, filename)

            # # 检查视频是否需要转换为AV1格式
            conversion_performed = False
            # if not is_audio:
            #     try:
            #         from utils.video_converter import should_convert_video, convert_video_to_av1
                    
            #         if should_convert_video(final_file_path):
            #             print(f"Detected H.265/HEVC video, converting to AV1: {filename}")
                        
            #             # 创建AV1输出路径
            #             av1_temp_path = final_file_path.replace(final_extension, '_av1.mp4')
                        
            #             # 定义进度回调函数
            #             def conversion_progress(status):
            #                 print(f"AV1 conversion progress: {status}")
                        
            #             # 执行AV1转换（使用超快模式）
            #             if convert_video_to_av1(final_file_path, av1_temp_path, conversion_progress, ultra_fast=True):
            #                 # 转换成功，替换原文件
            #                 os.remove(final_file_path)  # 删除原H.265文件
            #                 os.rename(av1_temp_path, final_file_path.replace(final_extension, '.mp4'))
                            
            #                 # 更新文件名和路径信息
            #                 filename = f"{md5_value}.mp4"
            #                 final_file_path = os.path.join(save_dir, filename)
            #                 conversion_performed = True
            #                 print(f"Successfully converted to AV1: {filename}")
            #             else:
            #                 # 转换失败，保留原文件
            #                 if os.path.exists(av1_temp_path):
            #                     os.remove(av1_temp_path)
            #                 print(f"AV1 conversion failed, keeping original format: {filename}")
            #         else:
            #             print(f"Video format is browser-compatible, no conversion needed: {filename}")
                        
            #     except Exception as e:
            #         print(f"Error during AV1 conversion check: {str(e)}")
            #         # 转换出错时继续使用原文件
            #         conversion_performed = False
            
            # 获取媒体时长
            from ..utils import get_video_duration, format_duration
            duration_seconds = get_video_duration(final_file_path)
            formatted_duration = None
            if duration_seconds is not None:
                formatted_duration = format_duration(duration_seconds)
                print(f"Media duration: {formatted_duration}")
            else:
                print("Could not get media duration")

            # 为视频自动生成缩略图（音频跳过）
            thumbnail_filename = ''
            if not is_audio:
                try:
                    thumbnail_filename = self._auto_generate_thumbnail(final_file_path, md5_value)
                    print(f"[Auto-thumbnail] Generated: {thumbnail_filename}")
                except Exception as e:
                    print(f"[Auto-thumbnail] Failed to generate thumbnail: {e}")

            # 创建新的 Video 记录（音频也存储在 Video 表中）
            new_video = Video.objects.create(
                name=file.name,
                url=filename,
                thumbnail_url=thumbnail_filename,
                video_length=formatted_duration,
                category=None,
            )

            # 自动生成波形数据（无论是音频还是视频文件）
            try:
                from utils.audio.waveform_generator import get_waveform_for_file
                print(f"[Auto-generating waveform] Starting waveform generation for: {filename}")
                waveform_result = get_waveform_for_file(filename)
                if waveform_result:
                    print(f"[Auto-generating waveform] Successfully generated waveform for: {filename}")
                else:
                    print(f"[Auto-generating waveform] Failed to generate waveform for: {filename}")
            except Exception as e:
                print(f"[Auto-generating waveform] Error generating waveform for {filename}: {str(e)}")

            return JsonResponse({
                'video_id': new_video.id,
                'file_path': final_file_path,
                'file_name': file.name,
                'final_format': '.mp4' if conversion_performed else final_extension,
                'was_converted': needs_conversion or conversion_performed,
                'conversion_type': 'FLAC→M4A' if needs_conversion else ('H.265→AV1' if conversion_performed else 'None'),
                'is_audio': is_audio,
                'video_length': formatted_duration,
                'message': 'Upload successful',
                'file_exists': file_exists,
                'success': True,
            }, status=201)

        except Exception as e:
            print(f"Upload error: {str(e)}")
            return JsonResponse({
                'error': f'File upload failed: {str(e)}',
                'message': 'Upload failed',
                'success': False
            }, status=500)
    
    def rename(self,request,video_id):
        try:
            data = json.loads(request.body)
            video_id = data.get('videoId')
            new_name = data.get('newName')
        except json.JSONDecodeError:
            return JsonResponse(
                {'success': False, 'message': 'Invalid JSON'},
                status=400
            )

        if not video_id or not new_name:
            return JsonResponse(
                {'success': False, 'message': 'Invalid data'},
                status=400
            )

        try:
            video = Video.objects.get(pk=video_id)
        except ObjectDoesNotExist:
            return JsonResponse(
                {'success': False, 'message': 'Video not found'},
                status=404
            )

        try:
            video.name = new_name
            video.save()
        except Exception as e:
            return JsonResponse(
                {'success': False, 'message': f'Database error: {str(e)}'},
                status=500
            )

        return JsonResponse(
            {'success': True, 'message': 'Video renamed successfully'},
            status=200
        )
    
    def query(self, request, video_id):
        try:
            v = Video.objects.get(pk=video_id)
        except Video.DoesNotExist:
            return self.json_err('Video not found', status=404)
        return self.json_ok({'title': v.name, 'description': v.description})
    @requires_delete_permission
    def delete(self,request,video_id):
        try:
            video = Video.objects.get(pk=video_id)
        except ObjectDoesNotExist:
            return JsonResponse(
                {'success': False, 'message': 'Video not found'},
                status=404
            )
        
        # 删除所有相关文件（视频、音频、缩略图、字幕、波形、截图、附件等）
        deleted_files, errors = delete_all_related_files(video)
        
        # 删除数据库记录
        video.delete()
        
        # 准备包含删除摘要的响应
        message = f'Video deleted successfully. Removed {len(deleted_files)} related files.'
        if errors:
            message += f' {len(errors)} files had deletion errors (see logs).'
        
        return JsonResponse(
            {
                'success': True, 
                'message': message,
                'deleted_files': deleted_files,
                'errors': errors if errors else None
            },
            status=200
        )
    
    def rename_description(self,request,video_id):
        try:
            data = json.loads(request.body)
            new_description = data.get('description')
            
            if not video_id or not new_description:
                return JsonResponse(
                    {'success': False, 'error': 'Missing video_id or description'},
                    status=400
                )
                
            video = Video.objects.get(pk=video_id)
            print(video,new_description)
            video.description = new_description
            video.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Description updated successfully'
            })
            
        except json.JSONDecodeError:
            return JsonResponse(
                {'success': False, 'error': 'Invalid JSON format'},
                status=400
            )
        except Video.DoesNotExist:
            return JsonResponse(
                {'success': False, 'error': 'Video not found'},
                status=404
            )
        except Exception as e:
            return JsonResponse(
                {'success': False, 'error': str(e)},
                status=500
            )
    def delete_not_cited_videos(self,request):
        try:
            # 查询所有视频
            videos = Video.query.all()
            
            # 获取所有媒体文件链接
            media_urls = [video.url.split("/")[-1] for video in videos]
            print(f"Database media URLs: {media_urls}")
            
            # 清理两个目录：saved_video 和 saved_audio
            media_dirs = [
                ('media/saved_video', 'video files'),
                ('media/saved_audio', 'audio files')
            ]
            
            for saved_dir, file_type in media_dirs:
                if not os.path.exists(saved_dir):
                    print(f"Directory {saved_dir} does not exist, skipping")
                    continue
                    
                saved_files = os.listdir(saved_dir)
                print(f"Found {len(saved_files)} {file_type} in {saved_dir}")

                # 遍历所有保存的媒体文件
                for file_name in saved_files:
                    file_path = os.path.join(saved_dir, file_name)
                    
                    # 如果文件不在数据库链接中，则删除
                    if file_name not in media_urls:
                        # 删除对应的媒体文件
                        os.remove(file_path)
                        print(f"Deleted {file_type.rstrip('s')}: {file_path}")
                    
                    # 删除对应的缩略图文件 (提取MD5值)
                    try:
                        md5_value = os.path.splitext(file_name)[0]  # 去掉.mp4扩展名
                        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnail')
                        
                        # 查找可能的缩略图文件 (支持多种扩展名)
                        for ext in ['jpg', 'jpeg', 'png', 'webp']:
                            thumbnail_path = os.path.join(thumbnail_dir, f"{md5_value}.{ext}")
                            if os.path.exists(thumbnail_path):
                                os.remove(thumbnail_path)
                                print(f"Deleted thumbnail: {thumbnail_path}")
                                break
                    except Exception as e:
                        print(f"[ERROR] Failed to delete thumbnail for {file_name}: {e}")
                else:
                    print(f"Kept: {file_path}")
            return JsonResponse({"message":"结束未引用视频删除"})
        except Exception as e:
            print(f"An error occurred: {e}")
    
    def watch(self, request, subpath):
        # print("watch video")
    
        # 自动解码 URL 编码的路径参数
        decoded_path = urllib.parse.unquote(subpath)
        # print(subpath,decoded_path)
        absolute_path=decoded_path
        # 数据库查询 (Django ORM 方式)
        video = Video.objects.filter(url=decoded_path).first()
        if not video:
            return HttpResponseNotFound("Video not found in database")
        
        # 检查文件存在性 - 根据文件类型选择正确的目录
        directory_name, _ = get_media_path_info(absolute_path)
        file_path = os.path.join(settings.MEDIA_ROOT, directory_name, absolute_path)
        if not os.path.exists(file_path):
            raise Http404("Media file not found")
        
        # 构建媒体文件 URL (使用 Django URL 反向解析)
        # 获取用于URL构建的正确媒体类型
        _, url_prefix = get_media_path_info(absolute_path)
        video_path = request.build_absolute_uri(
            reverse('video:serve_media', args=[url_prefix, absolute_path])
        )
        # print(video_path)
        
        return render(request, 'video.html', {
            'video_path': video_path,
            'video_id': video.id
        })
    
    def update_thumbnail(self,request,video_id):
        """
        接受前端上传的视频缩略图文件，并保存到指定目录。
        目前仅支持POST请求。
        """
        if request.method != 'POST':
            return JsonResponse({'error': 'Method not allowed'}, status=405)

        if 'thumbnail_file' not in request.FILES:
            return JsonResponse({'error': 'No video file part'}, status=400)

        file = request.FILES['thumbnail_file']
        if not file.name:
            return JsonResponse({'error': 'No selected file'}, status=400)
        video = Video.objects.get(pk=video_id)
        if not video:
            return JsonResponse({'error': 'Video not found'}, status=404)
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnail')
        # 使用视频url作为缩略图文件名，防止重复
        url = os.path.splitext(os.path.basename(video.url))[0]  # 获取文件名，不包含扩展名
        thumbnail_filename = f"{url}.jpg"
        thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
        # 保存缩略图文件
        with open(thumbnail_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)
        # 更新视频模型的缩略图字段
        video.thumbnail_url = thumbnail_filename
        video.last_modified = timezone.now()  # 更新最后修改时间
        video.save()

        return JsonResponse({'success': True,'thumbnail_url':thumbnail_filename}, status=200)

    def move_category(self, request, video_id):
        """
        POST /videos/move_category/<video_id>  →  将视频归入指定分类  
        请求体 JSON 允许两种方式：
            {"categoryId": 3}                     # 用分类 id
            {"categoryName": "Travel Vlog"}       # 或用分类名（不区分大小写）
            {"categoryId": null}                  # 设为 None → 变成“未分类”
        """
        print("=== RAW BODY ===", request.body)          # bytes 形式
        print("=== AS TEXT ===", request.body.decode('utf‑8', 'ignore'))

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        # ------- 1. 取得目标分类（或 None） -------
        cat_id   = data.get("categoryId")
        cat_name = data.get("categoryName")

        if cat_id is None and not cat_name:           # 同时为空 → 语义错误
            return JsonResponse({'success': False, 'error': 'categoryId 或 categoryName 必须至少提供一个'},
                                status=400)

        if cat_id is None and cat_name is None:
            target_category = None                    # {"categoryId": null}
        elif cat_id is not None:
            target_category = get_object_or_404(Category, pk=cat_id)
        else:                                         # 通过名称查找（忽略大小写）
            target_category = get_object_or_404(Category, name__iexact=cat_name)

        # ------- 2. 获取并更新视频 -------
        video = get_object_or_404(Video, pk=video_id)

        # 若分类未变化可直接返回
        if video.category_id == (target_category.id if target_category else None):
            return JsonResponse({'success': True, 'message': '分类未改变'}, status=200)

        video.category = target_category
        
        # 检查当前合集是否属于目标分类
        if video.collection:
            # 清除合集如果：
            # 1. 移动到未分类（target_category为None）且合集有分类
            # 2. 合集属于与目标不同的分类
            # 3. 合集没有分类但要移动到特定分类
            if ((target_category is None and video.collection.category_id is not None) or
                (target_category is not None and video.collection.category_id != target_category.id)):
                video.collection = None
        
        video.last_modified = timezone.now()          # 保留一致的更新时间策略
        video.save(update_fields=["category", "collection", "last_modified"])

        return JsonResponse({
            'success': True,
            'message': f'视频已移动到分类 {target_category.name if target_category else "未分类"}',
            'videoId': video.id,
            'categoryId': target_category.id if target_category else None,
        }, status=200)
    
    def move_to_collection(self, request, video_id):
        """
        POST /videos/move_to_collection/<video_id>  →  将视频归入指定合集
        请求体 JSON:
            {"collectionId": 3}                     # 用合集 id
            {"collectionId": null}                  # 设为 None → 变成“未归档”
        """
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        # ------- 1. 取得目标合集（或 None） -------
        collection_id = data.get("collectionId")

        if collection_id is None:
            target_collection = None                    # {"collectionId": null}
        elif collection_id is not None:
            try:
                target_collection = get_object_or_404(Collection, pk=collection_id)
            except:
                return JsonResponse({'success': False, 'error': 'Collection not found'}, status=404)
        else:
            target_collection = None

        # ------- 2. 获取并更新视频 -------
        video = get_object_or_404(Video, pk=video_id)

        # 若合集未变化可直接返回
        if video.collection_id == (target_collection.id if target_collection else None):
            return JsonResponse({'success': True, 'message': '合集未改变'}, status=200)

        # ------- 3. 更新视频的合集和分类 -------
        video.collection = target_collection
        
        # 如果目标合集存在且有分类，将视频的分类设置为与合集相同的分类
        if target_collection and target_collection.category:
            video.category = target_collection.category
        # 如果目标合集不存在，不改变视频的分类
        
        video.last_modified = timezone.now()          # 保留一致的更新时间策略
        video.save(update_fields=["collection", "category", "last_modified"])

        return JsonResponse({
            'success': True,
            'message': f'视频已移动到合集 {target_collection.name if target_collection else "未归档"}',
            'videoId': video.id,
            'collectionId': target_collection.id if target_collection else None,
        }, status=200)

    def save_chapters(self, request, video_id):
        """
        保存视频章节信息
        POST /videos/save_chapters/<video_id>
        请求体 JSON:
        {
            "chapters": [
                {
                    "id": "1",
                    "title": "Chapter 1",
                    "startTime": 0,
                    "endTime": 60,
                    "thumbnail": "screenshot_url"
                }
            ]
        }
        """
        try:
            data = json.loads(request.body)
            chapters = data.get('chapters', [])
            
            video = get_object_or_404(Video, pk=video_id)
            video.chapters = chapters
            video.last_modified = timezone.now()
            video.save(update_fields=['chapters', 'last_modified'])
            
            return JsonResponse({
                'success': True,
                'message': 'Chapters saved successfully',
                'chapters': chapters
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def load_chapters(self, request, video_id):
        """
        加载视频章节信息
        GET /videos/load_chapters/<video_id>
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            record_video_last_open(video_id)  # 记录视频最后打开时间
            record_collection_last_open(video_id)  # 记录合集最后打开时间
            chapters = video.chapters or []
            
            return JsonResponse({
                'success': True,
                'chapters': chapters
            }, status=200)
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def get_screenshot(self, request, video_id):
        """
        获取视频指定时间点的截图
        POST /videos/get_screenshot/<video_id>
        请求体 JSON:
        {
            "timestamp": 30,  // 秒
            "chapters": [...]  // 可选：批量获取多个章节的截图
        }
        """
        try:
            data = json.loads(request.body)
            video = get_object_or_404(Video, pk=video_id)
            
            # 创建截图目录
            screenshot_dir = os.path.join(settings.MEDIA_ROOT, 'screenshot')
            os.makedirs(screenshot_dir, exist_ok=True)
            
            # 媒体文件路径 - 根据文件类型选择正确的目录
            directory_name, _ = get_media_path_info(video.url)
            video_path = os.path.join(settings.MEDIA_ROOT, directory_name, video.url)
            
            if not os.path.exists(video_path):
                return JsonResponse({'success': False, 'error': 'Video file not found'}, status=404)
            
            # 批量处理章节截图
            if 'chapters' in data:
                chapters = data['chapters']
                results = []
                
                for chapter in chapters:
                    timestamp = chapter.get('startTime', 0)
                    chapter_id = chapter.get('id', '')
                    
                    # 生成截图文件名：视频ID_章节ID_时间戳.jpg
                    screenshot_filename = f"{video_id}_{chapter_id}_{timestamp}.jpg"
                    screenshot_path = os.path.join(screenshot_dir, screenshot_filename)
                    
                    # 使用FFmpeg生成截图
                    success = self._generate_screenshot_ffmpeg(video_path, timestamp, screenshot_path)
                    
                    if success:
                        screenshot_url = f"/media/screenshot/{screenshot_filename}"
                        print(f"Screenshot generated successfully: {screenshot_url}")
                        results.append({
                            'chapterId': chapter_id,
                            'timestamp': timestamp,
                            'screenshot': screenshot_url
                        })
                    else:
                        print(f"Failed to generate screenshot for chapter {chapter_id} at {timestamp}s")
                        results.append({
                            'chapterId': chapter_id,
                            'timestamp': timestamp,
                            'error': 'Failed to generate screenshot'
                        })
                
                return JsonResponse({
                    'success': True,
                    'screenshots': results
                }, status=200)
            
            # 单个截图
            else:
                timestamp = data.get('timestamp', 0)
                screenshot_filename = f"{video_id}_{timestamp}.jpg"
                screenshot_path = os.path.join(screenshot_dir, screenshot_filename)
                
                success = self._generate_screenshot_ffmpeg(video_path, timestamp, screenshot_path)
                
                if success:
                    return JsonResponse({
                        'success': True,
                        'screenshot': f"/media/screenshot/{screenshot_filename}"
                    }, status=200)
                else:
                    return JsonResponse({'success': False, 'error': 'Failed to generate screenshot'}, status=500)
                    
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def _auto_generate_thumbnail(self, video_path, md5_value):
        try:
            thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnail')
            os.makedirs(thumbnail_dir, exist_ok=True)
            thumbnail_filename = f"{md5_value}.jpg"
            thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)

            from ..utils import get_video_duration
            duration = get_video_duration(video_path)
            extract_time = max(0.5, duration * 0.1) if duration and duration > 0 else 0.5

            cmd = [
                'ffmpeg',
                '-ss', str(extract_time),
                '-i', video_path,
                '-frames:v', '1',
                '-vf', 'scale=480:-2',
                '-q:v', '3',
                '-y',
                thumbnail_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, stderr=subprocess.PIPE)

            if result.returncode == 0 and os.path.exists(thumbnail_path):
                return thumbnail_filename
            else:
                return ''
        except Exception as e:
            print(f"[Auto-thumbnail] {e}")
            return ''

    def _generate_screenshot_ffmpeg(self, video_path, timestamp, output_path):
        try:
            cmd = [
                'ffmpeg',
                '-ss', str(timestamp),
                '-i', video_path,
                '-frames:v', '1',
                '-q:v', '2',
                '-y',
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and os.path.exists(output_path):
                return True
            else:
                print(f"FFmpeg error: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print("FFmpeg timeout")
            return False
        except Exception as e:
            print(f"Screenshot generation error: {e}")
            return False

    def save_notes(self, request, video_id):
        """
        保存视频笔记
        POST /videos/save_notes/<video_id>
        请求体 JSON:
        {
            "notes": "markdown content"
        }
        """
        try:
            data = json.loads(request.body)
            notes = data.get('notes', '')
            
            # Validate notes length (8000 characters max)
            if len(notes) > 8000:
                return JsonResponse({
                    'success': False, 
                    'error': 'Notes exceed maximum length of 8000 characters'
                }, status=400)
            
            video = get_object_or_404(Video, pk=video_id)
            video.notes = notes
            video.last_modified = timezone.now()
            video.save(update_fields=['notes', 'last_modified'])
            
            return JsonResponse({
                'success': True,
                'message': 'Notes saved successfully',
                'notes': notes
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def load_notes(self, request, video_id):
        """
        加载视频笔记
        GET /videos/load_notes/<video_id>
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            notes = video.notes or ''
            
            return JsonResponse({
                'success': True,
                'notes': notes
            }, status=200)
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    def upload_note_image(self, request, video_id):
        """
        上传笔记中的图片 (使用新的VideoAttachment模型)
        POST /videos/upload_note_image/<video_id>
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            
            if 'image' not in request.FILES:
                return JsonResponse({'success': False, 'error': 'No image file provided'}, status=400)

            file = request.FILES['image']
            if not file.name:
                return JsonResponse({'success': False, 'error': 'No selected file'}, status=400)

            # Validate file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
            if file.content_type not in allowed_types:
                return JsonResponse({
                    'success': False, 
                    'error': 'Invalid file type. Only JPEG, PNG, GIF, and WebP are allowed.'
                }, status=400)

            # Validate file size (10MB max)
            max_size = 10 * 1024 * 1024  # 10MB
            if file.size > max_size:
                return JsonResponse({
                    'success': False, 
                    'error': 'File size too large. Maximum size is 10MB.'
                }, status=400)

            # Create attachment directory
            attachment_dir = os.path.join(settings.MEDIA_ROOT, 'attachments')
            os.makedirs(attachment_dir, exist_ok=True)

            # Generate filename with timestamp
            timestamp = int(timezone.now().timestamp() * 1000)  # milliseconds
            file_extension = os.path.splitext(file.name)[1] or '.jpg'
            filename = f"VidGo_{video_id}_{timestamp}{file_extension}"
            relative_path = f"attachments/{filename}"
            full_path = os.path.join(attachment_dir, filename)

            # Save file
            with open(full_path, 'wb+') as destination:
                for chunk in file.chunks():
                    destination.write(chunk)

            # Create VideoAttachment record
            attachment = VideoAttachment.objects.create(
                video=video,
                filename=filename,
                original_name=file.name,
                file_path=relative_path,
                file_type=file.content_type,
                file_size=file.size,
                context_type='notes',
                context_id='',  # Empty for notes
                alt_text=file.name  # Default alt text to filename
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Image uploaded successfully',
                'attachmentId': attachment.id,
                'imageUrl': attachment.url,
                'filename': filename,
                'originalName': file.name
            }, status=200)

        except Exception as e:
            # Clean up file if attachment creation failed
            if 'full_path' in locals() and os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except:
                    pass
            
            return JsonResponse({
                'success': False, 
                'error': f'Image upload failed: {str(e)}'
            }, status=500)

    def upload_attachment(self, request, video_id):
        """
        通用附件上传端点 (支持notes和mindmap)
        POST /videos/upload_attachment/<video_id>
        Form data:
        - image: 文件
        - context_type: 'notes' | 'mindmap'
        - context_id: mindmap节点ID (如果是mindmap类型)
        - alt_text: 替代文本
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            
            if 'image' not in request.FILES:
                return JsonResponse({'success': False, 'error': 'No image file provided'}, status=400)

            file = request.FILES['image']
            if not file.name:
                return JsonResponse({'success': False, 'error': 'No selected file'}, status=400)
            
            # Get context information
            context_type = request.POST.get('context_type', 'notes')
            context_id = request.POST.get('context_id', '')
            alt_text = request.POST.get('alt_text', file.name)
            
            # Validate context_type
            if context_type not in ['notes', 'mindmap']:
                return JsonResponse({
                    'success': False, 
                    'error': 'Invalid context_type. Must be "notes" or "mindmap".'
                }, status=400)

            # Validate file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
            if file.content_type not in allowed_types:
                return JsonResponse({
                    'success': False, 
                    'error': 'Invalid file type. Only JPEG, PNG, GIF, and WebP are allowed.'
                }, status=400)

            # Validate file size (10MB max)
            max_size = 10 * 1024 * 1024  # 10MB
            if file.size > max_size:
                return JsonResponse({
                    'success': False, 
                    'error': 'File size too large. Maximum size is 10MB.'
                }, status=400)

            # Create attachment directory
            attachment_dir = os.path.join(settings.MEDIA_ROOT, 'attachments')
            os.makedirs(attachment_dir, exist_ok=True)

            # Generate filename with timestamp
            timestamp = int(timezone.now().timestamp() * 1000)  # milliseconds
            file_extension = os.path.splitext(file.name)[1] or '.jpg'
            filename = f"VidGo_{video_id}_{context_type}_{timestamp}{file_extension}"
            relative_path = f"attachments/{filename}"
            full_path = os.path.join(attachment_dir, filename)

            # Save file
            with open(full_path, 'wb+') as destination:
                for chunk in file.chunks():
                    destination.write(chunk)

            # Create VideoAttachment record
            attachment = VideoAttachment.objects.create(
                video=video,
                filename=filename,
                original_name=file.name,
                file_path=relative_path,
                file_type=file.content_type,
                file_size=file.size,
                context_type=context_type,
                context_id=context_id,
                alt_text=alt_text
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Attachment uploaded successfully',
                'attachment': {
                    'id': attachment.id,
                    'url': attachment.url,
                    'filename': filename,
                    'originalName': file.name,
                    'fileType': file.content_type,
                    'fileSize': file.size,
                    'contextType': context_type,
                    'contextId': context_id,
                    'altText': alt_text,
                    'uploadTime': attachment.upload_time.isoformat()
                }
            }, status=200)

        except Exception as e:
            # Clean up file if attachment creation failed
            if 'full_path' in locals() and os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except:
                    pass
            
            return JsonResponse({
                'success': False, 
                'error': f'Attachment upload failed: {str(e)}'
            }, status=500)

    def list_attachments(self, request, video_id):
        """
        列出视频的所有附件
        GET /videos/list_attachments/<video_id>?context_type=notes|mindmap
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            
            # Optional filter by context_type
            context_type = request.GET.get('context_type')
            attachments = video.attachments.filter(is_active=True)
            
            if context_type:
                if context_type not in ['notes', 'mindmap']:
                    return JsonResponse({
                        'success': False, 
                        'error': 'Invalid context_type. Must be "notes" or "mindmap".'
                    }, status=400)
                attachments = attachments.filter(context_type=context_type)
            
            # Serialize attachments
            attachment_list = []
            for attachment in attachments:
                attachment_list.append({
                    'id': attachment.id,
                    'url': attachment.url,
                    'filename': attachment.filename,
                    'originalName': attachment.original_name,
                    'fileType': attachment.file_type,
                    'fileSize': attachment.file_size,
                    'contextType': attachment.context_type,
                    'contextId': attachment.context_id,
                    'altText': attachment.alt_text,
                    'uploadTime': attachment.upload_time.isoformat()
                })
            
            return JsonResponse({
                'success': True,
                'attachments': attachment_list,
                'count': len(attachment_list)
            }, status=200)
            
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'error': str(e)
            }, status=500)

    def serve_attachment(self, request, video_id):
        """
        通过VideoAttachment模型安全地提供附件访问
        GET /videos/serve_attachment/<video_id>?attachment_id=123
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            attachment_id = request.GET.get('attachment_id')
            
            if not attachment_id:
                return JsonResponse({
                    'success': False, 
                    'error': 'attachment_id parameter is required'
                }, status=400)
            
            # Get attachment and verify it belongs to this video
            attachment = get_object_or_404(VideoAttachment, id=attachment_id, video=video, is_active=True)
            
            # Build full file path
            full_path = os.path.join(settings.MEDIA_ROOT, attachment.file_path)
            
            if not os.path.exists(full_path):
                return JsonResponse({
                    'success': False, 
                    'error': 'Attachment file not found'
                }, status=404)
            
            # Return file as response
            return FileResponse(
                open(full_path, 'rb'),
                content_type=attachment.file_type,
                filename=attachment.original_name
            )
            
        except VideoAttachment.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'error': 'Attachment not found'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'error': str(e)
            }, status=500)

    def update_raw_lang(self, request, video_id):
        """
        更新视频的原始语言
        POST /videos/update_raw_lang/<video_id>
        请求体 JSON:
        {
            "raw_lang": "zh" | "en" | "jp"
        }
        """
        try:
            data = json.loads(request.body)
            raw_lang = data.get('raw_lang')
            
            # Validate raw_lang
            if raw_lang not in ['zh', 'en', 'jp']:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid raw_lang. Must be zh, en, or jp.'
                }, status=400)
            
            video = get_object_or_404(Video, pk=video_id)
            video.raw_lang = raw_lang
            video.last_modified = timezone.now()
            video.save(update_fields=['raw_lang', 'last_modified'])
            
            return JsonResponse({
                'success': True,
                'message': 'Video raw_lang updated successfully',
                'raw_lang': raw_lang
            }, status=200)
            
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    def get_video_collection(self, request, video_id):
        """
        获取包含指定视频的合集信息
        GET /video/collection/<video_id>
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            
            if not video.collection:
                return JsonResponse({
                    'success': False,
                    'message': 'Video is not in any collection'
                }, status=404)
            
            collection = video.collection
            
            return JsonResponse({
                'success': True,
                'id': collection.id,
                'name': collection.name,
                'thumbnail': f"img/{collection.thumbnail_url}" if collection.thumbnail_url else "",
                'type': 'collection',
                'last_modified': calc_diff_time(collection.last_modified or timezone.now())
            }, status=200)
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

    def extract_audio(self, request, video_id):
        """
        从saved_video中的视频文件提取音频到saved_audio目录
        POST /video/extract_audio/<video_id>
        请求体 JSON (可选):
        {
            "quality": "192k",  // 音频质量，默认192k
            "format": "mp3"     // 输出格式，默认mp3
        }
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            
            # 检查是否为音频文件（音频文件不需要提取）
            if is_audio_file(video.url):
                return JsonResponse({
                    'success': False,
                    'error': 'This is already an audio file'
                }, status=400)
            
            # 获取请求参数
            data = {}
            if request.body:
                try:
                    data = json.loads(request.body)
                except json.JSONDecodeError:
                    pass
            
            audio_quality = data.get('quality', '192k')
            audio_format = data.get('format', 'mp3')
            
            # 构建文件路径
            video_dir = os.path.join(settings.MEDIA_ROOT, 'saved_video')
            audio_dir = os.path.join(settings.MEDIA_ROOT, 'saved_audio')
            
            video_path = os.path.join(video_dir, video.url)
            
            # 检查视频文件是否存在
            if not os.path.exists(video_path):
                return JsonResponse({
                    'success': False,
                    'error': 'Video file not found'
                }, status=404)
            
            # 创建音频目录
            os.makedirs(audio_dir, exist_ok=True)
            
            # 生成音频文件名（使用相同的MD5命名，但扩展名改为音频格式）
            video_name_without_ext = os.path.splitext(video.url)[0]
            audio_filename = f"{video_name_without_ext}.{audio_format}"
            audio_path = os.path.join(audio_dir, audio_filename)
            
            # 检查音频文件是否已经存在
            if os.path.exists(audio_path):
                return JsonResponse({
                    'success': False,
                    'error': 'Audio file already exists',
                    'audio_path': f"/media/audio/{audio_filename}"
                }, status=409)
            
            # 使用FFmpeg提取音频
            # 根据格式选择合适的编码器
            if audio_format == 'mp3':
                audio_codec = 'mp3'
            elif audio_format == 'alac':
                audio_codec = 'alac'
            elif audio_format == 'flac':
                audio_codec = 'flac'
            elif audio_format == 'wav':
                audio_codec = 'pcm_s16le'
            else:  # m4a, aac
                audio_codec = 'aac'
            
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', video_path,
                '-vn',  # 禁用视频
                '-acodec', audio_codec,  # 音频编码器
                '-ab', audio_quality,  # 音频比特率
                '-ar', '44100',  # 采样率
                '-y',  # 覆盖输出文件
                audio_path
            ]
            
            print(f"Extracting audio: {video_path} -> {audio_path}")
            print(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
            
            # 执行FFmpeg命令
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10分钟超时
            )
            
            if result.returncode == 0 and os.path.exists(audio_path):
                # 获取音频文件大小
                audio_size = os.path.getsize(audio_path)
                
                print(f"Audio extraction successful: {audio_filename} ({audio_size} bytes)")
                
                return JsonResponse({
                    'success': True,
                    'message': 'Audio extracted successfully',
                    'audio_filename': audio_filename,
                    'audio_path': f"/media/saved_audio/{audio_filename}",
                    'audio_size': audio_size,
                    'quality': audio_quality,
                    'format': audio_format
                }, status=200)
            else:
                print(f"FFmpeg failed: {result.stderr}")
                # 清理失败的输出文件
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                
                return JsonResponse({
                    'success': False,
                    'error': 'Audio extraction failed',
                    'details': result.stderr
                }, status=500)
        
        except subprocess.TimeoutExpired:
            return JsonResponse({
                'success': False,
                'error': 'Audio extraction timed out'
            }, status=500)
        except Exception as e:
            print(f"Audio extraction error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Audio extraction failed: {str(e)}'
            }, status=500)
    
    def has_audio_file(self, request, video_id):
        """
        检查视频是否已有对应的音频文件
        GET /video/has_audio/<video_id>
        返回音频文件的存在状态和相关信息
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            
            # 如果本身就是音频文件，返回自身信息
            if is_audio_file(video.url):
                audio_dir = os.path.join(settings.MEDIA_ROOT, 'saved_audio')
                audio_path = os.path.join(audio_dir, video.url)
                
                return JsonResponse({
                    'success': True,
                    'has_audio': True,
                    'is_audio_file': True,
                    'audio_filename': video.url,
                    'audio_path': f"/media/saved_audio/{video.url}",
                    'audio_size': os.path.getsize(audio_path) if os.path.exists(audio_path) else 0,
                    'message': 'This is an audio file'
                }, status=200)
            
            # 对于视频文件，检查是否有对应的音频文件
            audio_dir = os.path.join(settings.MEDIA_ROOT, 'saved_audio')
            video_name_without_ext = os.path.splitext(video.url)[0]
            
            # 检查常见音频格式
            audio_formats = ['mp3', 'm4a', 'aac', 'wav','alac']
            found_audio = None
            
            for fmt in audio_formats:
                audio_filename = f"{video_name_without_ext}.{fmt}"
                audio_path = os.path.join(audio_dir, audio_filename)
                
                if os.path.exists(audio_path):
                    found_audio = {
                        'filename': audio_filename,
                        'path': f"/media/audio/{audio_filename}",
                        'size': os.path.getsize(audio_path),
                        'format': fmt
                    }
                    break
            
            if found_audio:
                return JsonResponse({
                    'success': True,
                    'has_audio': True,
                    'is_audio_file': False,
                    'audio_filename': found_audio['filename'],
                    'audio_path': found_audio['path'],
                    'audio_size': found_audio['size'],
                    'audio_format': found_audio['format'],
                    'message': 'Audio file found'
                }, status=200)
            else:
                return JsonResponse({
                    'success': True,
                    'has_audio': False,
                    'is_audio_file': False,
                    'message': 'No audio file found'
                }, status=200)
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def has_waveform_peaks(self, request, video_id):
        """
        检查视频是否有对应的波形峰值JSON文件
        GET /video/has_waveform_peaks/<video_id>
        返回波形文件的存在状态和相关信息
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            
            # 使用helper函数检查波形文件
            exists, waveform_path = has_waveform_peaks(video.url)
            
            if exists:
                # 获取文件大小
                file_size = os.path.getsize(waveform_path)
                
                # 构建相对路径用于前端访问
                waveform_filename = os.path.basename(waveform_path)
                waveform_url = f"/media/waveform_data/{waveform_filename}"
                
                return JsonResponse({
                    'success': True,
                    'has_waveform_peaks': True,
                    'waveform_path': waveform_url,
                    'waveform_filename': waveform_filename,
                    'file_size': file_size,
                    'message': 'Waveform peaks file found'
                }, status=200)
            else:
                return JsonResponse({
                    'success': True,
                    'has_waveform_peaks': False,
                    'message': 'No waveform peaks file found'
                }, status=200)
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def generate_waveform_peaks(self, request, video_id):
        """
        为指定视频生成波形峰值JSON文件
        GET /video/generate_waveform_peaks/<video_id>
        传入参数是video_id.
        支持音频和视频文件的波形生成，
        对于视频文件：先检查是否有对应音频文件，没有则提取音频，然后生成波形
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            
            # 根据文件类型确定媒体路径
            directory_name, _ = get_media_path_info(video.url)
            media_path = os.path.join(settings.MEDIA_ROOT, directory_name, video.url)
            
            # 检查媒体文件是否存在
            if not os.path.exists(media_path):
                return JsonResponse({
                    'success': False,
                    'error': 'Media file not found',
                    'media_path': media_path
                }, status=404)
            
            # 检查是否已有波形文件
            waveform_exists_before, waveform_path = has_waveform_peaks(video.url)
            
            # 确定用于生成波形的文件名
            target_filename = video.url
            audio_extracted = False
            
            # 如果是视频文件，需要先检查/提取音频
            if not is_audio_file(video.url):
                print(f"[Waveform Generation] Video file detected: {video.url}, checking for audio file...")
                
                # 检查是否已有对应的音频文件
                video_name_without_ext = os.path.splitext(video.url)[0]
                audio_dir = os.path.join(settings.MEDIA_ROOT, 'saved_audio')
                
                # 查找已存在的音频文件（支持多种格式）
                audio_formats = ['mp3', 'm4a', 'aac', 'wav', 'alac']
                existing_audio_filename = None
                
                for fmt in audio_formats:
                    test_filename = f"{video_name_without_ext}.{fmt}"
                    test_path = os.path.join(audio_dir, test_filename)
                    if os.path.exists(test_path):
                        existing_audio_filename = test_filename
                        print(f"[Waveform Generation] Found existing audio file: {existing_audio_filename}")
                        break
                
                if existing_audio_filename:
                    # 使用已存在的音频文件
                    target_filename = existing_audio_filename
                else:
                    # 需要提取音频文件，调用现有的 extract_audio 方法
                    print(f"[Waveform Generation] No audio file found, extracting audio from video...")
                    
                    try:
                        # 调用现有的 extract_audio 方法
                        extraction_response = self.extract_audio(request, video_id)
                        
                        # 解析 JsonResponse 内容
                        import json
                        if hasattr(extraction_response, 'content'):
                            response_data = json.loads(extraction_response.content.decode('utf-8'))
                        else:
                            response_data = extraction_response
                        
                        if response_data.get('success'):
                            # 音频提取成功
                            audio_filename = response_data.get('audio_filename')
                            if audio_filename:
                                target_filename = audio_filename
                                audio_extracted = True
                                print(f"[Waveform Generation] Audio extraction successful: {audio_filename}")
                            else:
                                return JsonResponse({
                                    'success': False,
                                    'error': 'Audio extraction succeeded but no filename returned'
                                }, status=500)
                        else:
                            # 检查是否是文件已存在的情况 (status 409)
                            if extraction_response.status_code == 409:
                                # 文件已存在，尝试获取文件名
                                audio_path = response_data.get('audio_path', '')
                                if audio_path:
                                    # 从路径中提取文件名
                                    audio_filename = os.path.basename(audio_path.replace('/media/saved_audio/', ''))
                                    target_filename = audio_filename
                                    print(f"[Waveform Generation] Using existing audio file: {audio_filename}")
                                else:
                                    # 回退：根据视频文件名推断音频文件名
                                    audio_filename = f"{video_name_without_ext}.mp3"
                                    test_path = os.path.join(audio_dir, audio_filename)
                                    if os.path.exists(test_path):
                                        target_filename = audio_filename
                                        print(f"[Waveform Generation] Found audio file by inference: {audio_filename}")
                                    else:
                                        return JsonResponse({
                                            'success': False,
                                            'error': 'Audio file exists but cannot determine filename'
                                        }, status=500)
                            else:
                                # 音频提取失败
                                return JsonResponse({
                                    'success': False,
                                    'error': 'Audio extraction failed',
                                    'details': response_data.get('error', 'Unknown error')
                                }, status=500)
                                
                    except Exception as e:
                        print(f"[Waveform Generation] Audio extraction error: {str(e)}")
                        return JsonResponse({
                            'success': False,
                            'error': 'Audio extraction failed',
                            'details': str(e)
                        }, status=500)
            
            try:
                # 使用 waveform_generator 中的函数生成波形
                from utils.audio.waveform_generator import get_waveform_for_file
                
                print(f"[Waveform Generation] Generating waveform for filename: {target_filename}")
                waveform_data = get_waveform_for_file(target_filename)
                
                if waveform_data:
                    # 获取生成的文件信息
                    waveform_exists_after, new_waveform_path = has_waveform_peaks(target_filename)
                    file_size = os.path.getsize(new_waveform_path) if waveform_exists_after else 0
                    
                    # 构建前端访问URL
                    waveform_filename = os.path.basename(new_waveform_path)
                    waveform_url = f"/media/waveform_data/{waveform_filename}"
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Waveform peaks generated successfully',
                        'waveform_path': waveform_url,
                        'waveform_filename': waveform_filename,
                        'file_size': file_size,
                        'peaks_count': len(waveform_data.get('peaks', [])),
                        'duration': waveform_data.get('duration', 0),
                        'samples_per_second': waveform_data.get('samples_per_second', 10),
                        'was_existing': waveform_exists_before,
                        'audio_extracted': audio_extracted,  # 记录是否提取了音频
                        'target_filename': target_filename  # 记录实际用于生成波形的文件
                    }, status=200)
                else:
                    return JsonResponse({
                        'success': False,
                        'error': 'Failed to generate waveform peaks',
                        'message': 'The waveform generation process returned no data'
                    }, status=500)
                    
            except ImportError as e:
                return JsonResponse({
                    'success': False,
                    'error': 'Waveform generator module not found',
                    'details': str(e)
                }, status=500)
            except Exception as e:
                print(f"[Waveform Generation Error] {str(e)}")
                return JsonResponse({
                    'success': False,
                    'error': 'Waveform generation failed',
                    'details': str(e)
                }, status=500)
        
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def get_dimensions(self, request, video_id):
        """
        获取视频的分辨率信息（宽度和高度）
        GET /video/dimensions/<video_id>
        返回视频的宽度和高度，用于ASS字幕头部设置
        """
        try:
            video = get_object_or_404(Video, pk=video_id)
            
            # 根据文件类型确定媒体路径
            directory_name, _ = get_media_path_info(video.url)
            video_path = os.path.join(settings.MEDIA_ROOT, directory_name, video.url)
            
            if not os.path.exists(video_path):
                return JsonResponse({
                    'success': False,
                    'error': 'Video file not found'
                }, status=404)
            
            # 对于音频文件，返回错误
            if is_audio_file(video.url):
                return JsonResponse({
                    'success': False,
                    'error': 'Cannot get dimensions for audio file'
                }, status=400)
            
            # 使用 ffprobe 获取视频分辨率
            import json as json_lib
            
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-of', 'json',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                data = json_lib.loads(result.stdout)
                if 'streams' in data and len(data['streams']) > 0:
                    stream = data['streams'][0]
                    width = stream.get('width', 1920)
                    height = stream.get('height', 1080)
                    
                    return JsonResponse({
                        'success': True,
                        'width': width,
                        'height': height,
                        'message': 'Video dimensions retrieved successfully'
                    })
                else:
                    # 没有视频流
                    return JsonResponse({
                        'success': False,
                        'error': 'No video stream found in file'
                    }, status=400)
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to analyze video file',
                    'details': result.stderr
                }, status=500)
        
        except subprocess.TimeoutExpired:
            return JsonResponse({
                'success': False,
                'error': 'Video analysis timed out'
            }, status=500)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class BatchVideoActionView(View):
    @requires_delete_permission
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        
        action = data.get('action')
        
        if action == 'move_to_collection':
            return self.move_videos_to_collection(request, data)
        elif action == 'delete':
            return self.batch_delete_videos(request, data)
        elif action == 'concat':
            return self.concat_videos(request, data)
        else:
            return JsonResponse({'success': False, 'error': 'Unknown action'}, status=400)
    
    def move_videos_to_collection(self, request, data):
        """
        批量移动视频到指定合集
        请求体 JSON:
            {
                "action": "move_to_collection",
                "videoIds": [1, 2, 3],
                "collectionId": 5
            }
        """
        video_ids = data.get('videoIds', [])
        collection_id = data.get('collectionId')
        
        if not video_ids or not isinstance(video_ids, list):
            return JsonResponse({'success': False, 'error': 'Invalid videoIds'}, status=400)
        
        # 获取目标合集
        if collection_id is None:
            target_collection = None
        else:
            try:
                target_collection = get_object_or_404(Collection, pk=collection_id)
            except:
                return JsonResponse({'success': False, 'error': 'Collection not found'}, status=404)
        
        # 获取所有要移动的视频
        videos = Video.objects.filter(id__in=video_ids)
        if not videos.exists():
            return JsonResponse({'success': False, 'error': 'No valid videos found'}, status=404)
        
        # 批量更新视频
        updated_count = 0
        for video in videos:
            # 更新合集
            video.collection = target_collection
            
            # 如果目标合集存在且有分类，将视频的分类设置为与合集相同的分类
            if target_collection and target_collection.category:
                video.category = target_collection.category
            
            video.last_modified = timezone.now()
            video.save(update_fields=["collection", "category", "last_modified"])
            updated_count += 1
        
        return JsonResponse({
            'success': True,
            'message': f'成功移动 {updated_count} 个视频到合集 {target_collection.name if target_collection else "未归档"}',
            'updatedCount': updated_count,
            'collectionId': target_collection.id if target_collection else None,
        }, status=200)
    
    @requires_delete_permission
    def batch_delete_videos(self, request, data):
        """
        批量删除视频
        请求体 JSON:
            {
                "action": "delete",
                "videoIds": [1, 2, 3]
            }
        """
        video_ids = data.get('videoIds', [])
        
        if not video_ids or not isinstance(video_ids, list):
            return JsonResponse({'success': False, 'error': 'Invalid videoIds'}, status=400)
        
        # 获取所有要删除的视频
        videos = Video.objects.filter(pk__in=video_ids)
        if not videos.exists():
            return JsonResponse({'success': False, 'error': 'No valid videos found'}, status=404)
        
        # 收集要删除的文件路径
        deleted_count = 0
        deleted_files = []
        errors = []
        
        for video in videos:
            try:
                # Delete all related files for this video
                video_deleted_files, video_errors = delete_all_related_files(video)
                
                # Add files to overall list
                deleted_files.extend(video_deleted_files)
                if video_errors:
                    errors.extend([f"Video {video.name}: {err}" for err in video_errors])
                
                # Delete database record
                video.delete()
                deleted_count += 1
                
            except Exception as e:
                error_msg = f"删除视频 {video.name} 失败: {str(e)}"
                errors.append(error_msg)
                print(f"[ERROR] {error_msg}")
        
        # 构建响应消息
        if deleted_count > 0:
            message = f'成功删除 {deleted_count} 个视频，清理了 {len(deleted_files)} 个相关文件'
            if errors:
                message += f'，{len(errors)} 个文件删除失败'
        else:
            message = '没有视频被删除'
        
        return JsonResponse({
            'success': deleted_count > 0,
            'message': message,
            'deletedCount': deleted_count,
            'deletedFiles': deleted_files,
            'fileErrors': errors if errors else None
        }, status=200 if deleted_count > 0 else 400)
    
    def concat_videos(self, request, data):
        """
        批量合并视频
        请求体 JSON:
            {
                "action": "concat",
                "videoIds": [1, 2, 3]
            }
        """
        video_ids = data.get('videoIds', [])
        
        if not video_ids or not isinstance(video_ids, list) or len(video_ids) < 2:
            return JsonResponse({'success': False, 'error': 'At least 2 videos required for concatenation'}, status=400)
        
        # Get videos in the specified order
        videos = []
        for video_id in video_ids:
            try:
                video = Video.objects.get(pk=video_id)
                videos.append(video)
            except Video.DoesNotExist:
                return JsonResponse({'success': False, 'error': f'Video with ID {video_id} not found'}, status=404)
        
        # Validate videos exist and have files
        validation_errors = []
        for i, video in enumerate(videos):
            print(video.url)
            if not video.url or not os.path.exists(os.path.join(settings.MEDIA_ROOT, 'saved_video', video.url)):
                validation_errors.append(f"Video {i+1} ({video.name}): file not found")
        
        if validation_errors:
            return JsonResponse({'success': False, 'error': 'Video file validation failed', 'details': validation_errors}, status=400)
        
        # Generate temporary filename first, will rename after MD5 calculation
        import time
        temp_output_name = f"temp_merge_{int(time.time())}.mp4"
        
        # Check video properties for compatibility (optional validation)
        compatibility_warnings = self._check_video_compatibility(videos)
        
        # Perform concatenation
        try:
            result = self._concatenate_videos_with_subtitles(videos, temp_output_name)
            
            if result['success']:
                # Get the actual output filename from the result
                actual_output_name = result.get('output_name', temp_output_name)
                
                # Delete original videos
                deleted_videos = []
                for video in videos:
                    try:
                        # Delete files
                        delete_all_related_files(video)
                        deleted_videos.append(video.name)
                        video.delete()
                    except Exception as e:
                        print(f"Warning: Failed to delete video {video.name}: {e}")
                
                message = f"Successfully concatenated {len(videos)} videos into {actual_output_name}"
                if compatibility_warnings:
                    message += f". Warnings: {'; '.join(compatibility_warnings)}"
                
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'outputFile': actual_output_name,
                    'deletedVideos': deleted_videos,
                    'warnings': compatibility_warnings
                }, status=200)
            else:
                return JsonResponse({'success': False, 'error': result['error']}, status=500)
                
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Concatenation failed: {str(e)}'}, status=500)
    
    def _check_video_compatibility(self, videos):
        """Check if videos have compatible properties for smooth concatenation"""
        warnings = []
        
        # Check subtitle languages
        subtitle_languages = set()
        for video in videos:
            if video.raw_lang:
                subtitle_languages.add(video.raw_lang)
        
        if len(subtitle_languages) > 1:
            warnings.append(f"Videos have different subtitle languages: {', '.join(subtitle_languages)}")
        
        # Note: Full video codec/resolution checking would require ffprobe
        # For now, we just return warnings about subtitle languages
        
        return warnings
    
    def _concatenate_videos_with_subtitles(self, videos, output_name):
        """Concatenate videos and their subtitles"""
        try:
            import tempfile
            from datetime import timedelta
            
            # Create temporary directory for processing
            with tempfile.TemporaryDirectory() as temp_dir:
                # Step 1: Create file list for FFmpeg
                file_list_path = os.path.join(temp_dir, 'file_list.txt')
                video_paths = []
                
                with open(file_list_path, 'w', encoding='utf-8') as f:
                    for video in videos:
                        video_path = os.path.join(settings.MEDIA_ROOT, 'saved_video', video.url)
                        # Escape single quotes for FFmpeg
                        escaped_path = video_path.replace("'", "'\"'\"'")
                        f.write(f"file '{escaped_path}'\n")
                        video_paths.append(video_path)
                
                # Step 2: Concatenate videos using FFmpeg (to temporary file)
                temp_output_path = os.path.join(settings.MEDIA_ROOT, 'saved_video', output_name)
                
                ffmpeg_cmd = [
                    'ffmpeg', '-y',  # -y to overwrite existing files
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', file_list_path,
                    '-c', 'copy',  # Copy streams without re-encoding for speed
                    temp_output_path
                ]
                
                print(f"FFmpeg concat command: {' '.join(ffmpeg_cmd)}")
                
                result = subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    text=True,
                    timeout=1800  # 30 minutes timeout
                )
                
                if result.returncode != 0:
                    return {
                        'success': False,
                        'error': f'FFmpeg concatenation failed: {result.stderr}'
                    }
                
                # Step 2.5: Calculate MD5 of the merged video file and rename it
                md5_hash = hashlib.md5()
                with open(temp_output_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        md5_hash.update(chunk)
                md5_value = md5_hash.hexdigest()
                
                # Create final filename with MD5
                final_output_name = f"{md5_value}.mp4"
                final_output_path = os.path.join(settings.MEDIA_ROOT, 'saved_video', final_output_name)
                
                # Rename the file to use MD5 as filename
                os.rename(temp_output_path, final_output_path)
                
                # Update output_name for later use in subtitles and database
                output_name = final_output_name
                
                # Step 3: Get video duration for subtitle timing
                video_durations = []
                for video_path in video_paths:
                    duration = self._get_video_duration(video_path)
                    video_durations.append(duration)
                
                # Step 4: Concatenate subtitles if they exist and have same language
                self._concatenate_subtitles(videos, video_durations, output_name)
                
                # Step 5: Create new Video database entry
                self._create_concatenated_video_record(videos, output_name, video_durations)
                
                return {'success': True, 'output_name': output_name}
                
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Video concatenation timed out'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_video_duration(self, video_path):
        """Get video duration in seconds using ffprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                duration = float(data['format']['duration'])
                return duration
            else:
                print(f"Failed to get duration for {video_path}: {result.stderr}")
                return 0.0
        except Exception as e:
            print(f"Error getting video duration: {e}")
            return 0.0
    
    def _concatenate_subtitles(self, videos, video_durations, output_name):
        """Concatenate subtitle files with adjusted timestamps"""
        try:
            # Check if all videos have subtitles with same language
            subtitle_languages = set()
            videos_with_subtitles = []
            
            for video in videos:
                if video.srt_path and os.path.exists(os.path.join(settings.MEDIA_ROOT, 'saved_srt', video.srt_path)):
                    videos_with_subtitles.append((video, 'srt_path'))
                    if video.raw_lang:
                        subtitle_languages.add(video.raw_lang)
                
                if video.translated_srt_path and os.path.exists(os.path.join(settings.MEDIA_ROOT, 'saved_srt', video.translated_srt_path)):
                    videos_with_subtitles.append((video, 'translated_srt_path'))
            
            if not videos_with_subtitles:
                print("No subtitle files found for concatenation")
                return
            
            if len(subtitle_languages) > 1:
                print(f"Warning: Multiple subtitle languages detected: {subtitle_languages}")
                return
            
            # Concatenate subtitles with adjusted timestamps
            cumulative_time = 0.0
            concatenated_subtitles = []
            
            for i, (video, subtitle_field) in enumerate(videos_with_subtitles):
                subtitle_path = getattr(video, subtitle_field)
                full_subtitle_path = os.path.join(settings.MEDIA_ROOT, 'subtitle', subtitle_path)
                
                try:
                    with open(full_subtitle_path, 'r', encoding='utf-8') as f:
                        subtitle_content = f.read()
                    
                    # Parse and adjust timestamps
                    adjusted_content = self._adjust_subtitle_timestamps(subtitle_content, cumulative_time)
                    concatenated_subtitles.append(adjusted_content)
                    
                    # Add this video's duration to cumulative time
                    if i < len(video_durations):
                        cumulative_time += video_durations[i]
                    
                except Exception as e:
                    print(f"Error processing subtitle file {subtitle_path}: {e}")
            
            if concatenated_subtitles:
                # Save concatenated subtitle file
                output_subtitle_name = output_name.replace('.mp4', '.srt').replace('.mkv', '.srt').replace('.webm', '.srt')
                output_subtitle_path = os.path.join(settings.MEDIA_ROOT, 'subtitle', output_subtitle_name)
                
                with open(output_subtitle_path, 'w', encoding='utf-8') as f:
                    f.write('\n\n'.join(concatenated_subtitles))
                
                print(f"Successfully created concatenated subtitle file: {output_subtitle_name}")
                return output_subtitle_name
                
        except Exception as e:
            print(f"Error concatenating subtitles: {e}")
            return None
    
    def _adjust_subtitle_timestamps(self, subtitle_content, time_offset):
        """Adjust SRT subtitle timestamps by adding time_offset seconds"""
        import re
        
        def adjust_timestamp(match):
            timestamp = match.group(0)
            # Parse timestamp format: HH:MM:SS,mmm
            time_parts = timestamp.replace(',', '.').split(':')
            hours = int(time_parts[0])
            minutes = int(time_parts[1])
            seconds = float(time_parts[2])
            
            # Convert to total seconds and add offset
            total_seconds = hours * 3600 + minutes * 60 + seconds + time_offset
            
            # Convert back to timestamp format
            new_hours = int(total_seconds // 3600)
            new_minutes = int((total_seconds % 3600) // 60)
            new_seconds = total_seconds % 60
            
            return f"{new_hours:02d}:{new_minutes:02d}:{new_seconds:06.3f}".replace('.', ',')
        
        # Regex pattern to match SRT timestamps
        timestamp_pattern = r'\d{2}:\d{2}:\d{2},\d{3}'
        
        # Adjust all timestamps in the subtitle content
        adjusted_content = re.sub(timestamp_pattern, adjust_timestamp, subtitle_content)
        
        return adjusted_content
    
    def _create_concatenated_video_record(self, original_videos, output_name, video_durations):
        """Create a new Video database record for the concatenated video"""
        try:
            # Calculate total duration
            total_duration = sum(video_durations)
            
            # Format duration as HH:MM:SS
            hours = int(total_duration // 3600)
            minutes = int((total_duration % 3600) // 60)
            seconds = int(total_duration % 60)
            formatted_duration = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            # Use first video's metadata as base
            first_video = original_videos[0]
            
            # Create concatenated video name
            video_names = [v.name for v in original_videos[:3]]  # Limit to first 3 names
            if len(original_videos) > 3:
                concat_name = f"Merged: {', '.join(video_names)}... ({len(original_videos)} videos)"
            else:
                concat_name = f"Merged: {', '.join(video_names)}"
            
            # Create new video record
            new_video = Video.objects.create(
                name=concat_name[:128],  # Respect max_length constraint
                url=output_name,
                video_length=formatted_duration,
                category=first_video.category,
                collection=first_video.collection,
                description=f"Concatenated from {len(original_videos)} videos: {', '.join([v.name for v in original_videos])}",
                video_source='upload',  # Mark as upload since it's processed
                raw_lang=first_video.raw_lang,  # Use first video's language
                created_time=timezone.now(),
                last_modified=timezone.now()
            )
            
            # Check if concatenated subtitle was created
            output_subtitle_name = output_name.replace('.mp4', '.srt').replace('.mkv', '.srt').replace('.webm', '.srt')
            output_subtitle_path = os.path.join(settings.MEDIA_ROOT, 'subtitle', output_subtitle_name)
            
            if os.path.exists(output_subtitle_path):
                new_video.srt_path = output_subtitle_name
                new_video.save(update_fields=['srt_path'])
            
            print(f"Created new video record: {new_video.name} (ID: {new_video.id})")
            return new_video
            
        except Exception as e:
            print(f"Error creating concatenated video record: {e}")
            return None

@method_decorator(csrf_exempt, name='dispatch')
class VideoSearchView(JsonView):
    """Search videos by title, subtitles, and notes content"""
    http_method_names = ['get', 'post']

    def get_search_results(self, query, limit=2000):
        """
        Search videos by title, subtitles, and notes
        Returns list of results with matched content
        """
        if not query.strip():
            return []

        # Get all videos
        videos = Video.objects.all().select_related('category', 'collection')
        results = []
        total_matches = 0

        for video in videos:
            video_result = {
                'id': video.id,
                'url':video.url,
                'title': video.name,
                'subtitle_matched': [],
                'notes_matched': [],
                'total_matched_nums': 0
            }
            
            # Search in title
            if query.lower() in video.name.lower():
                video_result['total_matched_nums'] += 1

            # Search in subtitle files - check {videoId}_{lang}.srt pattern
            srt_dir = os.path.join(settings.MEDIA_ROOT, 'saved_srt')
            languages = ['zh', 'en', 'jp', 'kr']
            
            # Also check the main srt_path if it exists
            if video.srt_path:
                full_subtitle_path = os.path.join(srt_dir, video.srt_path)
                if os.path.exists(full_subtitle_path):
                    try:
                        with open(full_subtitle_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            lines = content.split('\n')
                            for line in lines:
                                line = line.strip()
                                # Skip SRT metadata lines (numbers, timestamps, empty lines)
                                if line and not line.isdigit() and '-->' not in line:
                                    if query.lower() in line.lower():
                                        video_result['subtitle_matched'].append(line)
                                        video_result['total_matched_nums'] += 1
                    except (IOError, UnicodeDecodeError):
                        pass

            # Check language-specific subtitle files
            for lang in languages:
                subtitle_filename = f"{video.id}_{lang}.srt"
                full_subtitle_path = os.path.join(srt_dir, subtitle_filename)
                if os.path.exists(full_subtitle_path):
                    try:
                        with open(full_subtitle_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            lines = content.split('\n')
                            for line in lines:
                                line = line.strip()
                                # Skip SRT metadata lines (numbers, timestamps, empty lines)
                                if line and not line.isdigit() and '-->' not in line:
                                    if query.lower() in line.lower():
                                        video_result['subtitle_matched'].append(line)
                                        video_result['total_matched_nums'] += 1
                    except (IOError, UnicodeDecodeError):
                        continue

            # Search in notes
            if video.notes:
                note_lines = video.notes.split('\n')
                for line in note_lines:
                    line = line.strip()
                    if line and query.lower() in line.lower():
                        video_result['notes_matched'].append(line)
                        video_result['total_matched_nums'] += 1

            # Only include videos with matches
            if video_result['total_matched_nums'] > 0:
                results.append(video_result)
                total_matches += video_result['total_matched_nums']
                
                # Check if we've exceeded the limit
                if total_matches >= limit:
                    break

        return results, total_matches

    def get(self, request):
        """Handle GET requests for search"""
        query = request.GET.get('q', '').strip()
        if not query:
            return JsonResponse({'results': [], 'total_matches': 0, 'truncated': False})

        results, total_matches = self.get_search_results(query)
        
        return JsonResponse({
            'results': results,
            'total_matches': total_matches,
            'truncated': total_matches >= 2000
        })

    def post(self, request):
        """Handle POST requests for search"""
        try:
            data = json.loads(request.body)
            query = data.get('query', '').strip()
        except (json.JSONDecodeError, AttributeError):
            query = request.POST.get('query', '').strip()

        if not query:
            return JsonResponse({'results': [], 'total_matches': 0, 'truncated': False})

        results, total_matches = self.get_search_results(query)
        
        return JsonResponse({
            'results': results,
            'total_matches': total_matches,
            'truncated': total_matches >= 2000
        })


@method_decorator(csrf_exempt, name="dispatch")
class VideoLanguageView(View):
    """Set video language for proper subtitle display"""
    
    def post(self, request, video_id):
        try:
            data = json.loads(request.body)
            raw_lang = data.get('raw_lang')
            
            if raw_lang not in ['zh', 'en', 'jp']:
                return JsonResponse({'error': 'Invalid language code'}, status=400)
            
            video = get_object_or_404(Video, pk=video_id)
            video.raw_lang = raw_lang
            video.save(update_fields=['raw_lang'])
            
            return JsonResponse({
                'success': True,
                'message': f'Video language set to {raw_lang}',
                'video_id': video_id,
                'raw_lang': raw_lang
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ============= Standalone Audio Processing Functions =============

def get_video_file_paths(video_id):
    """
    根据视频ID获取视频文件路径信息
    返回: (video_object, video_path, audio_dir)
    """
    import os
    from django.conf import settings
    from django.shortcuts import get_object_or_404
    from ..models import Video
    
    video = get_object_or_404(Video, pk=video_id)
    
    # 检查是否为音频文件，如果是则返回音频路径
    if is_audio_file(video.url):
        audio_dir = os.path.join(settings.MEDIA_ROOT, 'saved_audio')
        audio_path = os.path.join(audio_dir, video.url)
        return video, audio_path, audio_dir
    
    # 构建视频文件路径
    video_dir = os.path.join(settings.MEDIA_ROOT, 'saved_video')
    audio_dir = os.path.join(settings.MEDIA_ROOT, 'saved_audio')
    video_path = os.path.join(video_dir, video.url)
    
    return video, video_path, audio_dir


def get_audio_file_for_transcription(video_id):
    """
    为转录获取音频文件路径，如果需要则先从视频提取音频
    返回: (audio_file_path, is_newly_extracted)
    """
    import os
    
    video, file_path, audio_dir = get_video_file_paths(video_id)
    
    # 如果文件已经是音频文件，直接返回
    if is_audio_file(video.url):
        if os.path.exists(file_path):
            return file_path, False
        else:
            raise FileNotFoundError(f"Audio file not found: {file_path}")
    
    # 否则是视频文件，检查是否已有对应的音频文件
    video_name_without_ext = os.path.splitext(video.url)[0]
    
    # 检查各种音频格式
    for audio_ext in ['.mp3', '.wav', '.m4a', '.aac']:
        audio_filename = f"{video_name_without_ext}{audio_ext}"
        audio_path = os.path.join(audio_dir, audio_filename)
        if os.path.exists(audio_path):
            print(f"Found existing audio file: {audio_path}")
            return audio_path, False
    
    # 如果没有找到音频文件，从视频提取
    print(f"No existing audio file found, extracting from video: {file_path}")
    
    # 创建音频目录
    os.makedirs(audio_dir, exist_ok=True)
    
    # 检查视频文件是否存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Video file not found: {file_path}")
    
    # 检测视频中的原始音频格式
    original_audio_format = detect_video_audio_format(file_path)
    print(f"Detected original audio format: {original_audio_format}")
    
    # 生成音频文件路径（保持原始格式）
    audio_filename = f"{video_name_without_ext}.{original_audio_format}"
    audio_path = os.path.join(audio_dir, audio_filename)
    
    # 提取音频（保持原始格式）
    success, error_msg, audio_size = extract_audio_from_video_file(file_path, audio_path, preserve_format=True)
    
    if success:
        print(f"Audio extracted successfully for transcription: {audio_path} ({audio_size} bytes)")
        return audio_path, True
    else:
        raise Exception(f"Failed to extract audio for transcription: {error_msg}")



