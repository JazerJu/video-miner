import tempfile
from pathlib import Path

from django.test import TestCase

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
