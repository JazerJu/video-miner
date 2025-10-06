from django.urls import path
from .views.set_setting import ConfigAPIView, TranscriptionEnginesAPIView, LLMTestAPIView, WhisperModelAPIView, WhisperModelProgressAPIView, WhisperModelSizeAPIView
from .views.videos import (
    VideoDataView,
    VideoActionView,
    VideoInfoView,
    BatchVideoActionView,
    VideoLanguageView,
    LastVideoDataView,
    VideoSearchView,
)
from .views.processing_views import ConvertAudioView, ConvertHLSView
from .views.download import VideoDownloadView
from .views.categories import CategoryActionView
from .views.media import MediaActionView
from .views.collection import CollectionActionView
from .views.subtitles import SubtitleActionView
from .views.mindmap import MindmapActionView
from .views.waveform import WaveformAPIView, WaveformListView
from .views.export import ExportTaskAddView, AllExportStatusView, ExportStatusView, DeleteExportTaskView, RetryExportTaskView, ExportedVideoDownloadView
from .views.external_transcription import (
    ExternalTranscriptionSubmitView,
    ExternalTranscriptionStatusView,
    ExternalTranscriptionResultView,
    ExternalTranscriptionListView,
    ExternalTranscriptionDeleteView
)
from .views.realtime_subtitles import RealtimeSubtitleView, RealtimeSubtitleStreamView
from .views.tts import TTSGenerateView, AllTTSStatusView, TTSStatusView, DeleteTTSTaskView, RetryTTSTaskView
from django.views.decorators.csrf import csrf_exempt,get_token,ensure_csrf_cookie
from .tasks import SubtitleTaskStatusView
from .views import stream_media
from .views import subtitles
import django
from urllib.parse import urlparse
from django.views.decorators.http import require_GET
from django.http import JsonResponse
app_name="video"

@ensure_csrf_cookie
def get_csrf_token(request):
  token = django.middleware.csrf.get_token(request)
  return JsonResponse({'csrf_token': token})

from django.http import HttpResponse, Http404
import requests

# 放到模块顶层，避免每次函数调用都重新创建列表
THUMBNAIL_ALLOWED_HOSTS = {
    # B站CDN域名
    "i0.hdslb.com",
    "i1.hdslb.com",
    "i2.hdslb.com",
    "i3.hdslb.com",
    # YouTube缩略图域名
    "i.ytimg.com",
    "img.youtube.com",
}

# 设置一个合理的超时时间，防止代理卡死
REQUEST_TIMEOUT = (3.0, 5.0)   # (连接超时, 读取超时)

@require_GET
def thumbnail_proxy(request):
    """
    代理拉取 B 站 CDN 缩略图，并返回给前端。
    只允许访问 `THUMBNAIL_ALLOWED_HOSTS` 中的域名。
    """
    raw_url = request.GET.get("url")
    if not raw_url:
        raise Http404("缺少 url 参数")

    # 解析 URL： scheme://netloc/path...
    try:
        parsed = urlparse(raw_url)
    except ValueError:
        raise Http404("无效 URL")

    # 1) 仅允许 http/https
    if parsed.scheme not in {"http", "https"}:
        raise Http404("非法协议")

    # 2) 校验 Host 是否在白名单
    if parsed.hostname not in THUMBNAIL_ALLOWED_HOSTS:
        raise Http404("非法域名")

    # 3) 代理请求
    try:
        headers = {"Referer": "https://www.bilibili.com"}
        resp = requests.get(raw_url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True)
    except requests.RequestException:
        # 网络层面出错：返回 502 让前端知道服务端取图失败
        return HttpResponse(status=502)

    if resp.status_code != 200:
        # 把远端状态码原样返回即可
        return HttpResponse(status=resp.status_code)

    # 4) 把内容透传给前端
    content_type = resp.headers.get("Content-Type", "image/jpeg")
    return HttpResponse(resp.content, content_type=content_type)
"""
在urls.py中需要展示
"""
urlpatterns = [
    # ---------- MEDIA: 仅文件/图片/流媒体直出 ----------
    # B站视频封面图片代理 - 必须在通用媒体模式之前
    path('media/thumbnail/', thumbnail_proxy, name='proxy-thumbnail'),
    # 媒体文件服务
    path('media/<str:type>/<path:filename>', MediaActionView.as_view(), name='serve_media'),

    # 配置与引擎测试
    path('api/config/', ConfigAPIView.as_view(), name='config_api'),
    path('api/transcription-engines/', TranscriptionEnginesAPIView.as_view(), name='transcription_engines_api'),
    path('api/llm-test/', LLMTestAPIView.as_view(), name='llm_test_api'),
    path('api/whisper-models/', WhisperModelAPIView.as_view(), name='whisper_models_api'),
    path('api/whisper-models/progress/', WhisperModelProgressAPIView.as_view(), name='whisper_models_progress_api'),
    path('api/whisper-models/size/', WhisperModelSizeAPIView.as_view(), name='whisper_models_size_api'),
    path('api/get_csrf_token/', get_csrf_token, name='get_csrf_token'),

    # 视频相关
    path('api/videos/', VideoDataView.as_view(), name='video_data'),
    path('api/videos/search/', VideoSearchView.as_view(), name='video_search'),
    path('api/videos/last/', LastVideoDataView.as_view(), name='last_video_data'),
    path('api/videos/info/<str:filename>', VideoInfoView.as_view(), name='video_info'),
    path('api/videos/<int:video_id>/language', VideoLanguageView.as_view(), name='set_video_language'),
    path('api/videos/<int:video_id>/<str:action>', VideoActionView.as_view(), name='video_action'),
    path('api/videos/batch_action', BatchVideoActionView.as_view(), name='batch_video_action'),
    path('api/videos/<int:video_id>/download/<str:format_type>', VideoDownloadView.as_view(), name='video_download'),

    # 转换为HLS/音频格式
    path('api/convert-hls/<int:video_id>', ConvertHLSView.as_view(), name='convert_hls_api'),
    path('api/convert-audio/<int:video_id>/', ConvertAudioView.as_view(), name='convert_audio'),

    # 字幕与思维导图
    path('api/subtitle/<str:action>/<int:video_id>', SubtitleActionView.as_view(), name='subtitle_action'),
    path('api/mindmap/<str:action>/<int:video_id>', MindmapActionView.as_view(), name='mindmap_action'),

    # 流媒体控制面板
    path('api/stream_media/query', stream_media.InfoView.as_view(), name='query_info'),
    path('api/stream_media/download/add', stream_media.DownloadActionView.as_view(), name='download_action'),
    path('api/stream_media/download_status', stream_media.AllDownloadStatusView.as_view(), name='download_status'),
    path('api/stream_media/download/<str:task_id>/delete', stream_media.DeleteDownloadTaskView.as_view(), name='download-delete'),
    path('api/stream_media/download/<str:task_id>/status', stream_media.DownloadStatusView.as_view(), name='download_status'),
    path('api/stream_media/download/<str:task_id>/retry', stream_media.RetryDownloadTaskView.as_view()),

    # 分类与合集
    path('api/category/<str:action>/<int:video_id>', CategoryActionView.as_view(), name='category_action'),
    path('api/collection/<str:action>/<int:collection_id>', CollectionActionView.as_view()),
    path('api/collection/list', CollectionActionView.as_view(), {'action': 'list', 'collection_id': 0}),

    # 波形数据
    path('api/waveform/list', WaveformListView.as_view(), name='waveform_list'),
    path('api/waveform/<path:filename>', WaveformAPIView.as_view(), name='waveform_api'),

    # 导出功能
    path('api/export/add', ExportTaskAddView.as_view(), name='export_add'),
    path('api/export/status', AllExportStatusView.as_view(), name='export_status'),
    path('api/export/<str:task_id>/status', ExportStatusView.as_view(), name='export_status_single'),
    path('api/export/<str:task_id>/delete', DeleteExportTaskView.as_view(), name='export_delete'),
    path('api/export/<str:task_id>/retry', RetryExportTaskView.as_view(), name='export_retry'),
    path('api/export/<str:task_id>/download', ExportedVideoDownloadView.as_view(), name='export_download'),

    # 外部转录服务
    path('api/external_transcription/submit', ExternalTranscriptionSubmitView.as_view(), name='external_transcription_submit'),
    path('api/external_transcription/<str:task_id>/status', ExternalTranscriptionStatusView.as_view(), name='external_transcription_status'),
    path('api/external_transcription/<str:task_id>/result', ExternalTranscriptionResultView.as_view(), name='external_transcription_result'),
    path('api/external_transcription/list', ExternalTranscriptionListView.as_view(), name='external_transcription_list'),
    path('api/external_transcription/<str:task_id>/delete', ExternalTranscriptionDeleteView.as_view(), name='external_transcription_delete'),

    # 任务管理（字幕）
    path('api/tasks/subtitle_generate/status', subtitles.AllSubtitleGenerationInfoView.as_view()),
    path('api/tasks/subtitle_generate/add', subtitles.SubtitleGenerationAddView.as_view()),
    path('api/tasks/subtitle_translation/add', subtitles.SubtitleTranslationAddView.as_view()),
    path('api/tasks/subtitle_generate/<int:video_id>/<str:action>', subtitles.SubtitleGenerationTaskView.as_view(), name='subtitle-task-action'),

    # TTS配音生成
    path('api/tts/generate/<int:video_id>', TTSGenerateView.as_view(), name='tts_generate'),
    path('api/tts/status', AllTTSStatusView.as_view(), name='tts_status_all'),
    path('api/tts/<str:task_id>/status', TTSStatusView.as_view(), name='tts_status'),
    path('api/tts/<str:task_id>/delete', DeleteTTSTaskView.as_view(), name='tts_delete'),
    path('api/tts/<str:task_id>/retry', RetryTTSTaskView.as_view(), name='tts_retry'),

    # 🆕 实时字幕生成（逐句返回）
    path('api/realtime_subtitle/start/<int:video_id>', RealtimeSubtitleView.as_view(), name='realtime_subtitle_start'),
    path('api/realtime_subtitle/status/<str:task_id>', RealtimeSubtitleView.as_view(), name='realtime_subtitle_status'),
    path('api/realtime_subtitle/stream/<str:task_id>', RealtimeSubtitleStreamView.as_view(), name='realtime_subtitle_stream'),
]
