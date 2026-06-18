# pyright: reportAttributeAccessIssue=false, reportImplicitRelativeImport=false, reportUninitializedInstanceVariable=false
import json
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import TestCase

from video import mcp_server as mcp_tools
from video.models import Category, Tag, Video


class MCPToolTestMixin:
    def load_mcp_json(self, func, *args, **kwargs):
        return json.loads(async_to_sync(func)(*args, **kwargs))

    def create_video(self, name="MCP Test Video", url="mcp-test.mp4", **kwargs):
        return Video.objects.create(name=name, url=url, **kwargs)


class MCPTagToolTests(MCPToolTestMixin, TestCase):
    def test_create_tag_requires_name(self):
        body = self.load_mcp_json(mcp_tools.create_tag, "   ")

        self.assertEqual(body, {"success": False, "error": "name is required"})

    def test_create_tag_returns_existing_case_insensitive_match(self):
        tag = Tag.objects.create(name="Existing", color="#111111")

        body = self.load_mcp_json(mcp_tools.create_tag, "existing", "#222222")

        self.assertEqual(body["success"], True)
        self.assertEqual(body["created"], False)
        self.assertEqual(body["tag"]["id"], tag.id)
        self.assertEqual(body["tag"]["color"], "#111111")
        self.assertEqual(Tag.objects.count(), 1)

    def test_update_tag_rejects_duplicate_new_name(self):
        Tag.objects.create(name="Target")
        source = Tag.objects.create(name="Source")

        body = self.load_mcp_json(
            mcp_tools.update_tag,
            tag_id=source.id,
            new_name="target",
        )

        self.assertEqual(body, {"success": False, "error": "tag name already exists"})
        source.refresh_from_db()
        self.assertEqual(source.name, "Source")

    def test_delete_tag_removes_tag_without_deleting_videos(self):
        tag = Tag.objects.create(name="Delete Me")
        video = self.create_video(name="Tagged Video", url="tagged.mp4")
        video.tags.add(tag)

        body = self.load_mcp_json(mcp_tools.delete_tag, name="delete me")

        self.assertEqual(body["success"], True)
        self.assertEqual(body["affected_videos"], 1)
        self.assertFalse(Tag.objects.filter(id=tag.id).exists())
        self.assertTrue(Video.objects.filter(id=video.id).exists())

    def test_merge_tags_moves_videos_to_target_and_deletes_source(self):
        source = Tag.objects.create(name="Source")
        target = Tag.objects.create(name="Target")
        video = self.create_video(name="Merge Video", url="merge.mp4")
        video.tags.add(source)

        body = self.load_mcp_json(
            mcp_tools.merge_tags,
            source_tag_id=source.id,
            target_tag_id=target.id,
        )

        self.assertEqual(body["success"], True)
        self.assertEqual(body["merged_video_count"], 1)
        self.assertFalse(Tag.objects.filter(id=source.id).exists())
        self.assertTrue(video.tags.filter(id=target.id).exists())

    def test_add_video_tags_cleans_duplicates_and_creates_missing_tags(self):
        video = self.create_video(name="Duplicate Tags", url="duplicate-tags.mp4")

        body = self.load_mcp_json(
            mcp_tools.add_video_tags,
            ["alpha", "", "alpha", "beta"],
            video_id=video.id,
        )

        self.assertEqual(body["success"], True)
        self.assertEqual(body["updated_video_count"], 1)
        self.assertEqual([tag["name"] for tag in body["tags"]], ["alpha", "beta"])
        self.assertEqual(set(video.tags.values_list("name", flat=True)), {"alpha", "beta"})

    def test_set_video_tags_accepts_empty_list_to_clear_tags(self):
        tag = Tag.objects.create(name="temporary")
        video = self.create_video(name="Clear Tags", url="clear-tags.mp4")
        video.tags.add(tag)

        body = self.load_mcp_json(mcp_tools.set_video_tags, [], video_id=video.id)

        self.assertEqual(body["success"], True)
        self.assertEqual(body["updated_video_count"], 1)
        self.assertEqual(body["tags"], [])
        self.assertEqual(video.tags.count(), 0)

    def test_remove_video_tags_reports_missing_names_but_removes_matches(self):
        keep = Tag.objects.create(name="keep")
        remove = Tag.objects.create(name="remove")
        video = self.create_video(name="Remove Tags", url="remove-tags.mp4")
        video.tags.add(keep, remove)

        body = self.load_mcp_json(
            mcp_tools.remove_video_tags,
            ["remove", "missing"],
            video_id=video.id,
        )

        self.assertEqual(body["success"], True)
        self.assertEqual(body["missing_tag_names"], ["missing"])
        self.assertEqual(set(video.tags.values_list("name", flat=True)), {"keep"})

    def test_remove_video_tags_requires_at_least_one_existing_tag(self):
        video = self.create_video(name="No Tags", url="no-tags.mp4")

        body = self.load_mcp_json(
            mcp_tools.remove_video_tags,
            ["missing"],
            video_id=video.id,
        )

        self.assertEqual(body["success"], False)
        self.assertEqual(body["error"], "no matching tags found")
        self.assertEqual(body["missing_tag_names"], ["missing"])


class MCPCategoryToolTests(MCPToolTestMixin, TestCase):
    def test_list_categories_includes_videos_and_unarchived_section(self):
        category = Category.objects.create(name="Docs")
        categorized = self.create_video(name="Categorized", url="categorized.mp4", category=category)
        unarchived = self.create_video(name="Loose", url="loose.mp4")

        body = self.load_mcp_json(mcp_tools.list_categories, include_videos=True, video_limit=10)

        self.assertEqual(body["success"], True)
        self.assertEqual(body["categories"][0]["id"], category.id)
        self.assertEqual(body["categories"][0]["video_count"], 1)
        self.assertEqual(body["categories"][0]["videos"][0]["id"], categorized.id)
        self.assertEqual(body["unarchived"]["video_count"], 1)
        self.assertEqual(body["unarchived"]["videos"][0]["id"], unarchived.id)

    def test_create_category_returns_existing_case_insensitive_match(self):
        category = Category.objects.create(name="Docs")

        body = self.load_mcp_json(mcp_tools.create_category, "docs")

        self.assertEqual(body["success"], True)
        self.assertEqual(body["created"], False)
        self.assertEqual(body["category"]["id"], category.id)
        self.assertEqual(Category.objects.count(), 1)

    def test_update_category_requires_new_name(self):
        category = Category.objects.create(name="Docs")

        body = self.load_mcp_json(mcp_tools.update_category, category_id=category.id)

        self.assertEqual(body, {"success": False, "error": "new_name is required"})

    def test_update_category_rejects_duplicate_new_name(self):
        Category.objects.create(name="Existing")
        category = Category.objects.create(name="Rename Me")

        body = self.load_mcp_json(
            mcp_tools.update_category,
            category_id=category.id,
            new_name="existing",
        )

        self.assertEqual(body, {"success": False, "error": "category name already exists"})
        category.refresh_from_db()
        self.assertEqual(category.name, "Rename Me")

    def test_delete_category_unassigns_videos_without_deleting_them(self):
        category = Category.objects.create(name="Delete Category")
        video = self.create_video(name="Categorized", url="delete-category.mp4", category=category)

        body = self.load_mcp_json(mcp_tools.delete_category, category_id=category.id)

        self.assertEqual(body["success"], True)
        self.assertEqual(body["affected_videos"], 1)
        self.assertFalse(Category.objects.filter(id=category.id).exists())
        video.refresh_from_db()
        self.assertIsNone(video.category)

    def test_set_video_category_creates_missing_category_when_allowed(self):
        video = self.create_video(name="Move Me", url="move-me.mp4")

        body = self.load_mcp_json(
            mcp_tools.set_video_category,
            category_name="Created Category",
            video_id=video.id,
        )

        self.assertEqual(body["success"], True)
        self.assertEqual(body["category_created"], True)
        self.assertEqual(body["category"]["name"], "Created Category")
        video.refresh_from_db()
        self.assertEqual(video.category.name, "Created Category")

    def test_set_video_category_can_clear_existing_category(self):
        category = Category.objects.create(name="Clear From")
        video = self.create_video(name="Clear Me", url="clear-me.mp4", category=category)

        body = self.load_mcp_json(mcp_tools.set_video_category, clear=True, video_id=video.id)

        self.assertEqual(body["success"], True)
        self.assertIsNone(body["category"])
        video.refresh_from_db()
        self.assertIsNone(video.category)


class MCPAPIProxyToolTests(MCPToolTestMixin, TestCase):
    @patch("video.mcp_server._call_vidgo_api")
    def test_submit_summary_task_clamps_min_coverage_and_adds_next_step(self, mock_call):
        mock_call.return_value = {"success": True, "task_id": "summary-1"}
        video = self.create_video(name="Summary", url="summary file.mp4")

        body = self.load_mcp_json(
            mcp_tools.submit_summary_task,
            video_id=video.id,
            language="English",
            min_coverage=2.5,
        )

        self.assertEqual(body["success"], True)
        self.assertEqual(body["task_id"], "summary-1")
        self.assertIn("next_step", body)
        mock_call.assert_awaited_once_with(
            None,
            "POST",
            "/api/summary/add",
            {"video_id": video.id, "language": "English", "min_coverage": 1.0},
        )

    @patch("video.mcp_server._call_vidgo_api")
    def test_get_summary_result_truncates_long_summary(self, mock_call):
        mock_call.return_value = {"success": True, "summary": "abcdef"}
        video = self.create_video(name="Summary Result", url="summary-result.mp4")

        body = self.load_mcp_json(mcp_tools.get_summary_result, video_id=video.id, max_chars=3)

        self.assertEqual(body["summary"], "abc")
        self.assertEqual(body["summary_chars"], 6)
        self.assertTrue(body["truncated"])
        mock_call.assert_awaited_once_with(
            None,
            "GET",
            "/api/video-summary/summary-result.mp4",
            timeout=120,
        )

    @patch("video.mcp_server._call_vidgo_api")
    def test_start_download_queries_bilibili_details_and_builds_download_payload(self, mock_call):
        mock_call.side_effect = [
            {
                "success": True,
                "bvid": "BV1",
                "title": "Downloaded Title",
                "video_data": [
                    {"cid": 11, "part": "Part One", "duration": 60},
                    {"cid": 22, "title": "Part Two", "duration": 90},
                ],
            },
            {"success": True, "task_ids": ["task-1", "task-2"]},
        ]

        body = self.load_mcp_json(mcp_tools.start_download, "https://www.bilibili.com/video/BV1")

        self.assertEqual(body["success"], True)
        self.assertEqual(body["task_ids"], ["task-1", "task-2"])
        self.assertIn("each task_id", body["next_step"])
        self.assertEqual(mock_call.await_count, 2)
        download_call = mock_call.await_args_list[1]
        self.assertEqual(download_call.args[1:3], ("POST", "/api/stream_media/download/add"))
        self.assertEqual(
            download_call.args[3],
            {
                "url": "https://www.bilibili.com/video/BV1",
                "bvid": "BV1",
                "filename": "Downloaded Title",
                "cids": ["11", "22"],
                "parts": ["Part One", "Part Two"],
                "durations": [60, 90],
            },
        )

    @patch("video.mcp_server._call_vidgo_api")
    def test_start_subtitle_generation_normalizes_language_aliases(self, mock_call):
        mock_call.return_value = {"success": True, "queued": True}
        video = self.create_video(name="Subtitle", url="subtitle.mp4")

        body = self.load_mcp_json(
            mcp_tools.start_subtitle_generation,
            video_id=video.id,
            src_lang="ja",
            trans_lang="english",
            emphasize_dst="VidGo",
        )

        self.assertEqual(body["success"], True)
        self.assertEqual(body["polling_key"], video.id)
        mock_call.assert_awaited_once_with(
            None,
            "POST",
            "/api/tasks/subtitle_generate/add",
            {
                "video_id_list": [video.id],
                "video_name_list": ["Subtitle"],
                "src_lang": "jp",
                "trans_lang": "en",
                "emphasize_dst": "VidGo",
            },
        )

    @patch("video.mcp_server._call_vidgo_api")
    def test_get_subtitle_status_filters_single_video_task(self, mock_call):
        mock_call.return_value = {
            "success": True,
            "http_status": 200,
            "5": {"status": "Completed"},
        }

        body = self.load_mcp_json(mcp_tools.get_subtitle_status, video_id=5)

        self.assertEqual(body["success"], True)
        self.assertEqual(body["video_id"], 5)
        self.assertEqual(body["task"], {"status": "Completed"})
        self.assertTrue(body["found"])

    @patch("video.mcp_server._call_vidgo_api")
    def test_get_transcription_status_redacts_sensitive_settings(self, mock_call):
        mock_call.side_effect = [
            {
                "success": True,
                "data": {
                    "Transcription Engine": {
                        "primary_engine": "fun-asr",
                        "api_key": "secret-key",
                        "nested": {"token": "secret-token", "safe": "visible"},
                    }
                },
            },
            {
                "success": True,
                "data": {"available_engines": ["fun-asr"], "engines": {"fun-asr": True}},
            },
            {
                "success": True,
                "data": {
                    "models": [
                        {
                            "name": "fun-asr",
                            "label": "Fun ASR",
                            "status": "ready",
                            "downloaded_size": 10,
                            "total_size": 10,
                            "ignored": "not returned",
                        }
                    ]
                },
            },
            {"success": True, "progress": {"fun-asr": {"percent": 100}}},
        ]

        body = self.load_mcp_json(mcp_tools.get_transcription_status)

        self.assertEqual(body["success"], True)
        self.assertEqual(body["active_engine"], "fun-asr")
        self.assertEqual(body["transcription_engine"]["api_key"], True)
        self.assertEqual(body["transcription_engine"]["nested"]["token"], True)
        self.assertEqual(body["transcription_engine"]["nested"]["safe"], "visible")
        self.assertEqual(body["models"][0]["name"], "fun-asr")
        self.assertNotIn("ignored", body["models"][0])

    def test_start_model_download_rejects_unknown_source_before_api_call(self):
        body = self.load_mcp_json(
            mcp_tools.start_model_download,
            model_name="funasr",
            source="bad-source",
        )

        self.assertEqual(body, {"success": False, "error": "source must be hf or modelscope"})

    def test_set_bilibili_sessdata_requires_value(self):
        body = self.load_mcp_json(mcp_tools.set_bilibili_sessdata, "   ")

        self.assertEqual(body, {"success": False, "error": "sessdata is required"})
