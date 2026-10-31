"""BiliDownloader 回归测试（标准库 unittest，无外部依赖）。

运行：py tests/test_app.py  或  python -m unittest discover -s tests -v
"""
import http.client
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TEMP_DIR = tempfile.gettempdir()


def _temp_path(name):
    """测试临时文件放在系统临时目录（平铺，不建子目录）。"""
    return os.path.join(TEMP_DIR, f"bd_unit_{os.getpid()}_{name}")


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

from app.api import RemoteAPI  # noqa: E402
from app.bbdown import BBDownRunner, decode_line, mask_secrets  # noqa: E402
from app.config import DEFAULT_CONFIG, ConfigManager  # noqa: E402
from app.server import APP_VERSION, AppServer, _version_tuple  # noqa: E402


def _post(server, payload, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=8)
    body = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    connection.request("POST", "/api/action", body, request_headers)
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    return response.status, json.loads(raw.decode("utf-8"))


def _get(server, path, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=8)
    connection.request("GET", path, headers=headers or {})
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, response.getheader("Content-Type"), data


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.path = _temp_path("config.json")
        _remove(self.path)

    def tearDown(self):
        _remove(self.path)

    def test_defaults_merge(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"encoding_priority": "avc", "unknown_key": 1}, handle)
        manager = ConfigManager(self.path)
        self.assertEqual(manager.get("encoding_priority"), "avc")
        self.assertEqual(manager.get("use_aria2c"), DEFAULT_CONFIG["use_aria2c"])
        # 未知键原样保留，便于向前兼容
        self.assertEqual(manager.get("unknown_key"), 1)

    def test_save_roundtrip(self):
        manager = ConfigManager(self.path)
        manager.set("work_dir", "D:/videos")
        self.assertTrue(manager.save())
        again = ConfigManager(self.path)
        self.assertEqual(again.get("work_dir"), "D:/videos")


class ApiTests(unittest.TestCase):
    def test_parse(self):
        text = "prog_ver=2.0\nad=hello\nupdate=y\nurl=https://example.com/"
        self.assertEqual(RemoteAPI._parse(text, "prog_ver="), "2.0")
        self.assertEqual(RemoteAPI._parse(text, "url="), "https://example.com/")
        self.assertEqual(RemoteAPI._parse(text, "missing="), "")

    def test_unescape_and_decode(self):
        self.assertEqual(RemoteAPI._unescape("a\\nb"), "a\nb")
        self.assertEqual(RemoteAPI._decode("公告".encode("gbk")), "公告")
        self.assertEqual(RemoteAPI._decode("\ufeffhi".encode("utf-8")), "hi")


class BBDownTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(DEFAULT_CONFIG)
        self.runner = BBDownRunner(tempfile.gettempdir(), lambda: self.config)

    def test_mask_secrets(self):
        text = "cookie: SESSDATA=abcdef123456; bili_jct=deadbeef"
        masked = mask_secrets(text)
        self.assertIn("SESSDATA=abcd***", masked)
        self.assertNotIn("abcdef123456", masked)

    def test_decode_line(self):
        self.assertEqual(decode_line("中文".encode("utf-8")), "中文")
        self.assertEqual(decode_line("中文".encode("gbk")), "中文")

    def test_build_args_basic(self):
        self.config.update(
            encoding_priority="hevc,avc",
            use_aria2c=True,
            aria2c_args="-x16",
            skip_ai=True,
            force_http=True,
            work_dir="D:/out",
        )
        args = self.runner.build_args("BV1xx411c7mD")
        self.assertEqual(args[0], "BV1xx411c7mD")
        self.assertIn("--use-aria2c", args)
        self.assertIn("--aria2c-args", args)
        self.assertIn("-e", args)
        self.assertIn("hevc,avc", args)
        self.assertIn("D:/out", args)
        self.assertNotIn("--video-only", args)

    def test_build_args_overrides(self):
        args = self.runner.build_args("BV1xx", {"select_page": "3", "video_only": True})
        self.assertIn("-p", args)
        self.assertIn("3", args)
        self.assertIn("--video-only", args)

    def test_progress_parse(self):
        self.assertEqual(BBDownRunner._parse_progress("下载中 45.5%"), 45)
        self.assertEqual(BBDownRunner._parse_progress("[====    ]"), 10)
        self.assertIsNone(BBDownRunner._parse_progress("https://x/%20"))
        self.assertEqual(BBDownRunner._parse_progress("120%"), 100)

    def test_describe_failure(self):
        message = BBDownRunner._describe_failure(["net_http_ssl_connection_failed"], 1)
        self.assertIn("HTTPS", message)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.config_path = _temp_path("runtime_config.json")
        self.history_path = _temp_path("history.json")
        self.log_path = _temp_path("runtime.log")
        for path in (self.config_path, self.history_path, self.log_path):
            _remove(path)

        with mock.patch.object(RemoteAPI, "fetch", lambda self, on_done=None: None):
            self.server = AppServer()
        self.server.config = ConfigManager(self.config_path)
        self.server.config.config = dict(DEFAULT_CONFIG)
        self.server.config.save()
        self.server.history_path = self.history_path
        self.server.log_path = self.log_path
        self.server._history = []
        self.server.start(0)

    def tearDown(self):
        self.server.stop()
        for path in (self.config_path, self.history_path, self.log_path):
            _remove(path)

    def test_state(self):
        status, data = _post(self.server, {"action": "state"})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["version"], APP_VERSION)
        self.assertEqual(data["publisher"], "AnMo_C")
        self.assertIn("config", data)
        self.assertIn("account", data)
        self.assertEqual(len(data["core_files"]), 4)
        names = {item["name"] for item in data["core_files"]}
        self.assertEqual(names, {"BBDown.exe", "curl.exe", "aria2c.exe", "ffmpeg.exe"})

    def test_announce_update_flags(self):
        api = self.server.api
        api.fetched = True
        api.prog_ver = "2.1"
        api.update = "y"
        api.url = "https://example.com/new"
        announce = self.server._announce()
        self.assertTrue(announce["update"])
        self.assertTrue(announce["must_update"])

        api.update = "n"
        announce = self.server._announce()
        self.assertTrue(announce["update"])
        self.assertFalse(announce["must_update"])

        api.update = ""
        announce = self.server._announce()
        self.assertTrue(announce["update"])
        self.assertFalse(announce["must_update"])

        api.prog_ver = "2.0"
        api.update = "y"
        announce = self.server._announce()
        self.assertFalse(announce["update"])
        self.assertFalse(announce["must_update"])

    def test_save_and_reset_config(self):
        status, data = _post(
            self.server, {"action": "save_config", "patch": {"work_dir": "D:/videos"}}
        )
        self.assertTrue(data["ok"])
        self.assertEqual(data["config"]["work_dir"], "D:/videos")

        status, data = _post(self.server, {"action": "reset_config"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["config"]["work_dir"], DEFAULT_CONFIG["work_dir"])

    def test_unknown_action(self):
        status, data = _post(self.server, {"action": "rm_rf"})
        self.assertFalse(data["ok"])
        self.assertIn("未知操作", data["error"])

    def test_start_download_requires_url(self):
        status, data = _post(self.server, {"action": "start_download", "url": ""})
        self.assertFalse(data["ok"])
        self.assertIn("视频地址", data["error"])

    def test_status_shape(self):
        status, data = _post(self.server, {"action": "status", "since": 0})
        self.assertTrue(data["ok"])
        for key in ("running", "progress", "lines", "seq"):
            self.assertIn(key, data)

    def test_static_index(self):
        status, content_type, body = _get(self.server, "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn(b"BiliDownloader", body)

    def test_static_js(self):
        status, content_type, body = _get(self.server, "/app.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", content_type)
        self.assertGreater(len(body), 1000)

    def test_path_traversal_blocked(self):
        status, _, _ = _get(self.server, "/../gui.py")
        self.assertEqual(status, 403)

    def test_host_check(self):
        status, _ = _post(
            self.server,
            {"action": "state"},
            headers={"Host": "evil.example.com"},
        )
        self.assertEqual(status, 403)

    def test_open_url_scheme(self):
        status, data = _post(self.server, {"action": "open_url", "url": "file:///C:/Windows"})
        self.assertFalse(data["ok"])


class VersionTests(unittest.TestCase):
    def test_version_tuple(self):
        self.assertGreater(_version_tuple("2.1"), _version_tuple("2.0"))
        self.assertEqual(_version_tuple("v2.0.0"), (2, 0, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
