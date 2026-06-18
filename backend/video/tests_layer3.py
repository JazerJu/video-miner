# pyright: reportAttributeAccessIssue=false, reportImplicitRelativeImport=false, reportUninitializedInstanceVariable=false, reportIndexIssue=false, reportArgumentType=false
import json
import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from django.http import HttpResponse
from django.test import TestCase

from video.models import Video
from video.views import media as media_views
from video.views import stream_media as stream_views
from video.views import subtitles as subtitle_views
from video.views import set_setting


class JSONRequestMixin:
    def post_json(self, url, data):
        return self.client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )

    def delete_json(self, url, data=None):
        return self.client.delete(
            url,
            data=json.dumps(data or {}),
            content_type="application/json",
        )

    def create_video(self, name="Layer 3 Video", url="layer3.mp4", **kwargs):
        return Video.objects.create(name=name, url=url, **kwargs)


class SettingsLayer3Tests(JSONRequestMixin, TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_settings_file = set_setting.SETTINGS_FILE
        self._old_hotword_file = set_setting.HOTWORD_FILE
        self._old_client = set_setting.client
        set_setting.SETTINGS_FILE = str(Path(self._tmp.name) / "config.ini")
        set_setting.HOTWORD_FILE = str(Path(self._tmp.name) / "hotword.txt")
        set_setting.download_progress.clear()

    def tearDown(self):
        set_setting.SETTINGS_FILE = self._old_settings_file
        set_setting.HOTWORD_FILE = self._old_hotword_file
        set_setting.client = self._old_client
        set_setting.download_progress.clear()
        self._tmp.cleanup()

    def test_config_get_creates_default_settings(self):
        response = self.client.get("/api/config/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertIn("DEFAULT", body["data"])
        self.assertIn("Transcription Engine", body["data"])
        self.assertIn("Media Credentials", body["data"])

    def test_config_post_requires_json_content_type(self):
        response = self.client.post("/api/config/", data={"settings": {}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Content-Type must be application/json")

    @patch("utils.llm_client.ClientPool.clear")
    @patch("video.views.set_setting._init_client")
    def test_config_post_saves_settings_and_reinitializes_client(
        self,
        mock_init_client,
        mock_clear_pool,
    ):
        settings_payload = {
            "DEFAULT": {
                "selected_model_provider": "local",
                "local_api_key": "",
                "local_base_url": "http://localhost:1234/v1",
                "split_use_proxy": "false",
                "proxy_url": "",
            },
            "Media Credentials": {"bilibili_sessdata": "", "proxy_url": ""},
        }

        response = self.post_json("/api/config/", {"settings": settings_payload})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        self.assertEqual(set_setting.load_all_settings()["DEFAULT"]["selected_model_provider"], "local")
        mock_clear_pool.assert_called_once()
        mock_init_client.assert_called_once_with(
            "",
            "http://localhost:1234/v1",
            allow_empty_key=True,
            use_proxy=False,
        )

    @patch("video.views.set_setting.TranscriptionEngineFactory.get_available_engines")
    @patch("video.views.set_setting.TranscriptionEngineFactory.get_engine_info")
    def test_transcription_engines_marks_available_status(
        self,
        mock_engine_info,
        mock_available_engines,
    ):
        mock_engine_info.return_value = {
            "funasr_gguf": {"name": "FunASR"},
            "cloud": {"name": "Cloud"},
        }
        mock_available_engines.return_value = ["funasr_gguf"]

        response = self.client.get("/api/transcription-engines/")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["available_engines"], ["funasr_gguf"])
        self.assertEqual(data["engines"]["funasr_gguf"]["available"], True)
        self.assertEqual(data["engines"]["cloud"]["available"], False)

    @patch("video.views.set_setting.load_all_settings")
    def test_llm_test_missing_api_key_returns_400(self, mock_load_settings):
        mock_load_settings.return_value = {
            "DEFAULT": {
                "selected_model_provider": "deepseek",
                "deepseek_api_key": "",
                "deepseek_base_url": "https://api.deepseek.com/v1",
                "deepseek_model": "deepseek-chat",
                "split_use_proxy": "false",
            }
        }

        response = self.client.get("/api/llm-test/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)
        self.assertIn("API key not configured", response.json()["error"])

    @patch("video.views.set_setting.load_all_settings")
    @patch("video.views.set_setting._init_client")
    def test_llm_test_local_provider_success_uses_mocked_client(
        self,
        mock_init_client,
        mock_load_settings,
    ):
        fake_client = MagicMock()
        fake_choice = MagicMock()
        fake_choice.message.content = "Connection successful!"
        fake_client.chat.completions.create.return_value = MagicMock(choices=[fake_choice])

        def install_fake_client(*args, **kwargs):
            set_setting.client = fake_client

        mock_init_client.side_effect = install_fake_client
        mock_load_settings.return_value = {
            "DEFAULT": {
                "selected_model_provider": "local",
                "local_api_key": "",
                "local_base_url": "http://localhost:1234/v1",
                "local_model": "local-model",
                "split_use_proxy": "false",
            }
        }

        response = self.client.get("/api/llm-test/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "response": "Connection successful!"})
        fake_client.chat.completions.create.assert_called_once()

    @patch("video.views.set_setting.load_all_settings")
    def test_whisper_models_get_returns_current_engine(self, mock_load_settings):
        mock_load_settings.return_value = {
            "Transcription Engine": {"primary_engine": "whisper_cpp"}
        }

        response = self.client.get("/api/whisper-models/")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["current_engine"], "whisper_cpp")
        self.assertEqual(data["models"], [])

    def test_whisper_model_post_requires_model_name(self):
        response = self.post_json("/api/whisper-models/", {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "model_name is required")

    def test_whisper_model_post_rejects_already_downloading_model(self):
        set_setting.download_progress["base"] = 25

        response = self.post_json("/api/whisper-models/", {"model_name": "base"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "Model is already being downloaded")

    def test_whisper_model_progress_returns_current_progress(self):
        set_setting.download_progress["small"] = 50

        set_setting.download_progress["large"] = -1

        response = self.client.get("/api/whisper-models/progress/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["progress"], {"small": 50, "large": -1})

    def test_whisper_model_size_requires_model_name(self):
        response = self.post_json("/api/whisper-models/size/", {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "model_name is required")

    @patch("video.views.set_setting.os.path.getsize")
    @patch("video.views.set_setting.os.walk")
    @patch("video.views.set_setting.os.path.exists")
    def test_whisper_model_size_counts_mocked_folder_files(
        self,
        mock_exists,
        mock_walk,
        mock_getsize,
    ):
        mock_exists.return_value = True
        mock_walk.return_value = [("/models", [], ["a.bin", "b.bin"])]
        mock_getsize.side_effect = [1024, 2048]

        response = self.post_json("/api/whisper-models/size/", {"model_name": "base"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["size"], 3072)
        self.assertEqual(body["file_count"], 2)
        self.assertEqual(body["exists"], True)


class NamedBytesIO(io.BytesIO):
    name = "subtitle.srt"


class SubtitleLayer3Tests(JSONRequestMixin, TestCase):
    def setUp(self):
        subtitle_views.subtitle_task_status.clear()

    def tearDown(self):
        subtitle_views.subtitle_task_status.clear()

    def test_subtitle_action_requires_language_code(self):
        video = self.create_video()

        response = self.client.get(f"/api/subtitle/query/{video.id}")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "No language code")

    def test_subtitle_action_rejects_unsupported_language_code(self):
        video = self.create_video()

        response = self.client.get(f"/api/subtitle/query/{video.id}?lang=fr")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Unsupported language code")

    @patch("video.views.subtitles.os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    def test_subtitle_upload_saves_file_and_updates_video(self, mocked_open, mock_makedirs):
        video = self.create_video(srt_path="")

        response = self.post_json(
            f"/api/subtitle/upload/{video.id}?lang=en",
            {"srtContent": "1\n00:00:00,000 --> 00:00:01,000\nHello"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["success"], True)
        mock_makedirs.assert_called_once_with(subtitle_views.SAVE_DIR, exist_ok=True)
        mocked_open().write.assert_called_once()
        video.refresh_from_db()
        self.assertEqual(video.srt_path, f"{video.id}_en.srt")
        self.assertIsNotNone(video.content_updated_at)

    def test_subtitle_upload_rejects_invalid_json(self):
        video = self.create_video()

        response = self.client.post(
            f"/api/subtitle/upload/{video.id}?lang=en",
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON format")

    def test_subtitle_upload_requires_srt_content(self):
        video = self.create_video()

        response = self.post_json(f"/api/subtitle/upload/{video.id}?lang=en", {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Missing 'srtContent' in request body")

    @patch("video.views.subtitles.os.path.exists", return_value=True)
    @patch("builtins.open")
    def test_subtitle_query_returns_file_response(self, mocked_open, mock_exists):
        video = self.create_video(srt_path="existing.srt")
        mocked_open.return_value = NamedBytesIO(b"1\n00:00:00,000 --> 00:00:01,000\nHello")

        response = self.client.get(f"/api/subtitle/query/{video.id}?lang=en")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        mock_exists.assert_called_once()
        mocked_open.assert_called_once()

    def test_subtitle_query_without_saved_path_returns_404(self):
        video = self.create_video(srt_path="")

        response = self.client.get(f"/api/subtitle/query/{video.id}?lang=en")

        self.assertEqual(response.status_code, 404)

    @patch("video.views.subtitles.subtitle_task_queue.put")
    def test_subtitle_generation_add_enqueues_task_and_updates_raw_lang(self, mock_put):
        video = self.create_video(raw_lang="")

        response = self.post_json(
            "/api/tasks/subtitle_generate/add",
            {
                "video_id_list": [video.id],
                "video_name_list": [video.name],
                "src_lang": "en",
                "trans_lang": "zh",
                "emphasize_dst": "Django",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        mock_put.assert_called_once_with(str(video.id))
        self.assertEqual(subtitle_views.subtitle_task_status[video.id]["src_lang"], "en")
        video.refresh_from_db()
        self.assertEqual(video.raw_lang, "en")

    def test_subtitle_generation_add_requires_video_ids(self):
        response = self.post_json(
            "/api/tasks/subtitle_generate/add",
            {"video_name_list": ["Video"], "src_lang": "en"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], 'Missing "video_id_list" field')

    def test_subtitle_translation_add_rejects_invalid_target_language(self):
        video = self.create_video(raw_lang="en")

        response = self.post_json(
            "/api/tasks/subtitle_translation/add",
            {
                "video_id_list": [video.id],
                "video_name_list": [video.name],
                "target_lang": "fr",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid target language")

    @patch("video.views.subtitles.os.path.exists", return_value=False)
    def test_subtitle_translation_add_requires_existing_original_subtitle(self, mock_exists):
        video = self.create_video(raw_lang="en")

        response = self.post_json(
            "/api/tasks/subtitle_translation/add",
            {
                "video_id_list": [video.id],
                "video_name_list": [video.name],
                "target_lang": "zh",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Original subtitle not found", response.json()["error"])
        mock_exists.assert_called_once()

    @patch("video.views.subtitles.subtitle_task_queue.put")
    @patch("video.views.subtitles.os.path.exists", return_value=True)
    def test_subtitle_translation_add_enqueues_translation_only_task(
        self,
        mock_exists,
        mock_put,
    ):
        video = self.create_video(raw_lang="en")

        response = self.post_json(
            "/api/tasks/subtitle_translation/add",
            {
                "video_id_list": [video.id],
                "video_name_list": [video.name],
                "target_lang": "zh",
                "emphasize_dst": "terms",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertIn("Translation tasks queued", body["message"])
        self.assertEqual(subtitle_views.subtitle_task_status[video.id]["translation_only"], True)
        self.assertEqual(subtitle_views.subtitle_task_status[video.id]["total_progress"], 70)
        mock_put.assert_called_once_with(str(video.id))

    def test_subtitle_task_retry_missing_task_returns_400(self):
        response = self.client.post("/api/tasks/subtitle_generate/999/retry")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"Task not found")

    @patch("video.views.subtitles.subtitle_task_queue.put")
    def test_subtitle_task_retry_resets_existing_task(self, mock_put):
        video = self.create_video()
        subtitle_views.subtitle_task_status[video.id] = {
            "translation_only": True,
            "stages": {"translate": "Failed"},
            "stage_progress": {"translate": 50},
            "stage_detail": {"translate": "failed"},
            "total_progress": 85,
        }

        response = self.client.post(f"/api/tasks/subtitle_generate/{video.id}/retry")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task_id"], video.id)
        self.assertEqual(subtitle_views.subtitle_task_status[video.id]["stages"]["translate"], "Queued")
        self.assertEqual(subtitle_views.subtitle_task_status[video.id]["total_progress"], 70)
        mock_put.assert_called_once_with(str(video.id))

    def test_subtitle_task_delete_missing_task_returns_404(self):
        response = self.client.delete("/api/tasks/subtitle_generate/999/delete")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Task not found")

    def test_subtitle_task_delete_removes_existing_status(self):
        video = self.create_video()
        subtitle_views.subtitle_task_status[video.id] = {"filename": video.name}

        response = self.client.delete(f"/api/tasks/subtitle_generate/{video.id}/delete")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Download task deleted")
        self.assertNotIn(video.id, subtitle_views.subtitle_task_status)


class StreamMediaLayer3Tests(JSONRequestMixin, TestCase):
    def setUp(self):
        with stream_views.download_status_lock:
            stream_views.download_status.clear()

    def tearDown(self):
        with stream_views.download_status_lock:
            stream_views.download_status.clear()

    def test_stream_query_rejects_invalid_json(self):
        response = self.client.post(
            "/api/stream_media/query",
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON")

    def test_stream_query_requires_url(self):
        response = self.post_json("/api/stream_media/query", {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], 'Missing "url" field')

    def test_stream_query_rejects_unsupported_url(self):
        response = self.post_json("/api/stream_media/query", {"url": "https://example.com/v"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Unsupported URL")

    @patch("video.views.stream_media.YouTubeDownloader")
    def test_stream_query_youtube_uses_mocked_downloader(self, mock_downloader_cls):
        mock_downloader_cls.return_value.get_video_info.return_value = {
            "id": "yt123",
            "title": "YouTube Clip",
            "duration": 42,
            "uploader": "Uploader",
            "thumbnail": "thumb.jpg",
        }

        response = self.post_json(
            "/api/stream_media/query",
            {"url": "https://youtube.com/watch?v=yt123"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["bvid"], "yt123")
        self.assertEqual(body["title"], "YouTube Clip")
        self.assertEqual(body["collectionCount"], 1)
        mock_downloader_cls.return_value.get_video_info.assert_called_once()

    @patch("video.views.stream_media.bili_download.get_cid")
    @patch("video.views.stream_media.bili_download.get_video_info")
    @patch("video.views.stream_media.bili_download.extract_av_bv_p")
    def test_stream_query_bilibili_uses_mocked_helpers(
        self,
        mock_extract,
        mock_video_info,
        mock_get_cid,
    ):
        mock_extract.return_value = ("BV123", None, 1)
        mock_video_info.return_value = {
            "bvid": "BV123",
            "owner": "owner",
            "pic_url": "pic.jpg",
            "title": "Bili Clip",
            "duration": 99,
        }
        mock_get_cid.return_value = (["cid1", "cid2"], [{"cid": "cid1"}, {"cid": "cid2"}])

        response = self.post_json(
            "/api/stream_media/query",
            {"url": "https://www.bilibili.com/video/BV123"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["bvid"], "BV123")
        self.assertEqual(body["collectionCount"], 2)
        self.assertEqual(body["video_data"], [{"cid": "cid1"}, {"cid": "cid2"}])

    @patch("video.views.stream_media.download_queue.put")
    @patch("video.views.stream_media.time.time", return_value=123.456)
    def test_stream_download_add_youtube_enqueues_status(self, mock_time, mock_put):
        response = self.post_json(
            "/api/stream_media/download/add",
            {
                "url": "https://youtube.com/watch?v=yt123",
                "bvid": "yt123",
                "filename": "YouTube Clip",
            },
        )

        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task_id"]
        self.assertEqual(task_id, "123456")
        self.assertEqual(stream_views.download_status[task_id]["platform"], "youtube")
        self.assertEqual(stream_views.download_status[task_id]["stage_weights"]["video"], 1.0)
        mock_put.assert_called_once_with(task_id)

    def test_stream_download_add_bilibili_requires_bvid(self):
        response = self.post_json(
            "/api/stream_media/download/add",
            {"url": "https://www.bilibili.com/video/BV123"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing "bvid"')

    def test_stream_download_status_missing_returns_404(self):
        response = self.client.get("/api/stream_media/download/missing/status")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Task not found")

    def test_stream_all_download_status_returns_current_statuses(self):
        with stream_views.download_status_lock:
            stream_views.download_status["task1"] = {"finished": False, "title": "One"}

        response = self.client.get("/api/stream_media/download_status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"task1": {"finished": False, "title": "One"}})

    @patch("video.views.stream_media.download_queue.put")
    def test_stream_retry_resets_existing_task(self, mock_put):
        with stream_views.download_status_lock:
            stream_views.download_status["task1"] = {
                "finished": True,
                "stages": {"video": "Failed", "audio": "Failed", "merge": "Failed"},
                "stage_progress": {"video": 100, "audio": 20, "merge": 0},
                "total_progress": 50,
            }

        response = self.client.post("/api/stream_media/download/task1/retry")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(stream_views.download_status["task1"]["finished"], False)
        self.assertEqual(stream_views.download_status["task1"]["stages"]["video"], "Queued")
        self.assertEqual(stream_views.download_status["task1"]["total_progress"], 0)
        mock_put.assert_called_once_with("task1")

    def test_stream_delete_missing_task_returns_404(self):
        response = self.client.delete("/api/stream_media/download/missing/delete")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Task not found")

    def test_stream_delete_existing_task_removes_status(self):
        with stream_views.download_status_lock:
            stream_views.download_status["task1"] = {"finished": False}

        response = self.client.delete("/api/stream_media/download/task1/delete")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Download task deleted")
        self.assertNotIn("task1", stream_views.download_status)


class MediaLayer3Tests(JSONRequestMixin, TestCase):
    @patch("video.views.media.subprocess.run")
    def test_detect_video_codec_returns_av1_mime_type(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="av1\n")

        content_type = media_views.detect_video_codec("movie.mp4")

        self.assertEqual(content_type, 'video/mp4; codecs="av01.0.08M.08"')
        mock_run.assert_called_once()

    @patch("video.views.media.subprocess.run", side_effect=FileNotFoundError)
    def test_detect_video_codec_falls_back_when_ffprobe_missing(self, mock_run):
        content_type = media_views.detect_video_codec("movie.mp4")

        self.assertEqual(content_type, "video/mp4")

    @patch("builtins.open", new_callable=mock_open, read_data=b"video-bytes")
    @patch("video.views.media.detect_video_codec", return_value="video/mp4")
    @patch("video.views.media.os.path.getsize", return_value=1000)
    @patch("video.views.media.os.path.exists", return_value=True)
    def test_media_video_range_request_returns_partial_content_headers(
        self,
        mock_exists,
        mock_getsize,
        mock_detect_codec,
        mocked_open,
    ):
        response = self.client.get(
            "/media/video/movie.mp4?t=12",
            HTTP_RANGE="bytes=10-19",
        )

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], "bytes 10-19/1000")
        self.assertEqual(response["Content-Length"], "10")
        self.assertEqual(response["Accept-Ranges"], "bytes")
        self.assertEqual(response["X-Initial-Time"], "12")

    @patch("video.views.media.detect_video_codec", return_value="video/mp4")
    @patch("video.views.media.os.path.getsize", return_value=1000)
    @patch("video.views.media.os.path.exists", return_value=True)
    def test_media_video_invalid_range_returns_416(
        self,
        mock_exists,
        mock_getsize,
        mock_detect_codec,
    ):
        response = self.client.get("/media/video/movie.mp4", HTTP_RANGE="bytes=90-10")

        self.assertEqual(response.status_code, 416)
        self.assertEqual(response["Content-Range"], "bytes */1000")

    @patch("builtins.open", new_callable=mock_open, read_data=b"audio-bytes")
    @patch("video.views.media.os.path.getsize", return_value=100)
    @patch("video.views.media.os.path.exists", side_effect=[False, True])
    def test_media_audio_falls_back_to_saved_video_and_supports_range(
        self,
        mock_exists,
        mock_getsize,
        mocked_open,
    ):
        response = self.client.get("/media/audio/sound.mp3", HTTP_RANGE="bytes=0-9")

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], "bytes 0-9/100")
        self.assertEqual(response["Content-Length"], "10")

    @patch("video.views.media.os.path.exists", return_value=False)
    def test_media_video_missing_file_returns_404(self, mock_exists):
        response = self.client.get("/media/video/missing.mp4")

        self.assertEqual(response.status_code, 404)

    @patch("builtins.open")
    @patch("video.views.media.os.path.exists", return_value=True)
    def test_media_stream_video_playlist_sets_hls_headers(self, mock_exists, mocked_open):
        mocked_open.return_value = NamedBytesIO(b"#EXTM3U")

        response = self.client.get("/media/stream_video/digest/index.m3u8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.apple.mpegurl")
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")
        self.assertEqual(response["Cache-Control"], "public, max-age=10")
        mocked_open.assert_called_once()

    @patch("video.views.media.serve", return_value=HttpResponse(b"image"))
    @patch("video.views.media.os.path.exists", return_value=True)
    def test_media_image_delegates_to_static_serve(self, mock_exists, mock_serve):
        response = self.client.get("/media/img/thumb.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"image")
        mock_serve.assert_called_once()

    def test_media_unknown_type_returns_405(self):
        response = self.client.get("/media/unknown/file.bin")

        self.assertEqual(response.status_code, 405)


class WaveformLayer3Tests(JSONRequestMixin, TestCase):
    @patch("video.views.waveform.get_waveform_for_file")
    @patch("video.views.waveform.WaveformAPIView._find_audio_file_by_prefix")
    def test_waveform_get_returns_generated_data(self, mock_find_audio, mock_get_waveform):
        mock_find_audio.return_value = "audio.mp3"
        mock_get_waveform.return_value = {
            "audio_file": "audio.mp3",
            "duration": 12.5,
            "peaks": [0.1, 0.2],
            "length": 2,
        }

        response = self.client.get("/api/waveform/audio")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["audio_file"], "audio.mp3")
        self.assertEqual(body["generated_at"], "server-side")
        self.assertEqual(body["matched_filename"], "audio.mp3")
        mock_get_waveform.assert_called_once_with("audio.mp3")

    @patch("video.views.waveform.WaveformAPIView._find_audio_file_by_prefix", return_value=None)
    def test_waveform_get_returns_404_when_audio_file_missing(self, mock_find_audio):
        response = self.client.get("/api/waveform/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "No matching audio file found")

    @patch("video.views.waveform.get_waveform_for_file", return_value=None)
    @patch("video.views.waveform.WaveformAPIView._find_audio_file_by_prefix", return_value="audio.mp3")
    def test_waveform_get_returns_404_when_generation_fails(
        self,
        mock_find_audio,
        mock_get_waveform,
    ):
        response = self.client.get("/api/waveform/audio")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Failed to generate or retrieve waveform data")

    @patch("video.views.waveform.os.path.getmtime", return_value=456.0)
    @patch("video.views.waveform.os.path.getsize", return_value=123)
    @patch("video.views.waveform.json.load")
    @patch("builtins.open", new_callable=mock_open, read_data="{}")
    @patch("video.views.waveform.os.listdir", return_value=["audio.peaks.json", "ignore.txt"])
    @patch("video.views.waveform.os.path.exists", return_value=True)
    def test_waveform_list_returns_metadata_for_peak_files(
        self,
        mock_exists,
        mock_listdir,
        mocked_open,
        mock_json_load,
        mock_getsize,
        mock_getmtime,
    ):
        mock_json_load.return_value = {"audio_file": "audio.mp3", "duration": 12.5, "length": 2}

        response = self.client.get("/api/waveform/list")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_count"], 1)
        self.assertEqual(body["waveform_files"][0]["filename"], "audio.peaks.json")
        self.assertEqual(body["waveform_files"][0]["file_size"], 123)

    @patch("video.views.waveform.os.path.exists", return_value=False)
    def test_waveform_list_returns_empty_when_directory_missing(self, mock_exists):
        response = self.client.get("/api/waveform/list")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["waveform_files"], [])
        self.assertEqual(response.json()["total_count"], 0)


class LanguageTracksLayer3Tests(JSONRequestMixin, TestCase):
    def test_language_tracks_missing_video_returns_404(self):
        response = self.client.get("/api/video/999/languages")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"success": False, "error": "Video not found"})

    @patch("video.views.language_tracks.os.path.exists", return_value=False)
    def test_language_tracks_returns_empty_when_files_missing(self, mock_exists):
        video = self.create_video(name="No Tracks", url="movie.mp4", raw_lang="en")

        response = self.client.get(f"/api/video/{video.id}/languages")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["data"]["video_id"], video.id)
        self.assertEqual(body["data"]["languages"], [])

    @patch("video.views.language_tracks.os.listdir")
    @patch("video.views.language_tracks.os.path.exists")
    def test_language_tracks_lists_original_and_tts_tracks(self, mock_exists, mock_listdir):
        video = self.create_video(name="Movie", url="movie.mp4", raw_lang="en")
        mock_exists.side_effect = [True, True]
        mock_listdir.return_value = ["movie_zh.mp4", "movie_en.mp4", "other_jp.mp4"]

        response = self.client.get(f"/api/video/{video.id}/languages")

        self.assertEqual(response.status_code, 200)
        languages = response.json()["data"]["languages"]
        self.assertEqual(
            languages,
            [
                {
                    "code": "en",
                    "name": "English",
                    "type": "original",
                    "url": "/media/saved_video/movie.mp4",
                },
                {
                    "code": "zh",
                    "name": "中文",
                    "type": "tts",
                    "url": "/media/saved_video/movie_zh.mp4",
                },
            ],
        )

    @patch("video.views.language_tracks.os.listdir", return_value=[])
    @patch("video.views.language_tracks.os.path.exists", side_effect=[True, True])
    def test_language_tracks_uses_uppercase_name_for_unknown_original_language(
        self,
        mock_exists,
        mock_listdir,
    ):
        video = self.create_video(name="German", url="german.mp4", raw_lang="de")

        response = self.client.get(f"/api/video/{video.id}/languages")

        self.assertEqual(response.status_code, 200)
        languages = response.json()["data"]["languages"]
        self.assertEqual(languages[0]["code"], "de")
        self.assertEqual(languages[0]["name"], "DE")
        self.assertEqual(languages[0]["type"], "original")
