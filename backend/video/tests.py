# pyright: reportAttributeAccessIssue=false, reportImplicitRelativeImport=false, reportUninitializedInstanceVariable=false
import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from video.models import Category, Tag, Video
from video.mcp_server import (
    get_video_info as mcp_get_video_info,
    list_videos as mcp_list_videos,
    search_videos as mcp_search_videos,
    test_connection as mcp_test_connection,
)
from video.views import set_setting


class BilibiliSessDataAPITests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_settings_file = set_setting.SETTINGS_FILE
        self._old_hotword_file = set_setting.HOTWORD_FILE
        set_setting.SETTINGS_FILE = str(Path(self._tmp.name) / "config.ini")
        set_setting.HOTWORD_FILE = str(Path(self._tmp.name) / "hotword.txt")

    def tearDown(self):
        set_setting.SETTINGS_FILE = self._old_settings_file
        set_setting.HOTWORD_FILE = self._old_hotword_file
        self._tmp.cleanup()

    def test_bilibili_sessdata_status_set_and_clear(self):
        url = "/api/media-credentials/bilibili-sessdata/"

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["configured"], False)

        sessdata = "abc%2C1893456000%2Cxyz"
        response = self.client.post(
            url,
            data={"sessdata": sessdata},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["configured"], True)
        self.assertEqual(data["length"], len(sessdata))
        self.assertEqual(data["expires_at"], "2030-01-01T00:00:00+00:00")
        self.assertNotIn("sessdata", response.json())

        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["configured"], False)

    def test_bilibili_sessdata_accepts_full_cookie_header(self):
        url = "/api/media-credentials/bilibili-sessdata/"
        response = self.client.post(
            url,
            data={"sessdata": "foo=bar; SESSDATA=abc%2C1893456000%2Cxyz; bili_jct=x"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        settings_data = set_setting.load_all_settings()
        self.assertEqual(
            settings_data["Media Credentials"]["bilibili_sessdata"],
            "abc%2C1893456000%2Cxyz",
        )

    @patch("video.views.set_setting.requests.get")
    def test_bilibili_sessdata_validate_without_cookie_does_not_call_bili(
        self,
        mock_get,
    ):
        response = self.client.get("/api/media-credentials/bilibili-sessdata/?validate=1")
        self.assertEqual(response.status_code, 200)

        data = response.json()["data"]
        self.assertEqual(data["configured"], False)
        self.assertEqual(data["validation"]["checked"], False)
        self.assertEqual(data["validation"]["valid"], False)
        mock_get.assert_not_called()

    @patch("video.views.set_setting.requests.get")
    def test_bilibili_sessdata_validate_returns_username_and_uid(self, mock_get):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "code": 0,
                    "message": "0",
                    "data": {
                        "isLogin": True,
                        "uname": "测试用户",
                        "mid": 123456,
                    },
                }

        mock_get.return_value = FakeResponse()
        url = "/api/media-credentials/bilibili-sessdata/"
        sessdata = "abc%2C1893456000%2Cxyz"

        self.client.post(
            url,
            data={"sessdata": sessdata},
            content_type="application/json",
        )
        response = self.client.get(f"{url}?validate=1")
        self.assertEqual(response.status_code, 200)

        body = response.json()
        data = body["data"]
        validation = data["validation"]
        self.assertEqual(validation["checked"], True)
        self.assertEqual(validation["valid"], True)
        self.assertEqual(validation["username"], "测试用户")
        self.assertEqual(validation["uid"], 123456)
        self.assertNotIn("sessdata", body)
        self.assertNotIn("sessdata", data)


class JSONRequestMixin:
    def post_json(self, url, data):
        return self.client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )

    def put_json(self, url, data):
        return self.client.put(
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

    def create_video(self, name="Test Video", url="test.mp4", **kwargs):
        return Video.objects.create(name=name, url=url, **kwargs)

    def login_root_user(self):
        User = get_user_model()
        user = User.objects.create_user(
            username=f"root-{User.objects.count()}",
            password="password",
            is_root=True,
            premium_authority=True,
        )
        self.client.force_login(user)
        return user

    def login_regular_user(self):
        User = get_user_model()
        user = User.objects.create_user(
            username=f"user-{User.objects.count()}",
            password="password",
            is_root=False,
            premium_authority=False,
        )
        self.client.force_login(user)
        return user


class VideoListTests(JSONRequestMixin, TestCase):
    def test_list_empty(self):
        response = self.client.get("/api/videos/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["data"], [])

    def test_list_with_videos(self):
        category = Category.objects.create(name="Tutorials")
        tagged = Tag.objects.create(name="python", color="#111111")
        video = self.create_video(
            name="Django Basics",
            url="django.mp4",
            category=category,
            raw_lang="en",
            video_source="upload",
        )
        video.tags.add(tagged)

        response = self.client.get("/api/videos/")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["data"][0]["id"], category.id)
        self.assertEqual(body["data"][0]["name"], "Tutorials")
        listed_video = body["data"][0]["loose_videos"][0]
        self.assertEqual(listed_video["id"], video.id)
        self.assertEqual(listed_video["name"], "Django Basics")
        self.assertEqual(listed_video["tags"], ["python"])
        self.assertEqual(listed_video["raw_lang"], "en")

    def test_list_has_unarchived_section(self):
        video = self.create_video(name="Loose Video", url="loose.mp4")

        response = self.client.get("/api/videos/")

        self.assertEqual(response.status_code, 200)
        sections = response.json()["data"]
        self.assertEqual(sections[-1]["id"], 0)
        self.assertEqual(sections[-1]["name"], None)
        self.assertEqual(sections[-1]["system_key"], "unarchived")
        self.assertEqual(sections[-1]["loose_videos"][0]["id"], video.id)

    def test_list_hides_categories_from_query_param(self):
        hidden = Category.objects.create(name="Hidden")
        visible = Category.objects.create(name="Visible")
        self.create_video(name="Secret", url="secret.mp4", category=hidden)
        self.create_video(name="Public", url="public.mp4", category=visible)

        response = self.client.get(f"/api/videos/?hidden_categories={hidden.id}")

        self.assertEqual(response.status_code, 200)
        category_names = [item["name"] for item in response.json()["data"]]
        self.assertNotIn("Hidden", category_names)
        self.assertIn("Visible", category_names)


class VideoSearchTests(JSONRequestMixin, TestCase):
    def test_search_by_title(self):
        video = self.create_video(name="Python Tutorial", url="python.mp4")
        self.create_video(name="Django Guide", url="django.mp4")

        response = self.client.get("/api/videos/search/?q=Python&mode=title")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("success", body)
        self.assertEqual(body["total_matches"], 1)
        self.assertEqual(body["results"][0]["id"], video.id)
        self.assertEqual(body["results"][0]["title"], "Python Tutorial")
        self.assertEqual(body["results"][0]["subtitle_matched"], [])

    def test_search_post_by_title(self):
        video = self.create_video(name="REST API Demo", url="rest.mp4")

        response = self.post_json(
            "/api/videos/search/",
            {"query": "REST", "mode": "title"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_matches"], 1)
        self.assertEqual(body["results"][0]["id"], video.id)

    def test_search_empty_query(self):
        self.create_video(name="Anything", url="anything.mp4")

        response = self.client.get("/api/videos/search/?q=&mode=title")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"results": [], "total_matches": 0, "truncated": False},
        )

    def test_search_no_results(self):
        self.create_video(name="Known Video", url="known.mp4")

        response = self.client.get("/api/videos/search/?q=missing&mode=title")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["results"], [])
        self.assertEqual(body["total_matches"], 0)
        self.assertEqual(body["truncated"], False)

    def test_search_matches_notes_in_title_content_mode(self):
        video = self.create_video(
            name="Keyword Weekly Notes",
            url="notes.mp4",
            notes="first line\nImportant keyword appears here",
        )

        response = self.client.get("/api/videos/search/?q=keyword&mode=title_content")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_matches"], 2)
        self.assertEqual(body["results"][0]["id"], video.id)
        self.assertEqual(
            body["results"][0]["notes_matched"],
            ["Important keyword appears here"],
        )


class VideoInfoTests(JSONRequestMixin, TestCase):
    def test_info_found(self):
        video = self.create_video(
            name="Info Video",
            url="info.mp4",
            description="Description",
            thumbnail_url="thumb.jpg",
            video_length="00:01:30",
            raw_lang="",
            last_played_time=12.5,
        )

        response = self.client.get("/api/videos/info/info.mp4")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("success", body)
        self.assertEqual(body["id"], video.id)
        self.assertEqual(body["name"], "Info Video")
        self.assertEqual(body["url"], "info.mp4")
        self.assertEqual(body["description"], "Description")
        self.assertEqual(body["thumbnailUrl"], "thumb.jpg")
        self.assertEqual(body["videoLength"], "00:01:30")
        self.assertEqual(body["rawLang"], "")
        self.assertEqual(body["last_played_time"], 12.5)

    def test_info_not_found(self):
        response = self.client.get("/api/videos/info/missing.mp4")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "Video not found"})

    def test_info_updates_last_modified(self):
        old_time = timezone.now() - timedelta(days=1)
        video = self.create_video(name="Recent", url="recent.mp4", last_modified=old_time)

        response = self.client.get("/api/videos/info/recent.mp4")

        self.assertEqual(response.status_code, 200)
        video.refresh_from_db()
        self.assertGreater(video.last_modified, old_time)
        self.assertIn("lastModified", response.json())


class VideoActionTests(JSONRequestMixin, TestCase):
    @patch("video.views.videos.delete_all_related_files")
    def test_delete_video(self, mock_delete_files):
        mock_delete_files.return_value = (["saved_video/delete.mp4"], [])
        video = self.create_video(name="Delete Me", url="delete.mp4")
        self.login_root_user()

        response = self.post_json(f"/api/videos/{video.id}/delete", {})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["deleted_files"], ["saved_video/delete.mp4"])
        self.assertFalse(Video.objects.filter(id=video.id).exists())

    def test_delete_requires_privileged_user(self):
        video = self.create_video(name="Protected", url="protected.mp4")
        self.login_regular_user()

        response = self.post_json(f"/api/videos/{video.id}/delete", {})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["success"], False)
        self.assertTrue(Video.objects.filter(id=video.id).exists())

    def test_rename_video(self):
        video = self.create_video(name="Old Title", url="old.mp4")

        response = self.post_json(
            f"/api/videos/{video.id}/rename",
            {"newName": "New Title"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        video.refresh_from_db()
        self.assertEqual(video.name, "New Title")

    def test_rename_requires_new_name(self):
        video = self.create_video(name="Old Title", url="old.mp4")

        response = self.post_json(f"/api/videos/{video.id}/rename", {"newName": ""})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)
        video.refresh_from_db()
        self.assertEqual(video.name, "Old Title")

    def test_save_and_load_notes(self):
        video = self.create_video(name="Notes Video", url="notes.mp4")

        save_response = self.post_json(
            f"/api/videos/{video.id}/save_notes",
            {"notes": "saved note text"},
        )
        load_response = self.client.get(f"/api/videos/{video.id}/load_notes")

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.json()["success"], True)
        self.assertEqual(load_response.status_code, 200)
        self.assertEqual(load_response.json(), {"success": True, "notes": "saved note text"})

    def test_update_progress(self):
        video = self.create_video(name="Progress", url="progress.mp4")

        response = self.post_json(
            f"/api/videos/{video.id}/update_progress",
            {"time": 1.5},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        video.refresh_from_db()
        self.assertEqual(video.last_played_time, 1.5)

    def test_unknown_action_returns_400(self):
        video = self.create_video(name="Unknown", url="unknown.mp4")

        response = self.post_json(f"/api/videos/{video.id}/unknown", {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)


class BatchActionTests(JSONRequestMixin, TestCase):
    @patch("video.views.videos.delete_all_related_files")
    def test_batch_delete(self, mock_delete_files):
        mock_delete_files.return_value = ([], [])
        videos = [
            self.create_video(name="First", url="first.mp4"),
            self.create_video(name="Second", url="second.mp4"),
        ]
        self.login_root_user()

        response = self.post_json(
            "/api/videos/batch_action",
            {"action": "delete", "videoIds": [video.id for video in videos]},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(len(body["results"]), 2)
        self.assertEqual(body["errors"], [])
        self.assertEqual(Video.objects.count(), 0)

    def test_batch_delete_requires_video_ids(self):
        self.login_root_user()

        response = self.post_json(
            "/api/videos/batch_action",
            {"action": "delete", "videoIds": []},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)

    @patch("video.views.videos.delete_all_related_files")
    def test_batch_delete_reports_missing_video(self, mock_delete_files):
        mock_delete_files.return_value = ([], [])
        video = self.create_video(name="Existing", url="existing.mp4")
        self.login_root_user()

        response = self.post_json(
            "/api/videos/batch_action",
            {"action": "delete", "videoIds": [video.id, 9999]},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], False)
        self.assertEqual(len(body["results"]), 2)
        self.assertEqual(body["results"][1]["error"], "Video not found")


class CategoryTests(JSONRequestMixin, TestCase):
    def test_query_categories(self):
        category = Category.objects.create(name="Cat")

        response = self.client.get("/api/category/query/0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        self.assertEqual(response.json()["categories"], [{"id": category.id, "name": "Cat"}])

    def test_query_empty_categories(self):
        response = self.client.get("/api/category/query/0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "categories": []})

    def test_add_category(self):
        response = self.post_json(
            "/api/category/add/0",
            {"categoryName": "New Cat"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["category"]["name"], "New Cat")
        self.assertTrue(Category.objects.filter(name="New Cat").exists())

    def test_add_category_requires_name(self):
        response = self.post_json("/api/category/add/0", {"categoryName": ""})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)

    def test_delete_category(self):
        category = Category.objects.create(name="Cat")

        response = self.post_json(
            "/api/category/delete/0",
            {"categoryName": category.name},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        self.assertFalse(Category.objects.filter(id=category.id).exists())

    def test_delete_category_unassigns_videos(self):
        category = Category.objects.create(name="Cat")
        video = self.create_video(name="Categorized", url="cat.mp4", category=category)

        response = self.post_json(
            "/api/category/delete/0",
            {"categoryName": category.name},
        )

        self.assertEqual(response.status_code, 200)
        video.refresh_from_db()
        self.assertIsNone(video.category)


class TagTests(JSONRequestMixin, TestCase):
    def test_list_tags(self):
        tag = Tag.objects.create(name="tag", color="#3B82F6")

        response = self.client.get("/api/tags/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"success": True, "tags": [{"id": tag.id, "name": "tag", "color": "#3B82F6"}]},
        )

    def test_list_tags_empty(self):
        response = self.client.get("/api/tags/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "tags": []})

    def test_create_tag(self):
        response = self.post_json(
            "/api/tags/create",
            {"name": "tag", "color": "#FF0000"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["tag"]["name"], "tag")
        self.assertEqual(body["tag"]["color"], "#FF0000")
        self.assertIn("recommended_colors", body)

    def test_create_tag_requires_name(self):
        response = self.post_json("/api/tags/create", {"name": "", "color": "#FF0000"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)

    def test_create_duplicate_tag(self):
        Tag.objects.create(name="tag")

        response = self.post_json("/api/tags/create", {"name": "tag"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)

    def test_update_tag(self):
        tag = Tag.objects.create(name="old", color="#111111")

        response = self.put_json(
            f"/api/tags/{tag.id}",
            {"name": "new", "color": "#000000"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["tag"]["name"], "new")
        self.assertEqual(body["tag"]["color"], "#000000")

    def test_update_tag_not_found(self):
        response = self.put_json("/api/tags/9999", {"name": "new", "color": "#000000"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["success"], False)

    def test_delete_tag(self):
        tag = Tag.objects.create(name="tag")

        response = self.delete_json(f"/api/tags/{tag.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        self.assertFalse(Tag.objects.filter(id=tag.id).exists())

    def test_batch_delete_tags(self):
        first = Tag.objects.create(name="first")
        second = Tag.objects.create(name="second")

        response = self.post_json(
            "/api/tags/batch_delete",
            {"tag_ids": [first.id, second.id]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        self.assertEqual(Tag.objects.count(), 0)

    def test_batch_delete_tags_requires_ids(self):
        response = self.post_json("/api/tags/batch_delete", {"tag_ids": []})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)


class MCPToolsTests(JSONRequestMixin, TestCase):
    def load_mcp_json(self, func, *args, **kwargs):
        return json.loads(async_to_sync(func)(*args, **kwargs))

    def test_connection(self):
        self.create_video(name="MCP Video", url="mcp.mp4")

        body = self.load_mcp_json(mcp_test_connection)

        self.assertEqual(body["success"], True)
        self.assertEqual(body["service"], "VidGo MCP")
        self.assertEqual(body["video_count"], 1)

    def test_list_videos(self):
        category = Category.objects.create(name="Docs")
        tag = Tag.objects.create(name="mcp-tag")
        video = self.create_video(
            name="MCP Listed",
            url="listed.mp4",
            category=category,
            video_length="00:02:00",
            video_length_seconds=120,
            raw_lang="en",
            video_source="upload",
        )
        video.tags.add(tag)

        body = self.load_mcp_json(mcp_list_videos, limit=10, offset=0)

        self.assertEqual(body["success"], True)
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["offset"], 0)
        self.assertEqual(body["limit"], 10)
        self.assertEqual(body["videos"][0]["id"], video.id)
        self.assertEqual(body["videos"][0]["title"], "MCP Listed")
        self.assertEqual(body["videos"][0]["filename"], "listed.mp4")
        self.assertEqual(body["videos"][0]["category"], "Docs")
        self.assertEqual(body["videos"][0]["tags"], ["mcp-tag"])

    def test_list_videos_empty(self):
        body = self.load_mcp_json(mcp_list_videos, limit=10, offset=0)

        self.assertEqual(body["success"], True)
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["videos"], [])

    def test_list_videos_respects_limit_and_offset(self):
        now = timezone.now()
        self.create_video(name="Old", url="old.mp4", last_modified=now - timedelta(minutes=3))
        expected = self.create_video(
            name="Middle",
            url="middle.mp4",
            last_modified=now - timedelta(minutes=2),
        )
        self.create_video(name="New", url="new.mp4", last_modified=now - timedelta(minutes=1))

        body = self.load_mcp_json(mcp_list_videos, limit=1, offset=1)

        self.assertEqual(body["success"], True)
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["limit"], 1)
        self.assertEqual(body["offset"], 1)
        self.assertEqual(body["videos"][0]["id"], expected.id)

    def test_search_videos(self):
        video = self.create_video(name="Keyword MCP", url="keyword.mp4")
        self.create_video(name="Other MCP", url="other.mp4")

        body = self.load_mcp_json(mcp_search_videos, "Keyword")

        self.assertEqual(body["success"], True)
        self.assertEqual(body["query"], "Keyword")
        self.assertEqual(body["mode"], "title")
        self.assertEqual(body["total_matches"], 1)
        self.assertEqual(body["results"][0]["id"], video.id)

    def test_get_video_info_by_id(self):
        video = self.create_video(name="Info MCP", url="info-mcp.mp4")

        body = self.load_mcp_json(mcp_get_video_info, video_id=video.id)

        self.assertEqual(body["success"], True)
        self.assertEqual(body["video"]["id"], video.id)
        self.assertEqual(body["video"]["title"], "Info MCP")
        self.assertEqual(body["video"]["filename"], "info-mcp.mp4")

    def test_get_video_info_not_found(self):
        body = self.load_mcp_json(mcp_get_video_info, video_id=9999)

        self.assertEqual(body["success"], False)
        self.assertEqual(body["error"], "video not found")


class VideoViewLayer3Tests(JSONRequestMixin, TestCase):
    def test_set_video_language_updates_raw_lang(self):
        video = self.create_video(name="Language", url="language.mp4")

        response = self.post_json(f"/api/videos/{video.id}/language", {"raw_lang": "en"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        self.assertEqual(response.json()["raw_lang"], "en")
        video.refresh_from_db()
        self.assertEqual(video.raw_lang, "en")

    def test_set_video_language_rejects_invalid_language(self):
        video = self.create_video(name="Language", url="language.mp4")

        response = self.post_json(f"/api/videos/{video.id}/language", {"raw_lang": "es"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid language code"})

    def test_set_video_language_rejects_invalid_json(self):
        video = self.create_video(name="Language", url="language.mp4")

        response = self.client.post(
            f"/api/videos/{video.id}/language",
            data="{bad-json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid JSON"})

    def test_update_video_props_updates_source_metadata(self):
        video = self.create_video(name="Props", url="props.mp4")

        response = self.post_json(
            f"/api/videos/{video.id}/props",
            {
                "raw_lang": "zh",
                "video_source": "youtube",
                "source_url": "https://youtube.com/watch?v=abc",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        video.refresh_from_db()
        self.assertEqual(video.raw_lang, "zh")
        self.assertEqual(video.video_source, "youtube")
        self.assertEqual(video.source_url, "https://youtube.com/watch?v=abc")

    def test_update_video_props_rejects_invalid_source(self):
        video = self.create_video(name="Props", url="props.mp4")

        response = self.post_json(
            f"/api/videos/{video.id}/props",
            {"video_source": "vimeo"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid source: vimeo"})

    def test_save_and_load_chapters(self):
        video = self.create_video(name="Chapters", url="chapters.mp4")
        chapters = [{"title": "Intro", "start": 0}, {"title": "Demo", "start": 90}]

        save_response = self.post_json(
            f"/api/videos/{video.id}/save_chapters",
            {"chapters": chapters},
        )
        load_response = self.client.get(f"/api/videos/{video.id}/load_chapters")

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.json()["success"], True)
        self.assertEqual(load_response.status_code, 200)
        self.assertEqual(load_response.json(), {"success": True, "chapters": chapters})

    def test_move_video_to_category_and_clear_category(self):
        category = Category.objects.create(name="Archive")
        video = self.create_video(name="Move", url="move.mp4")

        move_response = self.post_json(
            f"/api/videos/{video.id}/move_category",
            {"categoryId": category.id},
        )
        clear_response = self.post_json(
            f"/api/videos/{video.id}/move_category",
            {"categoryId": None},
        )

        self.assertEqual(move_response.status_code, 200)
        self.assertEqual(move_response.json()["success"], True)
        self.assertEqual(clear_response.status_code, 200)
        video.refresh_from_db()
        self.assertIsNone(video.category)

    def test_move_video_to_missing_category_returns_404(self):
        video = self.create_video(name="Move", url="move.mp4")

        response = self.post_json(
            f"/api/videos/{video.id}/move_category",
            {"categoryId": 9999},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["success"], False)

    def test_add_tags_creates_and_attaches_tags(self):
        video = self.create_video(name="Tagged", url="tagged.mp4")

        response = self.post_json(
            f"/api/videos/{video.id}/add_tags",
            {"tagNames": ["django", "tests"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        self.assertCountEqual(response.json()["tags"], ["django", "tests"])
        self.assertEqual(video.tags.count(), 2)

    def test_add_tags_requires_tag_names(self):
        video = self.create_video(name="Tagged", url="tagged.mp4")

        response = self.post_json(f"/api/videos/{video.id}/add_tags", {"tagNames": []})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)

    def test_batch_move_category_updates_all_requested_videos(self):
        category = Category.objects.create(name="Batch Archive")
        videos = [
            self.create_video(name="First", url="batch-first.mp4"),
            self.create_video(name="Second", url="batch-second.mp4"),
        ]

        response = self.post_json(
            "/api/videos/batch_action",
            {
                "action": "move_category",
                "videoIds": [video.id for video in videos],
                "categoryId": category.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        self.assertEqual(
            Video.objects.filter(category=category).count(),
            2,
        )

    def test_batch_move_category_missing_category_returns_404(self):
        video = self.create_video(name="Batch", url="batch.mp4")

        response = self.post_json(
            "/api/videos/batch_action",
            {"action": "move_category", "videoIds": [video.id], "categoryId": 9999},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["success"], False)

    def test_batch_add_and_remove_tags(self):
        videos = [
            self.create_video(name="First", url="tag-first.mp4"),
            self.create_video(name="Second", url="tag-second.mp4"),
        ]
        payload = {"videoIds": [video.id for video in videos], "tagNames": ["shared"]}

        add_response = self.post_json(
            "/api/videos/batch_action",
            {"action": "add_tags", **payload},
        )
        remove_response = self.post_json(
            "/api/videos/batch_action",
            {"action": "remove_tags", **payload},
        )

        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(add_response.json()["success"], True)
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(remove_response.json()["success"], True)
        self.assertFalse(Video.objects.filter(tags__name="shared").exists())

    def test_batch_remove_tags_returns_404_when_tags_do_not_exist(self):
        video = self.create_video(name="No Tags", url="no-tags.mp4")

        response = self.post_json(
            "/api/videos/batch_action",
            {"action": "remove_tags", "videoIds": [video.id], "tagNames": ["missing"]},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["success"], False)

    def test_similar_videos_requires_exact_same_category_and_tags(self):
        category = Category.objects.create(name="Similarity")
        django_tag = Tag.objects.create(name="django")
        tests_tag = Tag.objects.create(name="tests")
        target = self.create_video(name="Target", url="target.mp4", category=category)
        exact = self.create_video(name="Exact", url="exact.mp4", category=category)
        extra = self.create_video(name="Extra", url="extra.mp4", category=category)
        target.tags.add(django_tag)
        exact.tags.add(django_tag)
        extra.tags.add(django_tag, tests_tag)

        response = self.client.get(f"/api/videos/{target.id}/similar")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["videos"][0]["id"], exact.id)

    def test_similar_videos_missing_video_returns_404(self):
        response = self.client.get("/api/videos/9999/similar")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["success"], False)


from unittest.mock import MagicMock, mock_open


class VideoDownloadViewLayer3Tests(JSONRequestMixin, TestCase):
    @patch("video.views.download.os.path.getsize")
    @patch("video.views.download.os.path.exists")
    def test_head_mp4_returns_file_headers(self, mock_exists, mock_getsize):
        mock_exists.return_value = True
        mock_getsize.return_value = 12345
        video = self.create_video(name="Download", url="download.mp4")

        response = self.client.head(f"/api/videos/{video.id}/download/mp4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("Content-Length"), "12345")
        self.assertEqual(response.get("Content-Type"), "video/mp4")
        self.assertEqual(response.get("Accept-Ranges"), "bytes")

    def test_download_missing_video_returns_404(self):
        response = self.client.get("/api/videos/9999/download/mp4")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "视频不存在"})

    @patch("builtins.open", new_callable=mock_open, read_data=b"video-bytes")
    @patch("video.views.download.os.path.getsize")
    @patch("video.views.download.os.path.exists")
    def test_get_mp4_streams_existing_video(self, mock_exists, mock_getsize, mock_file):
        mock_exists.return_value = True
        mock_getsize.return_value = 11
        video = self.create_video(name="Download", url="download.mp4")

        response = self.client.get(f"/api/videos/{video.id}/download/mp4")
        content = b"".join(response.streaming_content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("Content-Type"), "video/mp4")
        self.assertEqual(
            response.get("Content-Disposition"),
            'attachment; filename="download.mp4"',
        )
        self.assertEqual(content, b"video-bytes")
        mock_file.assert_called_once()

    def test_mp4_download_rejects_audio_source(self):
        video = self.create_video(name="Audio", url="audio.mp3")

        response = self.client.get(f"/api/videos/{video.id}/download/mp4")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "音频文件无法导出为MP4格式，请选择MP3")

    @patch("builtins.open", new_callable=mock_open, read_data=b"audio-bytes")
    @patch("video.views.download.os.path.getsize")
    @patch("video.views.download.os.path.exists")
    def test_get_mp3_streams_existing_audio_file(self, mock_exists, mock_getsize, mock_file):
        mock_exists.return_value = True
        mock_getsize.return_value = 11
        video = self.create_video(name="Audio", url="audio.mp3")

        response = self.client.get(f"/api/videos/{video.id}/download/mp3")
        content = b"".join(response.streaming_content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("Content-Type"), "audio/mpeg")
        self.assertEqual(
            response.get("Content-Disposition"),
            'attachment; filename="audio.mp3"',
        )
        self.assertEqual(content, b"audio-bytes")
        mock_file.assert_called_once()

    @patch("video.views.download.os.unlink")
    @patch("builtins.open", new_callable=mock_open, read_data=b"mp3-bytes")
    @patch("video.views.download.subprocess.run")
    @patch("video.views.download.tempfile.NamedTemporaryFile")
    @patch("video.views.download.os.path.getsize")
    @patch("video.views.download.os.path.exists")
    def test_get_mp3_extracts_audio_from_video(
        self,
        mock_exists,
        mock_getsize,
        mock_named_temp,
        mock_run,
        mock_file,
        mock_unlink,
    ):
        mock_exists.return_value = True
        mock_getsize.return_value = 9
        temp_file = MagicMock()
        temp_file.name = "/tmp/extracted.mp3"
        mock_named_temp.return_value.__enter__.return_value = temp_file
        mock_run.return_value = MagicMock(returncode=0)
        video = self.create_video(name="Video", url="video.mp4")

        response = self.client.get(f"/api/videos/{video.id}/download/mp3")
        content = b"".join(response.streaming_content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("Content-Type"), "audio/mpeg")
        self.assertEqual(
            response.get("Content-Disposition"),
            'attachment; filename="video.mp3"',
        )
        self.assertEqual(content, b"mp3-bytes")
        mock_run.assert_called_once()
        mock_unlink.assert_called_once_with("/tmp/extracted.mp3")

    @patch("video.views.download.os.unlink")
    @patch("video.views.download.subprocess.run")
    @patch("video.views.download.tempfile.NamedTemporaryFile")
    @patch("video.views.download.os.path.exists")
    def test_get_mp3_extract_failure_returns_500(
        self,
        mock_exists,
        mock_named_temp,
        mock_run,
        mock_unlink,
    ):
        mock_exists.return_value = True
        temp_file = MagicMock()
        temp_file.name = "/tmp/failed.mp3"
        mock_named_temp.return_value.__enter__.return_value = temp_file
        mock_run.return_value = MagicMock(returncode=1)
        video = self.create_video(name="Video", url="video.mp4")

        response = self.client.get(f"/api/videos/{video.id}/download/mp3")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "音频提取失败"})
        mock_unlink.assert_called_once_with("/tmp/failed.mp3")

    def test_head_unsupported_format_returns_404(self):
        video = self.create_video(name="Download", url="download.mp4")

        response = self.client.head(f"/api/videos/{video.id}/download/wav")

        self.assertEqual(response.status_code, 404)


class YtDlpViewLayer3Tests(TestCase):
    @patch("video.views.yt_dlp._check_node_version")
    @patch("video.views.yt_dlp._check_node_available")
    @patch("video.views.yt_dlp._get_yt_dlp_ejs_version")
    @patch("video.views.yt_dlp._get_yt_dlp_version")
    def test_status_returns_dependency_versions(
        self,
        mock_yt_version,
        mock_ejs_version,
        mock_node_available,
        mock_node_version,
    ):
        mock_yt_version.return_value = "2026.01.01"
        mock_ejs_version.return_value = "0.1.0"
        mock_node_available.return_value = True
        mock_node_version.return_value = "v20.11.0"

        response = self.client.get("/api/yt_dlp/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["data"]["yt_dlp_version"], "2026.01.01")
        self.assertEqual(body["data"]["ejs_version"], "0.1.0")
        self.assertEqual(body["data"]["node_available"], True)
        self.assertEqual(body["data"]["node_version"], "v20.11.0")

    @patch("video.views.yt_dlp._get_yt_dlp_version", side_effect=RuntimeError("boom"))
    def test_status_returns_500_when_version_check_fails(self, mock_version):
        response = self.client.get("/api/yt_dlp/status")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["success"], False)
        self.assertIn("boom", response.json()["error"])

    @patch("video.views.yt_dlp._is_yt_dlp_ejs_importable")
    @patch("video.views.yt_dlp._get_yt_dlp_version")
    @patch("video.views.yt_dlp._run_pip")
    def test_install_deps_success_requires_ejs_importable(
        self,
        mock_run_pip,
        mock_version,
        mock_ejs_importable,
    ):
        mock_run_pip.return_value = (True, "installed")
        mock_version.return_value = "2026.01.01"
        mock_ejs_importable.return_value = True

        response = self.client.post("/api/yt_dlp/install_deps")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        self.assertEqual(response.json()["yt_dlp_version"], "2026.01.01")
        self.assertEqual(response.json()["ejs_installed"], True)
        mock_run_pip.assert_called_once_with(["install", "yt-dlp[default]"])

    @patch("video.views.yt_dlp._is_yt_dlp_ejs_importable")
    @patch("video.views.yt_dlp._get_yt_dlp_version")
    @patch("video.views.yt_dlp._run_pip")
    def test_install_deps_returns_500_when_ejs_missing(
        self,
        mock_run_pip,
        mock_version,
        mock_ejs_importable,
    ):
        mock_run_pip.return_value = (True, "installed without ejs")
        mock_version.return_value = "2026.01.01"
        mock_ejs_importable.return_value = False

        response = self.client.post("/api/yt_dlp/install_deps")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["success"], False)
        self.assertEqual(response.json()["ejs_installed"], False)

    @patch("video.views.yt_dlp._is_yt_dlp_ejs_importable")
    @patch("video.views.yt_dlp._get_yt_dlp_version")
    @patch("video.views.yt_dlp._run_pip", side_effect=RuntimeError("pip failed"))
    def test_install_deps_exception_returns_detail(
        self,
        mock_run_pip,
        mock_version,
        mock_ejs_importable,
    ):
        mock_version.return_value = "未安装"
        mock_ejs_importable.return_value = False

        response = self.client.post("/api/yt_dlp/install_deps")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["success"], False)
        self.assertEqual(response.json()["detail"], "pip failed")
        self.assertEqual(response.json()["yt_dlp_version"], "未安装")

    @patch("video.views.yt_dlp._get_yt_dlp_version")
    @patch("video.views.yt_dlp._run_pip")
    def test_upgrade_reports_upgraded_when_version_changes(self, mock_run_pip, mock_version):
        mock_version.side_effect = ["2025.12.01", "2026.01.01"]
        mock_run_pip.return_value = (True, "upgraded")

        response = self.client.post("/api/yt_dlp/upgrade")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["current_version"], "2025.12.01")
        self.assertEqual(body["new_version"], "2026.01.01")
        self.assertEqual(body["upgraded"], True)
        mock_run_pip.assert_called_once_with(["install", "-U", "yt-dlp[default]"])

    @patch("video.views.yt_dlp._get_yt_dlp_version")
    @patch("video.views.yt_dlp._run_pip")
    def test_upgrade_returns_500_when_pip_fails(self, mock_run_pip, mock_version):
        mock_version.side_effect = ["2025.12.01", "2025.12.01"]
        mock_run_pip.return_value = (False, "network failed")

        response = self.client.post("/api/yt_dlp/upgrade")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["success"], False)
        self.assertEqual(response.json()["upgraded"], False)
        self.assertEqual(response.json()["detail"], "network failed")


class VidUnderModelDownloadUrlTests(TestCase):
    def test_hf_source_uses_hf_endpoint_for_videominer_files(self):
        from vid_under.views_download import _source_url

        with patch.dict(os.environ, {"HF_ENDPOINT": "https://hf-mirror.com"}):
            self.assertEqual(
                _source_url("hf", "glm-ocr/GLM-OCR-Q8_0.gguf"),
                "https://hf-mirror.com/JazerJu/VideoMiner/resolve/main/"
                "glm-ocr/GLM-OCR-Q8_0.gguf",
            )

    def test_hf_source_uses_hf_endpoint_for_repo_specific_files(self):
        from vid_under.views_download import _source_url

        with patch.dict(os.environ, {"HF_ENDPOINT": "https://hf-mirror.com/"}):
            self.assertEqual(
                _source_url("hf", "model.safetensors", "zai-org/GLM-ASR-Nano-2512"),
                "https://hf-mirror.com/zai-org/GLM-ASR-Nano-2512/resolve/main/"
                "model.safetensors",
            )
