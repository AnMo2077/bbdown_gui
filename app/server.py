"""本地 HTTP 服务：托管 Web UI，并提供 JSON 动作接口。

只监听 127.0.0.1，随机端口；所有写操作都经过动作白名单。
"""
import ctypes
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .api import RemoteAPI
from .bbdown import BBDownRunner, mask_secrets
from .qrlogin import BiliQRLogin
from .config import ConfigManager, DEFAULT_CONFIG

APP_VERSION = "2.0"
PUBLISHER = "AnMo_C"
LOG_LIMIT = 800
CORE_FILES = ("BBDown.exe", "curl.exe", "aria2c.exe", "ffmpeg.exe")
MEDIA_EXTENSIONS = (".mp4", ".mkv", ".flv", ".m4a", ".webm", ".ts", ".avi")


def _app_home():
    """数据目录：安装版为 exe 目录，源码运行为项目根目录。"""
    env = os.environ.get("BILIDOWNLOADER_HOME")
    if env:
        return os.path.abspath(env)
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resource_dir():
    """只读资源目录：PyInstaller 下为解压目录，源码为项目根目录。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_MIME_OVERRIDES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json; charset=utf-8",
}


def _read_clipboard():
    """读取 Windows 剪贴板文本（不依赖 tkinter 主循环）。"""
    if os.name != "nt":
        return ""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetClipboardData.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

        if not user32.OpenClipboard(None):
            return ""
        try:
            handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
            if not handle:
                return ""
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                return ""
            try:
                return ctypes.wstring_at(pointer)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:  # noqa: BLE001 - 剪贴板不可用时静默降级
        return ""


def _pick_path(kind):
    """打开系统对话框选择目录或可执行文件。"""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        if kind == "dir":
            return filedialog.askdirectory(title="选择下载目录") or ""
        if kind == "ffmpeg":
            return filedialog.askopenfilename(
                title="选择 ffmpeg.exe",
                filetypes=[("ffmpeg", "ffmpeg.exe"), ("可执行文件", "*.exe")],
            ) or ""
        if kind == "aria2c":
            return filedialog.askopenfilename(
                title="选择 aria2c.exe",
                filetypes=[("aria2c", "aria2c.exe"), ("可执行文件", "*.exe")],
            ) or ""
        return ""
    finally:
        root.destroy()


def _split_windows_args(command):
    """按 Windows 规则拆分命令行（支持引号），不经过 shell。"""
    if os.name != "nt":
        import shlex

        return shlex.split(command)
    try:
        shell32 = ctypes.windll.shell32
        shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
        shell32.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        kernel32 = ctypes.windll.kernel32
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        argc = ctypes.c_int()
        argv = shell32.CommandLineToArgvW(command, ctypes.byref(argc))
        if not argv:
            return []
        try:
            return [argv[i] for i in range(argc.value)]
        finally:
            kernel32.LocalFree(argv)
    except Exception:  # noqa: BLE001
        import shlex

        return shlex.split(command, posix=False)


class AppServer:
    """本地服务：持有配置、下载器、远程公告与日志状态。"""

    def __init__(self):
        self.base_dir = _app_home()
        self.webui_dir = os.path.join(_resource_dir(), "app", "webui")
        self.history_path = os.path.join(self.base_dir, "download_history.json")
        self.log_path = os.path.join(self.base_dir, "BiliDownloader.log")

        self.config = ConfigManager()
        self.runner = BBDownRunner(self.base_dir, lambda: self.config.config)
        self.qr_login = BiliQRLogin(self.base_dir)
        self.api = RemoteAPI()
        self.api.fetch()

        self._lock = threading.RLock()
        self._log = []
        self._log_seq = 0
        self._progress = 0
        self._running = False
        self._last_result = ""
        self._last_output_file = ""
        self._last_output_dir = ""
        self._quit = False
        self._login = {"status": "idle", "qr": "", "message": ""}
        self._probe = {"status": "idle"}
        self._probe_refresh_pending = False
        self._debug_log = []
        self._debug_seq = 0
        self._debug_running = False
        self._history = self._load_history()

        self.httpd = None
        self.port = 0
        self.url = ""

        self._actions = {
            "state": self._action_state,
            "save_config": self._action_save_config,
            "reset_config": self._action_reset_config,
            "start_download": self._action_start_download,
            "stop_download": self._action_stop_download,
            "status": self._action_status,
            "clipboard": self._action_clipboard,
            "pick_dir": self._action_pick_dir,
            "open_path": self._action_open_path,
            "open_output": self._action_open_output,
            "open_url": self._action_open_url,
            "login_start": self._action_login_start,
            "login_check": self._action_login_check,
            "login_status": self._action_login_status,
            "logout": self._action_logout,
            "check_update": self._action_check_update,
            "license": self._action_license,
            "debug_state": self._action_debug_state,
            "debug_enable": self._action_debug_enable,
            "debug_run": self._action_debug_run,
            "debug_stop": self._action_debug_stop,
            "debug_clear": self._action_debug_clear,
            "quit": self._action_quit,
        }

    # ------------------------------------------------------------------ #
    #  生命周期
    # ------------------------------------------------------------------ #
    def start(self, port=0):
        handler = _make_handler(self)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/"
        thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True, name="http-server"
        )
        thread.start()
        try:
            os.makedirs(self._default_work_dir(), exist_ok=True)
        except OSError:
            pass
        self.write_log(f"服务已启动: {self.url}")

        # 启动时若已有登录文件，后台自动跑一次状态检测（不阻塞开窗）
        if os.path.isfile(self.runner.data_path):
            self._probe = {"status": "checking"}
            threading.Thread(
                target=self._auto_probe, daemon=True, name="auto-login-probe"
            ).start()

    def _auto_probe(self):
        try:
            result = self.runner.probe_login("ss1177")
            result["status"] = "done"
        except Exception as exc:  # noqa: BLE001
            result = {"status": "error", "error": str(exc)}
        for line in str(result.get("detail") or "").splitlines():
            self._append_debug(line, "probe")
        with self._lock:
            self._probe = result

    def stop(self):
        try:
            self.qr_login.cancel()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.runner.login_cancel()
        except Exception:  # noqa: BLE001
            pass
        if self._running:
            try:
                self.runner.stop()
            except Exception:  # noqa: BLE001
                pass
        if self.httpd is not None:
            try:
                self.httpd.shutdown()
            except Exception:  # noqa: BLE001
                pass
            try:
                self.httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
            self.httpd = None

    @property
    def quit_requested(self):
        return self._quit

    def write_log(self, message):
        """写启动/错误日志，便于窗口模式下排障。"""
        try:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    #  历史记录
    # ------------------------------------------------------------------ #
    def _load_history(self):
        try:
            with open(self.history_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save_history(self):
        try:
            tmp = self.history_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self._history[:100], handle, ensure_ascii=False, indent=2)
            os.replace(tmp, self.history_path)
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    #  动作实现
    # ------------------------------------------------------------------ #
    def _appearance(self):
        mode = str(self.config.get("appearance_mode", "System"))
        return {"mode": mode, "color": str(self.config.get("theme_color", "blue"))}

    def _announce(self):
        api = self.api
        update_available = False
        if api.prog_ver:
            try:
                update_available = _version_tuple(api.prog_ver) > _version_tuple(APP_VERSION)
            except ValueError:
                update_available = False
        flag = (api.update or "").strip().lower()
        forced_flag = flag == "y"
        return {
            "ad": api.ad,
            "log": api.log,
            "ver": api.prog_ver,
            "latest": api.prog_ver,
            "update": update_available,
            "must_update": update_available and forced_flag,
            "update_flag": flag,
            "url": api.url,
            "fetched": api.fetched,
            "error": api.error,
        }

    def _core_files(self):
        files = []
        for name in CORE_FILES:
            path = os.path.join(self.base_dir, name)
            try:
                size = os.path.getsize(path)
                ok = size > 0
            except OSError:
                size = 0
                ok = False
            files.append({"name": name, "ok": ok, "size": size})
        return files

    def _action_state(self, payload):
        return {
            "version": APP_VERSION,
            "publisher": PUBLISHER,
            "default_dir": self._default_work_dir(),
            "config": dict(self.config.config),
            "appearance": self._appearance(),
            "account": self.runner.account_state(),
            "probe": dict(self._probe),
            "running": self._running,
            "progress": self._progress,
            "history": self._history[:20],
            "announce": self._announce(),
            "core_files": self._core_files(),
            "last_result": self._last_result,
            "last_output": self._last_output_file,
            "last_output_dir": self._last_output_dir,
        }

    def _action_save_config(self, payload):
        patch = payload.get("patch") or {}
        if not isinstance(patch, dict):
            raise ValueError("patch 必须是对象")
        for key, value in patch.items():
            if key in DEFAULT_CONFIG:
                self.config.set(key, value)
        if not self.config.save():
            raise RuntimeError("配置保存失败，请检查目录写权限")
        return {
            "config": dict(self.config.config),
            "appearance": self._appearance(),
        }

    def _action_reset_config(self, payload):
        self.config.config = dict(DEFAULT_CONFIG)
        if not self.config.save():
            raise RuntimeError("配置保存失败，请检查目录写权限")
        return {
            "config": dict(self.config.config),
            "appearance": self._appearance(),
        }

    def _action_start_download(self, payload):
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ValueError("请先填写视频地址")
        if len(url) > 2048 or any(ch in url for ch in "\r\n\t"):
            raise ValueError("视频地址不合法")
        if self._running:
            raise RuntimeError("已有下载任务在运行")

        page = str(payload.get("page") or "").strip()
        quality = str(payload.get("quality") or "").strip()
        overrides = {}
        if page:
            overrides["select_page"] = page
        if quality:
            overrides["dfn_priority"] = quality
        if "video_only" in payload:
            overrides["video_only"] = bool(payload["video_only"])
        if "audio_only" in payload:
            overrides["audio_only"] = bool(payload["audio_only"])

        with self._lock:
            self._log = []
            self._log_seq = 0
            self._progress = 0
            self._last_result = ""
            self._last_output_file = ""
            self._last_output_dir = ""
            self._running = True
        started = time.time()
        self._append_log(f"开始下载: {url}")
        self._append_debug(f"开始下载: {url}", "download")

        def on_log(line):
            self._append_log(line)
            self._append_debug(line, "download")

        def on_progress(percent):
            with self._lock:
                self._progress = int(percent)

        def on_error(message):
            self._append_log(f"错误: {message}")

        def on_done(status, message):
            output_file = ""
            output_dir = ""
            if status == "success":
                output_file, output_dir = self._collect_outputs(started)
            with self._lock:
                self._running = False
                self._last_result = message
                if status == "success":
                    self._progress = 100
                self._last_output_file = output_file
                self._last_output_dir = output_dir
            if status != "stopped":
                self._history.insert(
                    0,
                    {
                        "url": url,
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "success": status == "success",
                    },
                )
                del self._history[100:]
                self._save_history()
            self._append_log(message)

        try:
            self.runner.start(
                url,
                overrides,
                on_log=on_log,
                on_progress=on_progress,
                on_done=on_done,
                on_error=on_error,
            )
        except Exception:
            with self._lock:
                self._running = False
            raise
        return {"message": "已开始下载"}

    def _action_stop_download(self, payload):
        if not self._running:
            return {"message": "当前没有下载任务"}
        self.runner.stop()
        return {"message": "正在停止"}

    def _action_status(self, payload):
        since = payload.get("since")
        with self._lock:
            if isinstance(since, int) and 0 <= since <= len(self._log):
                lines = self._log[since:]
                first = since
            else:
                lines = list(self._log[-200:])
                first = max(0, len(self._log) - len(lines))
            return {
                "running": self._running,
                "progress": self._progress,
                "lines": lines,
                "first": first,
                "seq": len(self._log),
                "result": self._last_result,
                "last_output": self._last_output_file,
                "last_output_dir": self._last_output_dir,
            }

    def _action_clipboard(self, payload):
        return {"text": _read_clipboard()}

    def _action_pick_dir(self, payload):
        kind = str(payload.get("kind") or "dir")
        if kind not in ("dir", "ffmpeg", "aria2c"):
            raise ValueError("未知的选择类型")
        return {"path": _pick_path(kind)}

    def _action_open_path(self, payload):
        path = str(payload.get("path") or "").strip()
        if not path or not os.path.exists(path):
            raise ValueError("路径不存在")
        os.startfile(path)  # noqa: S606 - 仅打开用户选择的本机路径
        return {"message": "已打开"}

    def _default_work_dir(self):
        return os.path.join(self.base_dir, "Downloads")

    def _newest_media(self, root, started):
        """在指定目录内找出开始下载后产生的最新媒体文件。"""
        if not os.path.isdir(root):
            return ""
        best = ""
        best_mtime = 0.0
        base_depth = root.rstrip("\\/").count(os.sep)
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                if dirpath.rstrip("\\/").count(os.sep) - base_depth > 6:
                    dirnames[:] = []
                    continue
                for name in filenames:
                    if not name.lower().endswith(MEDIA_EXTENSIONS):
                        continue
                    path = os.path.join(dirpath, name)
                    try:
                        stat = os.stat(path)
                    except OSError:
                        continue
                    if stat.st_size < 64 * 1024 or stat.st_mtime < started - 10:
                        continue
                    if stat.st_mtime > best_mtime:
                        best_mtime = stat.st_mtime
                        best = path
        except OSError:
            pass
        return best

    @staticmethod
    def _unique_destination(folder, name, is_dir):
        target = os.path.join(folder, name)
        if not os.path.exists(target):
            return target
        if is_dir:
            stem, ext = name, ""
        else:
            stem, ext = os.path.splitext(name)
        for index in range(2, 1000):
            candidate = os.path.join(folder, f"{stem} ({index}){ext}")
            if not os.path.exists(candidate):
                return candidate
        return target

    def _collect_outputs(self, started):
        """把本次下载产生的视频/剧集文件夹移动到程序目录的 Downloads，并打开它。"""
        source = str(self.config.get("work_dir") or "").strip() or self._default_work_dir()
        source_abs = os.path.abspath(source)
        target = str(self.config.get("output_dir") or "").strip() or self._default_work_dir()
        target = os.path.abspath(target)
        try:
            os.makedirs(target, exist_ok=True)
        except OSError:
            return "", source_abs
        target_abs = os.path.abspath(target)
        moved = []
        if source_abs != target_abs and os.path.isdir(source_abs):
            try:
                names = sorted(os.listdir(source_abs))
            except OSError:
                names = []
            for name in names:
                if name.startswith("."):
                    continue
                path = os.path.join(source_abs, name)
                if os.path.abspath(path) == target_abs:
                    continue
                try:
                    if os.path.isfile(path):
                        if not name.lower().endswith(MEDIA_EXTENSIONS):
                            continue
                        stat = os.stat(path)
                        if stat.st_size < 64 * 1024 or stat.st_mtime < started - 10:
                            continue
                        destination = self._unique_destination(target_abs, name, False)
                        shutil.move(path, destination)
                        moved.append(destination)
                    elif os.path.isdir(path):
                        if not self._newest_media(path, started):
                            continue
                        destination = self._unique_destination(target_abs, name, True)
                        shutil.move(path, destination)
                        moved.append(destination)
                except OSError:
                    continue
        final = ""
        for destination in moved:
            if os.path.isfile(destination):
                final = destination
                break
            newest = self._newest_media(destination, started)
            if newest:
                final = newest
                break
        if not final:
            final = self._newest_media(target_abs, started)
        try:
            os.startfile(target_abs)  # noqa: S606 - 仅打开下载目录
        except OSError:
            pass
        return final, target_abs

    def _action_open_output(self, payload):
        file_path = self._last_output_file
        if file_path and os.path.isfile(file_path):
            subprocess.Popen(["explorer.exe", f"/select,{file_path}"])
            return {"message": "已在资源管理器中定位文件"}
        folder = self._last_output_dir or str(self.config.get("work_dir") or "").strip() or self._default_work_dir()
        if os.path.isdir(folder):
            os.startfile(folder)  # noqa: S606 - 仅打开下载目录
            return {"message": "已打开下载目录"}
        raise RuntimeError("找不到下载目录")

    def _action_open_url(self, payload):
        url = str(payload.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("只允许打开 http/https 链接")
        webbrowser.open(url)
        return {"message": "已在浏览器打开"}

    def _action_login_start(self, payload):
        """优先使用自实现的 B 站扫码登录（BBDown 的 login 已取不到 SESSDATA）。"""
        data = self.qr_login.start()
        with self._lock:
            self._login = {
                "status": data["status"],
                "qr": data["qr"],
                "message": data["message"],
            }
            # 保留上次的会员等级展示；新登录成功后再重新检测
            self._probe_refresh_pending = True
        return data

    def _action_login_check(self, payload):
        """用 ss1177 做一次仅解析，验证当前登录凭证是否可用。"""
        result = self.runner.probe_login("ss1177")
        result["status"] = "done"
        for line in str(result.get("detail") or "").splitlines():
            self._append_debug(line, "probe")
        with self._lock:
            self._probe = result
            self._login["message"] = (
                "登录状态正常" if result["logged_in"] else "未登录或凭证已失效"
            )
        return result

    def _action_login_status(self, payload):
        snapshot = self.qr_login.snapshot()
        with self._lock:
            if snapshot["status"] != "idle":
                self._login = dict(snapshot)
            data = dict(self._login)
            data["probe"] = dict(self._probe)
        data["account"] = self.runner.account_state()

        # 扫码成功且这次登录还没检测过时，自动补一次会员等级检测
        if data.get("status") == "success" and self._probe_refresh_pending:
            self._probe_refresh_pending = False
            self._probe = {"status": "checking"}
            threading.Thread(target=self._auto_probe, daemon=True).start()
        return data

    def _action_logout(self, payload):
        self.runner.logout()
        self.qr_login.cancel()
        self.qr_login.status = "idle"
        self.qr_login.qr = ""
        self.qr_login.message = ""
        with self._lock:
            self._login = {"status": "idle", "qr": "", "message": ""}
            self._probe = {"status": "idle"}
        return {"account": self.runner.account_state()}

    def _action_check_update(self, payload):
        self.api.fetch()
        return {"announce": self._announce()}

    def _action_license(self, payload):
        """代理拉取远程许可文本，避免前端跨域。"""
        request = urllib.request.Request(
            RemoteAPI.LICENSE_URL,
            headers={"User-Agent": RemoteAPI.USER_AGENT, "Cache-Control": "no-cache"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read(512 * 1024)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"获取许可文本失败：{exc}") from exc
        return {"text": RemoteAPI._decode(raw)}

    # ------------------------------------------------------------------ #
    #  开发者调试
    # ------------------------------------------------------------------ #
    def _append_debug(self, line, source="bbdown"):
        text = f"[{source}] {mask_secrets(str(line))}"
        with self._lock:
            self._debug_log.append(text)
            self._debug_seq += 1
            if len(self._debug_log) > 5000:
                del self._debug_log[:1000]

    def _action_debug_enable(self, payload):
        """仅在本次运行内启用调试，不写入配置文件。"""
        with self._lock:
            self.config.config["dev_mode"] = True
        return {"enabled": True}

    def _action_debug_state(self, payload):
        if not self.config.get_bool("dev_mode"):
            return {"enabled": False, "lines": [], "first": 0, "seq": 0, "running": False}
        since = payload.get("since")
        with self._lock:
            if isinstance(since, int) and 0 <= since <= len(self._debug_log):
                lines = self._debug_log[since:]
                first = since
            else:
                lines = list(self._debug_log[-300:])
                first = max(0, len(self._debug_log) - len(lines))
            return {
                "enabled": True,
                "lines": lines,
                "first": first,
                "seq": len(self._debug_log),
                "running": self._debug_running,
            }

    def _action_debug_run(self, payload):
        if not self.config.get_bool("dev_mode"):
            raise RuntimeError("调试模式未开启")
        command = str(payload.get("command") or "").strip()
        if not command:
            raise ValueError("请输入要传给 BBDown 的参数")
        args = _split_windows_args(command)
        if args and args[0].lower() in ("bbdown", "bbdown.exe"):
            args = args[1:]
        if not args:
            raise ValueError("参数为空")

        with self._lock:
            if self._debug_running:
                raise RuntimeError("已有调试命令在运行")
            self._debug_running = True
            self._debug_log.append(f"$ BBDown.exe {' '.join(args)}")
            self._debug_seq += 1

        def on_log(line):
            self._append_debug(line, "out")

        def on_done(code, message):
            with self._lock:
                self._debug_running = False
                suffix = f" {message}" if message else ""
                self._debug_log.append(f"$ 退出码 {code}{suffix}")
                self._debug_seq += 1

        try:
            self.runner.run_raw(args, on_log=on_log, on_done=on_done)
        except Exception:
            with self._lock:
                self._debug_running = False
            raise
        return {"message": "已开始执行"}

    def _action_debug_stop(self, payload):
        if not self.config.get_bool("dev_mode"):
            raise RuntimeError("调试模式未开启")
        if not self._debug_running:
            return {"message": "当前没有调试任务"}
        self.runner.stop()
        return {"message": "正在停止"}

    def _action_debug_clear(self, payload):
        if not self.config.get_bool("dev_mode"):
            raise RuntimeError("调试模式未开启")
        with self._lock:
            self._debug_log = []
            self._debug_seq = 0
        return {"message": "已清空"}

    def _action_quit(self, payload):
        self._quit = True
        threading.Timer(0.4, self.stop).start()
        return {"message": "正在退出"}

    # ------------------------------------------------------------------ #
    #  日志缓冲
    # ------------------------------------------------------------------ #
    def _append_log(self, line):
        text = mask_secrets(str(line))
        with self._lock:
            self._log.append(text)
            self._log_seq += 1
            if len(self._log) > LOG_LIMIT:
                del self._log[: len(self._log) - LOG_LIMIT]

    # ------------------------------------------------------------------ #
    #  请求入口
    # ------------------------------------------------------------------ #
    def handle_action(self, payload):
        action = str(payload.get("action") or "")
        handler = self._actions.get(action)
        if handler is None:
            return {"ok": False, "error": f"未知操作: {action}"}
        try:
            result = handler(payload) or {}
            return {"ok": True, **result}
        except Exception as exc:  # noqa: BLE001
            self.write_log(f"操作 {action} 失败: {exc}\n{traceback.format_exc()}")
            return {"ok": False, "error": str(exc)}

    def serve_static(self, path):
        """返回 (status, content_type, body)；只允许 webui 目录内文件。"""
        relative = path.lstrip("/")
        if relative in ("", "index.html"):
            relative = "index.html"
        target = os.path.abspath(os.path.join(self.webui_dir, relative))
        if os.path.commonpath([target, os.path.abspath(self.webui_dir)]) != os.path.abspath(self.webui_dir):
            return 403, "text/plain; charset=utf-8", b"Forbidden"
        if not os.path.isfile(target):
            if relative == "favicon.ico":
                return 204, "image/x-icon", b""
            return 404, "text/plain; charset=utf-8", b"Not Found"
        extension = os.path.splitext(target)[1].lower()
        content_type = _MIME_OVERRIDES.get(extension)
        if content_type is None:
            content_type = mimetypes.guess_type(target)[0] or "application/octet-stream"
        try:
            with open(target, "rb") as handle:
                body = handle.read()
        except OSError:
            return 500, "text/plain; charset=utf-8", b"Read Error"
        return 200, content_type, body


def _version_tuple(text):
    parts = []
    for chunk in str(text).replace("-", ".").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def _make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BiliDownloader/2.0"

        def log_message(self, fmt, *args):  # noqa: A003 - 静默访问日志
            return

        def _allowed_host(self):
            host = (self.headers.get("Host") or "").lower()
            return host in (f"127.0.0.1:{app.port}", f"localhost:{app.port}")

        def _allowed_origin(self):
            origin = self.headers.get("Origin")
            if not origin:
                return True
            return origin in (f"http://127.0.0.1:{app.port}", f"http://localhost:{app.port}")

        def _send(self, status, content_type, body, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if not self._allowed_host():
                self._send(403, "text/plain; charset=utf-8", b"Forbidden")
                return
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                self._send(404, "application/json; charset=utf-8", b'{"ok":false,"error":"not found"}')
                return
            status, content_type, body = app.serve_static(path)
            self._send(status, content_type, body)

        def do_POST(self):  # noqa: N802
            if not self._allowed_host() or not self._allowed_origin():
                self._send(403, "application/json; charset=utf-8", b'{"ok":false,"error":"forbidden"}')
                return
            if urlparse(self.path).path != "/api/action":
                self._send(404, "application/json; charset=utf-8", b'{"ok":false,"error":"not found"}')
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > 1024 * 1024:
                self._send(400, "application/json; charset=utf-8", b'{"ok":false,"error":"bad length"}')
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError
            except (ValueError, UnicodeDecodeError):
                self._send(400, "application/json; charset=utf-8", b'{"ok":false,"error":"bad json"}')
                return
            result = app.handle_action(payload)
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)

    return Handler
