"""YouTube native subtitles and chapters (utils/stream_downloader/native_subtitles.py)."""
import json
import os
import tempfile

from django.test import SimpleTestCase, TestCase, override_settings

from utils.stream_downloader import native_subtitles as ns
from video.models import Video
from video.tasks import _apply_youtube_metadata, _native_transcript

# First cues of the automatic captions of "Build a LinuxFromScratch System Part 3" (en-orig track),
# as yt-dlp downloads them. Note the one-space line above the first words.
AUTO_VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.640 --> 00:00:02.310 align:start position:0%
 
hi<00:00:00.880><c> everyone</c><00:00:01.280><c> and</c><00:00:01.439><c> welcome</c><00:00:01.760><c> back</c><00:00:01.920><c> to</c><00:00:02.080><c> this</c>

00:00:02.310 --> 00:00:02.320 align:start position:0%
hi everyone and welcome back to this
 

00:00:02.320 --> 00:00:03.990 align:start position:0%
hi everyone and welcome back to this
tutorial<00:00:02.800><c> on</c><00:00:02.960><c> building</c><00:00:03.280><c> a</c><00:00:03.439><c> linux</c><00:00:03.840><c> from</c>

00:00:03.990 --> 00:00:04.000 align:start position:0%
tutorial on building a linux from
 

00:00:04.000 --> 00:00:05.749 align:start position:0%
tutorial on building a linux from
scratch<00:00:04.400><c> system</c>
"""

# First cues of human-made subtitles (Stanford CS336 lecture 10), one wrapped over two lines.
MANUAL_VTT = """WEBVTT
Kind: captions
Language: en-US

00:00:04.850 --> 00:00:06.450
So this is lecture 10.

00:00:06.450 --> 00:00:09.770
We're going to take a brief
respite from scaling laws.

00:00:09.770 --> 00:00:12.800
And we're going to
talk about inference.
"""


class ParseVttTests(SimpleTestCase):
    def test_automatic_captions_keep_each_line_once_with_word_times(self):
        segments, words = ns.parse_vtt(AUTO_VTT)
        self.assertEqual([s[2] for s in segments], [
            "hi everyone and welcome back to this",
            "tutorial on building a linux from",
            "scratch system",
        ])
        self.assertEqual(words[0], [0.64, 0.88, "hi"])
        self.assertEqual(words[6], [2.08, 2.31, "this"])
        self.assertEqual(" ".join(w[2] for w in words), " ".join(s[2] for s in segments))
        self.assertTrue(all(a[1] <= b[0] for a, b in zip(segments, segments[1:])))

    def test_human_subtitles_join_wrapped_lines(self):
        segments, words = ns.parse_vtt(MANUAL_VTT)
        self.assertEqual(segments[1], [6.45, 9.77, "We're going to take a brief respite from scaling laws."])
        self.assertEqual(len(segments), 3)
        self.assertEqual(words, [])

    def test_srt_output(self):
        segments, _ = ns.parse_vtt(MANUAL_VTT)
        self.assertTrue(ns.to_srt(segments).startswith("1\n00:00:04,850 --> 00:00:06,450\nSo this is lecture 10.\n\n2\n"))


class PickTrackTests(SimpleTestCase):
    VTT = [{"ext": "json3", "url": "u1"}, {"ext": "vtt", "url": "u2"}]

    def test_human_subtitles_in_original_language_first(self):
        info = {"language": "en", "subtitles": {"de": self.VTT, "en-US": self.VTT, "live_chat": self.VTT},
                "automatic_captions": {"en-orig": self.VTT}}
        self.assertEqual(ns.pick_track(info)["tag"], "en-US")
        self.assertEqual(ns.pick_track(info)["kind"], "manual")

    def test_translated_human_subtitles_lose_to_original_captions(self):
        info = {"language": "en-US", "subtitles": {"zh-Hans": self.VTT},
                "automatic_captions": {"en": self.VTT, "en-orig": self.VTT, "zh-Hans": self.VTT}}
        track = ns.pick_track(info)
        self.assertEqual((track["kind"], track["tag"], track["lang"]), ("auto", "en-orig", "en"))

    def test_japanese_maps_to_vidgo_code(self):
        info = {"language": None, "subtitles": {}, "automatic_captions": {"ja-orig": self.VTT, "en": self.VTT}}
        self.assertEqual(ns.pick_track(info)["lang"], "jp")

    def test_no_original_track_means_asr(self):
        info = {"language": None, "subtitles": {}, "automatic_captions": {"en": self.VTT, "de": self.VTT}}
        self.assertIsNone(ns.pick_track(info))
        self.assertIsNone(ns.pick_track({"language": "fr", "subtitles": {}, "automatic_captions": {"fr-orig": self.VTT}}))


class ChaptersTests(SimpleTestCase):
    def test_chapters_use_the_chapter_panel_format(self):
        info = {"chapters": [{"start_time": 0.0, "end_time": 37.0, "title": "Introduction"},
                             {"start_time": 37, "title": "Creating the list"}, {"title": "no start"}]}
        self.assertEqual(ns.chapters_from_info(info), [
            {"id": "yt-1", "title": "Introduction", "startTime": 0.0, "children": []},
            {"id": "yt-2", "title": "Creating the list", "startTime": 37.0, "children": []},
        ])
        self.assertEqual(ns.chapters_from_info({}), [])


class TaskIntegrationTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def _native(self, vtt, kind, lang):
        segments, words = ns.parse_vtt(vtt)
        return {"kind": kind, "tag": lang, "lang": lang, "segments": segments, "words": words}

    def test_download_stores_chapters_and_subtitle(self):
        video = Video.objects.create(name="lfs-p3 test", url="abc.mp4", video_source="youtube")
        info = {"chapters": [{"start_time": 0, "title": "Introduction"}, {"start_time": 37, "title": "Creating the list"}]}
        _apply_youtube_metadata(video, info, self._native(AUTO_VTT, "auto", "en"))
        video.refresh_from_db()
        self.assertEqual([c["title"] for c in video.chapters], ["Introduction", "Creating the list"])
        self.assertEqual((video.srt_path, video.raw_lang), (f"{video.id}_en.srt", "en"))
        with open(os.path.join(self.media, "saved_srt", video.srt_path), encoding="utf-8") as f:
            self.assertIn("hi everyone and welcome back to this", f.read())
        with open(os.path.join(self.media, "native_subtitles", f"{video.id}.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["kind"], "auto")

    def test_download_without_youtube_data_changes_nothing(self):
        video = Video.objects.create(name="plain", url="def.mp4", video_source="youtube")
        _apply_youtube_metadata(video, {"chapters": []}, None)
        video.refresh_from_db()
        self.assertIsNone(video.srt_path)

    def test_subtitle_task_uses_stored_track(self):
        ns.save(self.media, 7, self._native(AUTO_VTT, "auto", "en"))
        srt, split, detail = _native_transcript(7, "en", True)
        self.assertTrue(split)
        self.assertIn("\nhi\n", srt)  # one word per cue, like ASR word mode
        srt, split, _ = _native_transcript(7, "en", False)
        self.assertFalse(split)
        self.assertIn("\nhi everyone and welcome back to this\n", srt)
        self.assertIsNone(_native_transcript(7, "zh", True))  # other language -> ASR

        ns.save(self.media, 8, self._native(MANUAL_VTT, "manual", "en"))
        srt, split, detail = _native_transcript(8, "en", True)
        self.assertFalse(split)  # human-made lines are already sentences
        self.assertIn("YouTube subtitles", detail)
