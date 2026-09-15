"""Uploader chapters: Bilibili view_points at download, and chapter detection that keeps author chapters."""
import json
import os
import sys
from unittest import mock

from django.test import SimpleTestCase, TestCase

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vid_under"))
import agent as agent_module  # noqa: E402
from utils.stream_downloader import native_subtitles as ns  # noqa: E402
from video.models import Video  # noqa: E402
from video.tasks import _apply_bilibili_chapters  # noqa: E402

# view_points of BV1hj8fzrEey (硅谷101), as /x/player/wbi/v2 returns them, plus one non-chapter entry
VIEW_POINTS = [
    {"type": 2, "from": 0, "to": 132, "content": "OpenAI与DeepMind的金牌drama", "imgUrl": ""},
    {"type": 2, "from": 132, "to": 198, "content": "数学领域的AlphaGo时刻还没来", "imgUrl": ""},
    {"type": 1, "from": 150, "to": 160, "content": "高能", "imgUrl": ""},
    {"type": 2, "from": 198, "to": 251, "content": " “形式化证明”", "imgUrl": ""},
]

# lfs-p3 author chapters in the Video.chapters format written at download
LFS_P3_CHAPTERS = [
    {"id": "yt-1", "title": "Introduction", "startTime": 0, "children": []},
    {"id": "yt-2", "title": "Creating the list", "startTime": 37, "children": []},
    {"id": "yt-3", "title": "Opening the list", "startTime": "4:17", "children": []},
    {"id": "yt-4", "title": "Testing", "startTime": 795.0, "children": []},
]


class BilibiliChapterTests(SimpleTestCase):
    def test_only_type_2_entries_become_chapters(self):
        chapters = ns.chapters_from_view_points(VIEW_POINTS)
        self.assertEqual([c["title"] for c in chapters], ["OpenAI与DeepMind的金牌drama", "数学领域的AlphaGo时刻还没来", "“形式化证明”"])
        self.assertEqual([c["startTime"] for c in chapters], [0.0, 132.0, 198.0])
        self.assertEqual(chapters[0]["id"], "bili-1")
        self.assertEqual(ns.chapters_from_view_points(None), [])


class BilibiliDownloadTests(TestCase):
    def test_download_stores_uploader_chapters(self):
        video = Video.objects.create(name="硅谷101 test", url="x.mp4", video_source="bilibili")
        with mock.patch("utils.stream_downloader.bili_download.get_view_points", return_value=[p for p in VIEW_POINTS if p["type"] == 2]):
            _apply_bilibili_chapters(video, "BV1hj8fzrEey", 31368216795, "")
        video.refresh_from_db()
        self.assertEqual(len(video.chapters), 3)

    def test_api_failure_does_not_fail_the_download(self):
        video = Video.objects.create(name="no chapters", url="y.mp4", video_source="bilibili")
        with mock.patch("utils.stream_downloader.bili_download.get_view_points", side_effect=OSError("timeout")):
            _apply_bilibili_chapters(video, "BV1xx", 1, "")
        video.refresh_from_db()
        self.assertEqual(video.chapters, [])


def _agent(chapters, duration=1364):
    srt = [{"start": float(t), "end": float(t) + 9, "text": f"line {t}"} for t in range(0, duration, 10)]
    db = {"duration": duration, "video_path": "no_such_video_for_tests.mp4", "author_chapters": chapters}
    return agent_module.VideoAgent(db, srt)


class AuthorChapterTests(SimpleTestCase):
    def test_author_chapters_are_parsed_and_checked(self):
        self.assertEqual(_agent(LFS_P3_CHAPTERS)._author_chapters(),
                         [[0.0, "Introduction"], [37.0, "Creating the list"], [257.0, "Opening the list"], [795.0, "Testing"]])
        # the chapter panel creates entries that all start at 0: not usable
        placeholder = [{"title": "新章节 1", "startTime": 0}, {"title": "新章节 2", "startTime": 0}]
        self.assertEqual(_agent(placeholder)._author_chapters(), [])
        self.assertEqual(_agent([{"title": "past the end", "startTime": 99999}, {"title": "a", "startTime": 5}])._author_chapters(), [])
        self.assertEqual(_agent(json.dumps(LFS_P3_CHAPTERS))._author_chapters()[1][0], 37.0)

    def test_boundaries_stay_and_llm_writes_titles(self):
        reply = json.dumps({"overview": "作者建立软件包清单并编写下载脚本。", "chapters": [
            {"index": 1, "title": "开场介绍", "gist": "回顾上期进度"},
            {"index": 3, "title": "打开清单", "gist": "逐行查看 CSV"},
            {"index": 9, "title": "越界", "gist": "忽略"},
        ]}, ensure_ascii=False)
        a = _agent(LFS_P3_CHAPTERS)
        with mock.patch.object(agent_module, "call_deepseek", return_value=reply), \
                mock.patch.object(a, "_detect_chapters_llm", side_effect=AssertionError("LLM detection must not run")):
            result = a._detect_chapters()
        chapters = result["chapters"]
        self.assertEqual([c["start_seconds"] for c in chapters], [0.0, 37.0, 257.0, 795.0])
        self.assertEqual([c["end_seconds"] for c in chapters], [37.0, 257.0, 795.0, 1364.0])
        self.assertEqual([c["title"] for c in chapters], ["开场介绍", "Creating the list", "打开清单", "Testing"])
        self.assertEqual(chapters[2]["gist"], "逐行查看 CSV")
        self.assertEqual(result["overview"], "作者建立软件包清单并编写下载脚本。")
        self.assertTrue(result["_source"].startswith("author_chapters + "))

    def test_llm_failure_keeps_author_titles(self):
        a = _agent(LFS_P3_CHAPTERS)
        with mock.patch.object(agent_module, "call_deepseek", side_effect=OSError("API down")):
            result = a._detect_chapters()
        self.assertEqual(result["_source"], "author_chapters")
        self.assertEqual([c["title"] for c in result["chapters"]], ["Introduction", "Creating the list", "Opening the list", "Testing"])

    def test_without_author_chapters_llm_detection_runs(self):
        a = _agent([])
        detected = {"_source": "detect_chapters_llm", "chapters": [{"title": "x"}]}
        with mock.patch.object(a, "_detect_chapters_llm", return_value=detected) as llm:
            self.assertIs(a._detect_chapters(), detected)
        llm.assert_called_once()
