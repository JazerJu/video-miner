# views/videos.py
import time

from django.http import (
    JsonResponse,
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
    Http404,
    FileResponse,
    HttpRequest,
)
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings  # 确保这个在顶部
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from .base import JsonView
from django.views import View
from ..models import Video, Category, VideoAttachment
from ..utils import calc_diff_time
from django.contrib.auth import get_user_model
from functools import wraps

User = get_user_model()


def serialize_datetime(dt):
    if not dt:
        return ""
    return timezone.localtime(dt).isoformat()


def requires_delete_permission(func):
    """Decorator to check if user has permission to delete videos"""

    @wraps(func)
    def wrapper(self, request, *args, **kwargs):
        # 检查用户是否已认证
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return JsonResponse(
                {"success": False, "error": "Authentication required"}, status=401
            )

        # 检查用户是否为root或拥有高级权限
        if not (request.user.is_root or request.user.premium_authority):
            return JsonResponse(
                {
                    "success": False,
                    "error": "Insufficient permissions. Only premium users can delete videos",
                },
                status=403,
            )

        return func(self, request, *args, **kwargs)

    return wrapper


def get_user_combined_hidden_categories(request):
    """Get combined hidden categories for the current user"""
    if hasattr(request, "user") and request.user.is_authenticated:
        return request.user.get_combined_hidden_categories()

    # 对于未认证用户，检查hidden_categories参数
    hidden_category_ids = []
    if "hidden_categories" in request.GET:
        try:
            hidden_categories_param = request.GET["hidden_categories"]
            if hidden_categories_param:
                hidden_category_ids = [
                    int(x.strip())
                    for x in hidden_categories_param.split(",")
                    if x.strip()
                ]
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
from ..tag_colors import get_random_tag_color

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
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, "thumbnail")
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
            thumbnail_dir = os.path.join(settings.MEDIA_ROOT, "thumbnail")
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
            srt_dir = os.path.join(settings.MEDIA_ROOT, "saved_srt")
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
            translated_srt_dir = os.path.join(settings.MEDIA_ROOT, "saved_srt")
            translated_srt_path = os.path.join(
                translated_srt_dir, video.translated_srt_path
            )

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
            waveform_dir = os.path.join(settings.MEDIA_ROOT, "waveform_data")
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
            audio_dir = os.path.join(settings.MEDIA_ROOT, "saved_audio")
            if os.path.exists(audio_dir):
                # 查找匹配基础文件名的音频文件
                audio_extensions = [".mp3", ".m4a", ".aac", ".wav", ".flac", ".alac"]
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
            stream_dir = os.path.join(settings.MEDIA_ROOT, "stream_video")
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
        screenshot_dir = os.path.join(settings.MEDIA_ROOT, "screenshot")
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
        print(
            f"[INFO] Deleted {len(deleted_files)} files for video {video.id}: {deleted_files}"
        )
    if errors:
        print(f"[ERROR] {len(errors)} deletion errors for video {video.id}: {errors}")

    return deleted_files, errors


# 记录视频的最后打开时间
def record_video_last_open(video_id):
    print("record video last open time")
    # 当触发watch_video这个函数时，自动记录视频的最后打开时间
    time_open = timezone.now()
    try:
        video = Video.objects.get(pk=video_id)
        video.last_modified = time_open
        video.save(update_fields=["last_modified"])
    except:
        return time_open


from django.db.models import Prefetch
from django.utils import timezone


class VideoDataView(JsonView):
    """
    GET /videos/
    Returns:
      {
        "success": true,
        "data": [
           { "id": 1, "name": "FolderA", "loose_videos": [...] },
           { "id": 0, "name": "Uncategorized", "loose_videos": [...] }
        ]
      }
    """

    def video_json(self, v):
        """Standard video JSON structure"""
        added_at = v.created_at or v.file_created_time
        return {
            "id": v.id,
            "name": v.name,
            "url": v.url,
            "thumbnail_url": v.thumbnail_url,
            "description": v.description or "",
            "length": v.video_length or "",
            "video_length": v.video_length,
            "video_length_seconds": v.video_length_seconds,
            "file_size": v.file_size,
            "file_created_time": v.file_created_time.strftime("%Y-%m-%d %H:%M:%S")
            if v.file_created_time
            else "",
            "last_modified": calc_diff_time(v.last_modified),
            "last_accessed_at": serialize_datetime(v.last_modified),
            "added_at": serialize_datetime(added_at),
            "content_updated_at": serialize_datetime(v.content_updated_at),
            "tags": list(v.tags.values_list("name", flat=True)),
            "last_played_time": v.last_played_time,
            "category_id": v.category_id if v.category_id else None,
            "category_name": v.category.name if v.category else None,
            "raw_lang": v.raw_lang or "",
            "video_source": v.video_source or "",
            "source_url": v.source_url or "",
        }

    def category_json(self, cat):
        """cat.categories = videos in this category"""
        videos = cat.categories.all()
        return {
            "id": cat.id,
            "name": cat.name,
            "loose_videos": [self.video_json(v) for v in videos],
        }

    def get(self, request):
        # Get hidden categories
        hidden_category_ids = get_user_combined_hidden_categories(request)

        # 1. Fetch Categories (Folders) with their videos
        cats_query = (
            Category.objects.exclude(id__in=hidden_category_ids)
            if hidden_category_ids
            else Category.objects
        )

        # Optimize query: prefetch related videos
        cats = cats_query.prefetch_related(
            Prefetch(
                "categories",
                queryset=Video.objects.prefetch_related("tags").order_by(
                    "-last_modified"
                ),
            )
        )

        # 2. Fetch Uncategorized Videos
        uncated_vids_query = (
            Video.objects.filter(category__isnull=True)
            .prefetch_related("tags")
            .order_by("-last_modified")
        )
        if hidden_category_ids:
            # If "Uncategorized" (id=0) is hidden, we might need to skip this.
            # But usually hidden_categories refers to actual Category IDs.
            # We'll assume id=0 is not in Category table so it's handled separately.
            pass

        uncated_vids = uncated_vids_query

        # Build Payload
        payload = [self.category_json(c) for c in cats]

        if uncated_vids.exists():
            payload.append(
                {
                    "id": 0,
                    "name": None,
                    "system_key": "unarchived",
                    "loose_videos": [self.video_json(v) for v in uncated_vids],
                }
            )

        return self.json_ok({"success": True, "data": payload})


class VideoSearchView(JsonView):
    """Search videos by title, subtitles, and notes content"""

    http_method_names = ["get", "post"]

    def get_search_results(self, query, mode="title_content", limit=2000, timeout=10):
        """
        Search videos by title, subtitles, and notes.
        Title uses DB icontains; subtitle/notes use file/field scan with timeout protection.
        Returns (results, total_matches, truncated).
        """
        if not query.strip():
            return [], 0, False

        query_lower = query.lower()
        search_title = mode in ["title", "title_content"]
        search_subtitle = mode in ["subtitle", "title_content"]
        search_notes = mode == "title_content"

        # --- Phase 1: Title search via DB query (fast) ---
        title_matched_ids = set()
        if search_title:
            title_matched_ids = set(
                Video.objects.filter(name__icontains=query).values_list("id", flat=True)
            )

        # If mode is title-only, return immediately
        if mode == "title":
            results = list(
                Video.objects.filter(id__in=title_matched_ids).values(
                    "id", "url", "name"
                )
            )
            formatted = [
                {
                    "id": r["id"],
                    "url": r["url"],
                    "title": r["name"],
                    "subtitle_matched": [],
                    "notes_matched": [],
                    "total_matched_nums": 1,
                }
                for r in results
            ]
            return formatted, len(formatted), False

        # --- Phase 2: Subtitle/notes scan with timeout ---
        # Build candidate set: title matches + all videos (for subtitle/notes scan)
        if search_title:
            candidate_ids = title_matched_ids
        else:
            candidate_ids = None  # scan all

        videos = Video.objects.all().select_related("category")
        if candidate_ids is not None:
            videos = videos.filter(id__in=candidate_ids)

        results = []
        total_matches = 0
        truncated = False
        start_time = time.time()
        srt_dir = os.path.join(settings.MEDIA_ROOT, "saved_srt")
        languages = ["zh", "en", "jp", "de", "kr"]

        for video in videos:
            # Timeout check at each iteration
            if time.time() - start_time >= timeout:
                truncated = True
                break

            video_result = {
                "id": video.id,
                "url": video.url,
                "title": video.name,
                "subtitle_matched": [],
                "notes_matched": [],
                "total_matched_nums": 0,
            }

            # Title match (already in candidate set but count it)
            if video.id in title_matched_ids:
                video_result["total_matched_nums"] += 1

            # Search in main subtitle file
            if search_subtitle and video.srt_path:
                full_subtitle_path = os.path.join(srt_dir, video.srt_path)
                if os.path.exists(full_subtitle_path):
                    try:
                        with open(full_subtitle_path, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if (
                                    line
                                    and not line.isdigit()
                                    and "-->" not in line
                                    and query_lower in line.lower()
                                ):
                                    video_result["subtitle_matched"].append(line)
                                    video_result["total_matched_nums"] += 1
                    except (IOError, UnicodeDecodeError):
                        pass

            # Check language-specific subtitle files
            if search_subtitle:
                for lang in languages:
                    if time.time() - start_time >= timeout:
                        truncated = True
                        break
                    subtitle_filename = f"{video.id}_{lang}.srt"
                    full_subtitle_path = os.path.join(srt_dir, subtitle_filename)
                    if os.path.exists(full_subtitle_path):
                        try:
                            with open(full_subtitle_path, "r", encoding="utf-8") as f:
                                for line in f:
                                    line = line.strip()
                                    if (
                                        line
                                        and not line.isdigit()
                                        and "-->" not in line
                                        and query_lower in line.lower()
                                    ):
                                        video_result["subtitle_matched"].append(line)
                                        video_result["total_matched_nums"] += 1
                        except (IOError, UnicodeDecodeError):
                            continue
                if truncated:
                    # Still include this partial result
                    if video_result["total_matched_nums"] > 0:
                        results.append(video_result)
                        total_matches += video_result["total_matched_nums"]
                    break

            # Search in notes
            if search_notes and video.notes:
                for line in video.notes.split("\n"):
                    line = line.strip()
                    if line and query_lower in line.lower():
                        video_result["notes_matched"].append(line)
                        video_result["total_matched_nums"] += 1

            if video_result["total_matched_nums"] > 0:
                results.append(video_result)
                total_matches += video_result["total_matched_nums"]

                if total_matches >= limit:
                    truncated = True
                    break

        # If we have title matches that weren't scanned for subtitles yet,
        # include them as title-only results
        if not truncated and search_title:
            scanned_ids = {r["id"] for r in results}
            missing_ids = title_matched_ids - scanned_ids
            if missing_ids:
                missing_videos = Video.objects.filter(id__in=missing_ids).values(
                    "id", "url", "name"
                )
                for r in missing_videos:
                    results.append(
                        {
                            "id": r["id"],
                            "url": r["url"],
                            "title": r["name"],
                            "subtitle_matched": [],
                            "notes_matched": [],
                            "total_matched_nums": 1,
                        }
                    )
                    total_matches += 1

        return results, total_matches, truncated

    def get(self, request):
        query = request.GET.get("q", "").strip()
        mode = request.GET.get("mode", "title_content").strip()
        if not query:
            return JsonResponse({"results": [], "total_matches": 0, "truncated": False})

        results, total_matches, truncated = self.get_search_results(query, mode=mode)

        return JsonResponse(
            {
                "results": results,
                "total_matches": total_matches,
                "truncated": truncated or total_matches >= 2000,
            }
        )

    def post(self, request):
        try:
            data = json.loads(request.body)
            query = data.get("query", "").strip()
            mode = data.get("mode", "title_content").strip()
        except (json.JSONDecodeError, AttributeError):
            query = request.POST.get("query", "").strip()
            mode = request.POST.get("mode", "title_content").strip()

        if not query:
            return JsonResponse({"results": [], "total_matches": 0, "truncated": False})

        results, total_matches, truncated = self.get_search_results(query, mode=mode)

        return JsonResponse(
            {
                "results": results,
                "total_matches": total_matches,
                "truncated": truncated or total_matches >= 2000,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class VideoLanguageView(View):
    """Set video language for proper subtitle display"""

    def post(self, request, video_id):
        try:
            data = json.loads(request.body)
            raw_lang = data.get("raw_lang")

            if raw_lang not in ["zh", "en", "jp", "de"]:
                return JsonResponse({"error": "Invalid language code"}, status=400)

            video = get_object_or_404(Video, pk=video_id)
            video.raw_lang = raw_lang
            video.save(update_fields=["raw_lang"])

            return JsonResponse(
                {
                    "success": True,
                    "message": f"Video language set to {raw_lang}",
                    "video_id": video_id,
                    "raw_lang": raw_lang,
                }
            )

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class VideoPropsView(View):
    VALID_LANGS = {"zh", "en", "jp", "de", ""}
    VALID_SOURCES = {"bilibili", "youtube", "podcast", "upload", "ar_glass", ""}

    def post(self, request, video_id):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        try:
            video = get_object_or_404(Video, pk=video_id)
            update_fields = []

            if "raw_lang" in data:
                val = data["raw_lang"] or ""
                if val not in self.VALID_LANGS:
                    return JsonResponse({"error": f"Invalid lang: {val}"}, status=400)
                video.raw_lang = val or None
                update_fields.append("raw_lang")

            if "video_source" in data:
                val = data["video_source"] or ""
                if val not in self.VALID_SOURCES:
                    return JsonResponse({"error": f"Invalid source: {val}"}, status=400)
                video.video_source = val or None
                update_fields.append("video_source")

            if "source_url" in data:
                video.source_url = data["source_url"] or None
                update_fields.append("source_url")

            if update_fields:
                video.save(update_fields=update_fields)

            return JsonResponse(
                {
                    "success": True,
                    "raw_lang": video.raw_lang or "",
                    "video_source": video.video_source or "",
                    "source_url": video.source_url or "",
                }
            )

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


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
        audio_dir = os.path.join(settings.MEDIA_ROOT, "saved_audio")
        audio_path = os.path.join(audio_dir, video.url)
        return video, audio_path, audio_dir

    # 构建视频文件路径
    video_dir = os.path.join(settings.MEDIA_ROOT, "saved_video")
    audio_dir = os.path.join(settings.MEDIA_ROOT, "saved_audio")
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
    for audio_ext in [".mp3", ".wav", ".m4a", ".aac"]:
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
    success, error_msg, audio_size = extract_audio_from_video_file(
        file_path, audio_path, preserve_format=True
    )

    if success:
        print(
            f"Audio extracted successfully for transcription: {audio_path} ({audio_size} bytes)"
        )
        return audio_path, True
    else:
        raise Exception(f"Failed to extract audio for transcription: {error_msg}")


@method_decorator(csrf_exempt, name="dispatch")
class VideoActionView(View):
    """Handle individual video actions via URL pattern: /api/videos/<video_id>/<action>"""

    def get(self, request, video_id, action):
        """Handle GET requests for video actions (load_chapters, load_notes)"""
        try:
            video = get_object_or_404(Video, pk=video_id)

            if action == "load_chapters":
                # 返回视频章节信息
                chapters = video.chapters
                chapters_data = []
                if isinstance(chapters, list):
                    chapters_data = chapters
                elif isinstance(chapters, str) and chapters:
                    try:
                        import json

                        chapters_data = json.loads(chapters)
                    except:
                        chapters_data = []

                return JsonResponse({"success": True, "chapters": chapters_data})

            elif action == "load_notes":
                # 返回视频笔记
                notes = video.notes if video.notes else ""
                return JsonResponse({"success": True, "notes": notes})

            else:
                return JsonResponse(
                    {"success": False, "error": f"Unknown GET action: {action}"},
                    status=400,
                )

        except Http404:
            return JsonResponse(
                {"success": False, "error": "Video not found"}, status=404
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def post(self, request, video_id, action):
        """Handle video actions"""
        try:
            # video_id=0 表示创建新视频（用于上传）
            if video_id == 0 and action == "upload":
                return self.handle_upload(request)

            video = get_object_or_404(Video, pk=video_id)

            if action == "delete":
                # Check permissions
                if not (request.user.is_root or request.user.premium_authority):
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Insufficient permissions. Only premium users can delete videos",
                        },
                        status=403,
                    )

                # Delete associated files
                deleted_files, errors = delete_all_related_files(video)

                # Delete video record
                video_name = video.name
                video.delete()

                return JsonResponse(
                    {
                        "success": True,
                        "message": f"Video '{video_name}' deleted successfully",
                        "deleted_files": deleted_files,
                    }
                )

            elif action == "save_chapters":
                try:
                    data = json.loads(request.body)
                    chapters = data.get("chapters", [])
                    video.chapters = chapters
                    video.save(update_fields=["chapters"])
                    return JsonResponse({"success": True, "message": "Chapters saved"})
                except Exception as e:
                    return JsonResponse({"success": False, "error": str(e)}, status=500)

            elif action == "save_notes":
                try:
                    data = json.loads(request.body)
                    notes = data.get("notes", "")
                    video.notes = notes
                    video.content_updated_at = timezone.now()
                    video.save(update_fields=["notes", "content_updated_at"])
                    return JsonResponse({"success": True, "message": "Notes saved"})
                except Exception as e:
                    return JsonResponse({"success": False, "error": str(e)}, status=500)

            elif action == "rename":
                try:
                    data = json.loads(request.body)
                    new_name = data.get("newName", "")
                    if not new_name:
                        return JsonResponse(
                            {"success": False, "error": "New name is required"},
                            status=400,
                        )
                    video.name = new_name
                    video.save(update_fields=["name"])
                    return JsonResponse(
                        {"success": True, "message": "Video renamed successfully"}
                    )
                except Exception as e:
                    return JsonResponse({"success": False, "error": str(e)}, status=500)

            elif action == "update_progress":
                try:
                    data = json.loads(request.body)
                    time = data.get("time", 0)
                    video.last_played_time = float(time)
                    video.save(update_fields=["last_played_time"])
                    return JsonResponse({"success": True, "message": "Progress saved"})
                except Exception as e:
                    return JsonResponse({"success": False, "error": str(e)}, status=500)

            elif action == "move_category":
                try:
                    data = json.loads(request.body)
                    category_id = data.get("categoryId")

                    if category_id is None:
                        video.category = None
                    else:
                        category = get_object_or_404(Category, pk=category_id)
                        video.category = category

                    video.save(update_fields=["category"])
                    return JsonResponse(
                        {"success": True, "message": "Category updated"}
                    )
                except Http404:
                    return JsonResponse(
                        {"success": False, "error": "Category not found"}, status=404
                    )
                except Exception as e:
                    return JsonResponse({"success": False, "error": str(e)}, status=500)

            elif action == "add_tags":
                try:
                    data = json.loads(request.body)
                    tag_names = data.get("tagNames", [])

                    if not tag_names:
                        return JsonResponse(
                            {"success": False, "error": "No tag names provided"},
                            status=400,
                        )

                    from ..models import Tag

                    for name in tag_names:
                        tag, _ = Tag.objects.get_or_create(
                            name=name,
                            defaults={
                                "color": get_random_tag_color(
                                    Tag.objects.values_list("color", flat=True)
                                )
                            },
                        )
                        video.tags.add(tag)

                    return JsonResponse(
                        {
                            "success": True,
                            "message": f"Added {len(tag_names)} tag(s)",
                            "tags": list(video.tags.values_list("name", flat=True)),
                        }
                    )
                except Exception as e:
                    return JsonResponse({"success": False, "error": str(e)}, status=500)

            elif action == "extract_audio":
                """Extract audio from video file for waveform generation"""
                try:
                    # Check if audio already exists
                    video_name_without_ext = os.path.splitext(video.url)[0]
                    audio_dir = os.path.join(settings.MEDIA_ROOT, "saved_audio")

                    # Check for existing audio files
                    for audio_ext in [".m4a", ".mp3", ".aac", ".wav"]:
                        existing_audio = os.path.join(
                            audio_dir, f"{video_name_without_ext}{audio_ext}"
                        )
                        if os.path.exists(existing_audio):
                            return JsonResponse(
                                {
                                    "success": True,
                                    "message": "Audio already exists",
                                    "audio_path": existing_audio,
                                    "was_extracted": False,
                                }
                            )

                    # Get video file path
                    video_dir = os.path.join(settings.MEDIA_ROOT, "saved_video")
                    video_path = os.path.join(video_dir, video.url)

                    if not os.path.exists(video_path):
                        return JsonResponse(
                            {"success": False, "error": "Video file not found"},
                            status=404,
                        )

                    # Create audio directory
                    os.makedirs(audio_dir, exist_ok=True)

                    # Detect audio format and extract
                    from ..services.audio_processing import (
                        detect_video_audio_format,
                        extract_audio_from_video_file,
                    )

                    audio_format = detect_video_audio_format(video_path)
                    audio_filename = f"{video_name_without_ext}.{audio_format}"
                    audio_path = os.path.join(audio_dir, audio_filename)

                    success, error_msg, audio_size = extract_audio_from_video_file(
                        video_path, audio_path, preserve_format=True
                    )

                    if success:
                        return JsonResponse(
                            {
                                "success": True,
                                "message": "Audio extracted successfully",
                                "audio_path": audio_path,
                                "audio_size": audio_size,
                                "was_extracted": True,
                            }
                        )
                    else:
                        return JsonResponse(
                            {
                                "success": False,
                                "error": f"Audio extraction failed: {error_msg}",
                            },
                            status=500,
                        )

                except Exception as e:
                    return JsonResponse({"success": False, "error": str(e)}, status=500)

            elif action == "upload_note_image":
                try:
                    if "image" not in request.FILES:
                        return JsonResponse(
                            {"success": False, "error": "No image file provided"},
                            status=400,
                        )

                    image_file = request.FILES["image"]

                    # Generate unique filename
                    import uuid

                    ext = os.path.splitext(image_file.name)[1].lower()
                    filename = f"{uuid.uuid4()}{ext}"

                    # Ensure directory exists
                    save_dir = os.path.join(settings.MEDIA_ROOT, "note_image")
                    os.makedirs(save_dir, exist_ok=True)

                    file_path = os.path.join(save_dir, filename)

                    # Save file
                    with open(file_path, "wb+") as destination:
                        for chunk in image_file.chunks():
                            destination.write(chunk)

                    # Return URL
                    image_url = f"/media/note_image/{filename}"
                    return JsonResponse({"success": True, "imageUrl": image_url})

                except Exception as e:
                    return JsonResponse({"success": False, "error": str(e)}, status=500)

            else:
                return JsonResponse(
                    {"success": False, "error": f"Unknown action: {action}"}, status=400
                )

        except Http404:
            return JsonResponse(
                {"success": False, "error": "Video not found"}, status=404
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def handle_upload(self, request):
        """处理视频文件上传"""
        try:
            if "video_file" not in request.FILES:
                return JsonResponse(
                    {"success": False, "error": "No video_file in request"}, status=400
                )

            video_file = request.FILES["video_file"]

            # 生成安全的文件名（使用 MD5）
            import hashlib

            md5_hash = hashlib.md5()
            for chunk in video_file.chunks():
                md5_hash.update(chunk)
            md5_value = md5_hash.hexdigest()

            # 获取文件扩展名
            original_name = video_file.name
            file_ext = os.path.splitext(original_name)[1].lower()
            if not file_ext:
                file_ext = ".mp4"  # 默认扩展名

            # 构建文件名和路径
            filename = f"{md5_value}{file_ext}"
            save_dir = os.path.join(settings.MEDIA_ROOT, "saved_video")
            os.makedirs(save_dir, exist_ok=True)
            file_path = os.path.join(save_dir, filename)

            # 检查文件是否已存在
            if os.path.exists(file_path):
                return JsonResponse(
                    {
                        "success": False,
                        "error": "File already exists",
                        "filename": filename,
                    },
                    status=409,
                )

            # 保存文件
            with open(file_path, "wb+") as destination:
                for chunk in video_file.chunks():
                    destination.write(chunk)

            # 创建视频记录
            from ..utils import get_video_duration, format_duration

            duration_seconds = get_video_duration(file_path)
            formatted_duration = (
                format_duration(duration_seconds) if duration_seconds else None
            )

            video = Video.objects.create(
                name=original_name,
                url=filename,
                video_length=formatted_duration,
                category=None,
            )

            # 更新文件信息（文件大小、创建时间、时长秒数）
            from ..utils import update_video_file_info

            update_video_file_info(video, save=True)

            return JsonResponse(
                {
                    "success": True,
                    "message": "Video uploaded successfully",
                    "video_id": video.id,
                    "filename": filename,
                    "name": original_name,
                },
                status=201,
            )

        except Exception as e:
            return JsonResponse(
                {"success": False, "error": f"Upload failed: {str(e)}"}, status=500
            )


@method_decorator(csrf_exempt, name="dispatch")
class BatchVideoActionView(View):
    """Handle batch video actions"""

    def post(self, request):
        """Handle batch actions"""
        try:
            data = json.loads(request.body)
            action = data.get("action")
            video_ids = data.get("videoIds", [])

            if not video_ids:
                return JsonResponse(
                    {"success": False, "error": "No video IDs provided"}, status=400
                )

            if not action:
                return JsonResponse(
                    {"success": False, "error": "No action specified"}, status=400
                )

            # Check permissions for delete action
            if action == "delete":
                if not (request.user.is_root or request.user.premium_authority):
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Insufficient permissions. Only premium users can delete videos",
                        },
                        status=403,
                    )

            results = []
            errors = []

            if action == "move_category":
                category_id = data.get("categoryId")
                target_category = None
                if category_id is not None:
                    try:
                        target_category = Category.objects.get(pk=category_id)
                    except Category.DoesNotExist:
                        return JsonResponse(
                            {"success": False, "error": "Category not found"},
                            status=404,
                        )

                Video.objects.filter(pk__in=video_ids).update(category=target_category)
                return JsonResponse(
                    {
                        "success": True,
                        "message": f"Moved {len(video_ids)} video(s)",
                    }
                )

            if action == "add_tags":
                tag_names = data.get("tagNames", [])
                if not tag_names:
                    return JsonResponse(
                        {"success": False, "error": "No tag names provided"},
                        status=400,
                    )

                from ..models import Tag

                tags = []
                for name in tag_names:
                    tag, _ = Tag.objects.get_or_create(
                        name=name,
                        defaults={
                            "color": get_random_tag_color(
                                Tag.objects.values_list("color", flat=True)
                            )
                        },
                    )
                    tags.append(tag)

                videos = Video.objects.filter(pk__in=video_ids)
                for video in videos:
                    video.tags.add(*tags)

                return JsonResponse(
                    {
                        "success": True,
                        "message": f"Added {len(tag_names)} tag(s) to {len(video_ids)} video(s)",
                    }
                )

            if action == "remove_tags":
                tag_names = data.get("tagNames", [])
                if not tag_names:
                    return JsonResponse(
                        {"success": False, "error": "No tag names provided"},
                        status=400,
                    )

                from ..models import Tag

                tags = list(Tag.objects.filter(name__in=tag_names))
                if not tags:
                    return JsonResponse(
                        {"success": False, "error": "No matching tags found"},
                        status=404,
                    )

                videos = Video.objects.filter(pk__in=video_ids)
                for video in videos:
                    video.tags.remove(*tags)

                return JsonResponse(
                    {
                        "success": True,
                        "message": f"Removed {len(tags)} tag(s) from {len(video_ids)} video(s)",
                    }
                )

            for video_id in video_ids:
                try:
                    video = Video.objects.get(pk=video_id)

                    if action == "delete":
                        deleted_files, file_errors = delete_all_related_files(video)
                        video_name = video.name
                        video.delete()
                        results.append(
                            {
                                "id": video_id,
                                "success": True,
                                "message": f"Video '{video_name}' deleted",
                                "deleted_files": deleted_files,
                            }
                        )
                        if file_errors:
                            errors.extend(
                                [{"id": video_id, "error": e} for e in file_errors]
                            )

                    else:
                        results.append(
                            {
                                "id": video_id,
                                "success": False,
                                "error": f"Unknown action: {action}",
                            }
                        )

                except Video.DoesNotExist:
                    results.append(
                        {"id": video_id, "success": False, "error": "Video not found"}
                    )
                except Exception as e:
                    results.append({"id": video_id, "success": False, "error": str(e)})
                    errors.append({"id": video_id, "error": str(e)})

            all_success = all(r.get("success") for r in results)

            return JsonResponse(
                {
                    "success": all_success,
                    "message": f"Processed {len(results)} videos, {len(errors)} errors",
                    "results": results,
                    "errors": errors,
                }
            )

        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


class VideoInfoView(JsonView):
    """Get video info by filename"""

    def get(self, request, filename):
        """Return video info for given filename"""
        try:
            video = Video.objects.get(url=filename)

            # Update last modified time
            record_video_last_open(video.id)

            return self.json_ok(
                {
                    "id": video.id,
                    "name": video.name,
                    "url": video.url,
                    "description": video.description or "",
                    "thumbnailUrl": video.thumbnail_url or "",
                    "videoLength": str(video.video_length)
                    if video.video_length
                    else "",
                    "lastModified": calc_diff_time(video.last_modified),
                    "rawLang": video.raw_lang,
                    "last_played_time": video.last_played_time,
                }
            )
        except Video.DoesNotExist:
            return JsonResponse({"error": "Video not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class SimilarVideosView(JsonView):
    """Find videos with same tags and category as given video"""

    def get(self, request, video_id):
        """Get videos with exactly same tags and category"""
        try:
            target_video = (
                Video.objects.select_related("category")
                .prefetch_related("tags")
                .get(pk=video_id)
            )

            target_tag_names = set(target_video.tags.values_list("name", flat=True))
            target_category = target_video.category

            similar_videos = Video.objects.filter(
                category=target_category
            ).prefetch_related("tags")

            if target_tag_names:
                for tag_name in target_tag_names:
                    similar_videos = similar_videos.filter(tags__name=tag_name)
            else:
                similar_videos = similar_videos.filter(tags__isnull=True)

            similar_videos = similar_videos.exclude(pk=video_id)

            final_videos = []
            for video in similar_videos:
                video_tags = set(video.tags.values_list("name", flat=True))
                if video_tags == target_tag_names:
                    final_videos.append(video)

            videos_data = []
            for video in final_videos:
                videos_data.append(
                    {
                        "id": video.id,
                        "name": video.name,
                        "url": video.url,
                        "thumbnail_url": video.thumbnail_url or "",
                        "video_length": video.video_length or "",
                    }
                )

            return self.json_ok(
                {"success": True, "videos": videos_data, "count": len(videos_data)}
            )

        except Video.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Video not found"}, status=404
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)
