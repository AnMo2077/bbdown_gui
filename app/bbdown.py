"""BBDown 封装：下载、登录、进度解析。

设计要点：
- 只通过命令行调用 BBDown.exe，不依赖第三方 Python 包；
- 子进程输出按 UTF-8 / GBK 逐行自适应解码，避免中文乱码；
- 所有可能出现在日志里的 cookie / token 都经过掩码处理。
"""
import base64
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_QR_BLOCK_RE = re.compile(r"^[\u2588\u2580\u2584\u258c\u2590\u2591\u2592\u2593\s]+$")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_SECRET_RE = re.compile(
    r"(SESSDATA|bili_jct|DedeUserID__ckMd5|access_token|refresh_token)=([^;\s'\"]+)",
    re.IGNORECASE,
)


def mask_secrets(text: str) -> str:
    """把日志中的凭证值替换为 ***，避免写进界面或日志文件。"""
    def _replace(match):
        value = match.group(2)
        head = value[:4]
        return f"{match.group(1)}={head}***"

    return _SECRET_RE.sub(_replace, text or "")


def decode_line(raw: bytes) -> str:
    """BBDown 是 .NET 程序，控制台编码随系统变化，这里做自适应。"""
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class BBDownRunner:
    """封装 BBDown.exe 的下载与登录流程。"""

    def __init__(self, base_dir, config_getter):
        self.base_dir = os.path.abspath(base_dir)
        self.temp_dir = self._pick_runtime_dir()
        self.get_config = config_getter
        self.process = None
        self.is_running = False
        self._stop_requested = False
        self._lock = threading.Lock()

    def _pick_runtime_dir(self):
        """选一个真正可写的运行目录（二维码、System.CommandLine 哨兵文件）。

        优先项目内 .bbdown-tmp；程序目录只读时（例如装在 Program Files）
        退到 %LOCALAPPDATA%\\BiliDownloader\\tmp，再退到系统临时目录。
        """
        candidates = [
            os.path.join(self.base_dir, ".bbdown-tmp"),
            os.path.join(
                os.environ.get("LOCALAPPDATA") or self.base_dir,
                "BiliDownloader",
                "tmp",
            ),
            tempfile.gettempdir(),
        ]
        for path in candidates:
            try:
                os.makedirs(path, exist_ok=True)
                probe = os.path.join(path, ".write-probe")
                with open(probe, "w", encoding="utf-8") as handle:
                    handle.write("x")
                os.remove(probe)
                # BBDown 启动时 System.CommandLine 会创建该目录并写入注册文件；
                # 预先建好可以绕开某些环境下的“创建目录被拒”。
                try:
                    os.makedirs(
                        os.path.join(path, "system-commandline-sentinel-files"),
                        exist_ok=True,
                    )
                except OSError:
                    pass
                return path
            except OSError:
                continue
        return self.base_dir

    def _child_env(self):
        """BBDown 的 System.CommandLine 需要可写的哨兵目录。

        统一把 TEMP/TMP 指向项目内的 .bbdown-tmp，避免用户临时目录
        不可写或被安全软件拦截时解析失败。
        """
        env = os.environ.copy()
        env.setdefault("DOTNET_CLI_UI_LANGUAGE", "zh-Hans")
        try:
            os.makedirs(self.temp_dir, exist_ok=True)
        except OSError:
            return env
        env["TEMP"] = self.temp_dir
        env["TMP"] = self.temp_dir
        return env

    # ------------------------------------------------------------------ #
    #  路径与参数
    # ------------------------------------------------------------------ #
    @property
    def exe_path(self):
        return os.path.join(self.base_dir, "BBDown.exe")

    @property
    def data_path(self):
        return os.path.join(self.base_dir, "BBDown.data")

    def available(self):
        return os.path.isfile(self.exe_path)

    def build_args(self, url, overrides=None):
        """按配置拼装 BBDown 命令行（不含 exe 本身）。"""
        cfg = dict(self.get_config() or {})
        if overrides:
            cfg.update({k: v for k, v in overrides.items() if v is not None})

        args = [url]

        page = str(cfg.get("select_page") or "").strip()
        if page:
            args += ["-p", page]

        encoding = str(cfg.get("encoding_priority") or "").strip()
        if encoding:
            args += ["-e", encoding]

        dfn = str(cfg.get("dfn_priority") or "").strip()
        if dfn:
            args += ["-q", dfn]

        work_dir = str(cfg.get("work_dir") or "").strip()
        args += ["--work-dir", work_dir or os.path.join(self.base_dir, "Downloads")]

        ffmpeg_path = str(cfg.get("ffmpeg_path") or "").strip()
        if ffmpeg_path:
            args += ["--ffmpeg-path", ffmpeg_path]

        aria2c_path = str(cfg.get("aria2c_path") or "").strip()
        if aria2c_path:
            args += ["--aria2c-path", aria2c_path]

        if cfg.get("use_aria2c"):
            args.append("--use-aria2c")
            aria2c_args = str(cfg.get("aria2c_args") or "").strip()
            if aria2c_args:
                args += ["--aria2c-args", aria2c_args]

        if cfg.get("multi_thread", True):
            args.append("--multi-thread")

        if cfg.get("video_only"):
            args.append("--video-only")
        if cfg.get("audio_only"):
            args.append("--audio-only")

        if cfg.get("download_danmaku"):
            args.append("--download-danmaku")
        if cfg.get("skip_mux"):
            args.append("--skip-mux")
        if cfg.get("skip_subtitle"):
            args.append("--skip-subtitle")
        if cfg.get("skip_cover"):
            args.append("--skip-cover")
        if cfg.get("skip_ai", True):
            args.append("--skip-ai")
        if cfg.get("save_archives"):
            args.append("--save-archives-to-file")

        if cfg.get("use_tv_api"):
            args.append("--use-tv-api")
        if cfg.get("use_app_api"):
            args.append("--use-app-api")
        if cfg.get("use_intl_api"):
            args.append("--use-intl-api")

        if cfg.get("force_http", True):
            args.append("--force-http")
        if cfg.get("allow_pcdn"):
            args.append("--allow-pcdn")

        if cfg.get("video_ascending"):
            args.append("--video-ascending")
        if cfg.get("audio_ascending"):
            args.append("--audio-ascending")

        file_pattern = str(cfg.get("file_pattern") or "").strip()
        if file_pattern:
            args += ["--file-pattern", file_pattern]

        multi_pattern = str(cfg.get("multi_file_pattern") or "").strip()
        if multi_pattern:
            args += ["--multi-file-pattern", multi_pattern]

        delay = str(cfg.get("delay_per_page") or "").strip()
        if delay and delay != "0":
            args += ["--delay-per-page", delay]

        for key, flag in (
            ("host", "--host"),
            ("ep_host", "--ep-host"),
            ("area", "--area"),
            ("language", "--language"),
            ("user_agent", "--user-agent"),
            ("upos_host", "--upos-host"),
        ):
            value = str(cfg.get(key) or "").strip()
            if value:
                args += [flag, value]

        cookie = str(cfg.get("cookie") or "").strip()
        if cookie:
            args += ["--cookie", cookie]

        token = str(cfg.get("access_token") or "").strip()
        if token:
            args += ["--access-token", token]

        return args

    # ------------------------------------------------------------------ #
    #  下载
    # ------------------------------------------------------------------ #
    def start(self, url, overrides=None, on_log=None, on_progress=None,
              on_done=None, on_error=None):
        """后台线程启动下载；重复调用会被拒绝。"""
        with self._lock:
            if self.is_running:
                raise RuntimeError("已有下载任务在运行")
            if not self.available():
                raise RuntimeError("未找到 BBDown.exe，请确认程序目录完整")
            self.is_running = True
            self._stop_requested = False

        args = self.build_args(url, overrides)

        def _worker():
            return_code = None
            lines = []
            try:
                env = self._child_env()
                self.process = subprocess.Popen(
                    [self.exe_path] + args,
                    cwd=self.base_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    creationflags=CREATE_NO_WINDOW,
                )
                last_emit = 0.0
                for raw in iter(self.process.stdout.readline, b""):
                    line = decode_line(raw).rstrip("\r\n")
                    if not line:
                        continue
                    line = mask_secrets(line)
                    lines.append(line)
                    if len(lines) > 400:
                        del lines[:100]
                    if on_log:
                        on_log(line)
                    now = time.time()
                    if on_progress and now - last_emit > 0.15:
                        percent = self._parse_progress(line)
                        if percent is not None:
                            on_progress(percent)
                            last_emit = now
                self.process.wait()
                return_code = self.process.returncode
            except Exception as exc:  # noqa: BLE001
                if on_error and not self._stop_requested:
                    on_error(str(exc))
                return_code = -1
            finally:
                stopped = self._stop_requested
                self.is_running = False
                self.process = None
                self._stop_requested = False

                if stopped:
                    if on_done:
                        on_done("stopped", "已停止下载")
                elif return_code == 0:
                    if on_done:
                        on_done("success", "下载完成")
                else:
                    message = self._describe_failure(lines, return_code)
                    if on_done:
                        on_done("failed", message)

        threading.Thread(target=_worker, daemon=True, name="bbdown-download").start()

    def run_raw(self, args, on_log=None, on_done=None):
        """用给定参数直接运行 BBDown（调试控制台用，不经过参数拼装）。"""
        with self._lock:
            if self.is_running:
                raise RuntimeError("已有 BBDown 任务在运行")
            self.is_running = True
            self._stop_requested = False

        def _worker():
            code = None
            stopped = False
            try:
                self.process = subprocess.Popen(
                    [self.exe_path] + [str(a) for a in args],
                    cwd=self.base_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=self._child_env(),
                    creationflags=CREATE_NO_WINDOW,
                )
                for raw in iter(self.process.stdout.readline, b""):
                    line = decode_line(raw).rstrip("\r\n")
                    if line and on_log:
                        on_log(mask_secrets(line))
                self.process.wait()
                code = self.process.returncode
            except Exception as exc:  # noqa: BLE001
                if on_done:
                    on_done(-1, str(exc))
                return
            finally:
                stopped = self._stop_requested
                self.is_running = False
                self.process = None
                self._stop_requested = False
            if on_done:
                on_done(code, "stopped" if stopped else "")

        threading.Thread(target=_worker, daemon=True, name="bbdown-raw").start()

    def stop(self):
        """请求停止当前下载。"""
        self._stop_requested = True
        process = self.process
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass

    # ------------------------------------------------------------------ #
    #  登录
    # ------------------------------------------------------------------ #
    def account_state(self):
        """根据 BBDown.data 判断登录状态。"""
        if not os.path.isfile(self.data_path):
            return {"logged_in": False, "mid": "", "hint": "未登录"}
        try:
            with open(self.data_path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            return {"logged_in": False, "mid": "", "hint": "无法读取登录信息"}
        if "SESSDATA=" not in text:
            return {"logged_in": False, "mid": "", "hint": "登录信息不完整"}
        match = re.search(r"DedeUserID=(\d+)", text)
        return {
            "logged_in": True,
            "mid": match.group(1) if match else "",
            "hint": "已登录",
        }

    def probe_login(self, url="ss1177", timeout=90):
        """用一次仅解析验证当前凭证是否可用。"""
        if not self.available():
            raise RuntimeError("未找到 BBDown.exe")
        try:
            completed = subprocess.run(
                [self.exe_path, url, "-info"],
                cwd=self.base_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=self._child_env(),
                timeout=timeout,
                creationflags=CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            return {
                "logged_in": False,
                "account": "",
                "parsed": False,
                "detail": "解析超时，请检查网络后重试",
                "returncode": None,
            }

        lines = [decode_line(raw).rstrip("\r\n") for raw in (completed.stdout or b"").splitlines()]
        text = "\n".join(lines)

        data_text = ""
        if os.path.isfile(self.data_path):
            try:
                with open(self.data_path, "r", encoding="utf-8", errors="replace") as handle:
                    data_text = handle.read()
            except OSError:
                data_text = ""
        has_cookie = "SESSDATA=" in data_text
        uid_match = re.search(r"DedeUserID=(\d+)", data_text)
        uid = uid_match.group(1) if uid_match else ""

        # BBDown 只在 cookie 无效时打印“尚未登录”；
        # 有效时只打印“加载本地cookie…”然后继续解析。
        logged_in = has_cookie and ("尚未登录" not in text)
        account = f"UID {uid}" if (logged_in and uid) else ""

        login_line = ""
        for line in lines:
            if "尚未登录" in line:
                login_line = line
                break
        if not login_line and logged_in:
            login_line = f"登录状态正常：UID {uid}" if uid else "登录状态正常（本地凭证有效）"

        parsed = ("视频标题" in text) or ("共计" in text) or ("视频流" in text)

        # 从流列表里取最高画质，用于判定会员等级
        heights = []
        for line in lines:
            for match in re.finditer(r"\[(8K|4K|\d{3,4}P)\b", line):
                token = match.group(1)
                if token.upper() == "8K":
                    heights.append(4320)
                elif token.upper() == "4K":
                    heights.append(2160)
                else:
                    try:
                        heights.append(int(token[:-1]))
                    except ValueError:
                        pass
        max_height = max(heights) if heights else 0
        if max_height >= 4320:
            max_label = "8K"
        elif max_height >= 2160:
            max_label = "4K"
        elif max_height > 0:
            max_label = f"{max_height}P"
        else:
            max_label = ""

        # 收集去重后的清晰度标签（按高度从高到低）
        qualities = []
        for line in lines:
            match = re.search(r"\[((?:8K|4K|\d{3,4}P)[^\]]*)\]", line)
            if not match:
                continue
            label = match.group(1).strip()
            if label not in qualities:
                qualities.append(label)

        def _label_height(label):
            token = label.split(" ", 1)[0]
            if token.upper() == "8K":
                return 4320
            if token.upper() == "4K":
                return 2160
            try:
                return int(token[:-1])
            except ValueError:
                return 0

        qualities.sort(key=_label_height, reverse=True)

        if max_height >= 2160:
            membership = "大会员"
        elif max_height >= 720:
            membership = "普通用户"
        else:
            membership = "未登录"

        # 去掉带签名的超长 URL，其余完整保留
        url_count = sum(1 for line in lines if "://" in line)
        detail_lines = [line for line in lines if "://" not in line and line != login_line]
        if url_count:
            detail_lines.append(f"…（已略过 {url_count} 条带签名的下载链接）")
        head = [login_line] if login_line else []
        return {
            "logged_in": bool(logged_in),
            "account": mask_secrets(account) if account else "",
            "login_line": mask_secrets(login_line),
            "parsed": bool(parsed),
            "max_height": max_height,
            "max_label": max_label,
            "membership": membership,
            "qualities": qualities,
            "detail": "\n".join(head + detail_lines),
            "returncode": completed.returncode,
        }

    def login_start(self, on_qr=None, on_log=None, on_done=None):
        """启动扫码登录，过程中回调二维码 data URL。"""
        if not self.available():
            raise RuntimeError("未找到 BBDown.exe")
        if os.path.isfile(self.data_path):
            try:
                os.remove(self.data_path)
            except OSError:
                pass

        qr_dir = self.temp_dir
        try:
            os.makedirs(qr_dir, exist_ok=True)
        except OSError:
            qr_dir = self.base_dir
        qr_path = os.path.join(qr_dir, "qrcode.png")
        for stale in (qr_path, os.path.join(self.base_dir, "qrcode.png")):
            try:
                if os.path.isfile(stale):
                    os.remove(stale)
            except OSError:
                pass

        def _worker():
            process = None
            try:
                process = subprocess.Popen(
                    [self.exe_path, "login"],
                    cwd=qr_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=self._child_env(),
                    creationflags=CREATE_NO_WINDOW,
                )
                self._login_process = process
                recent = []

                def _pump():
                    for raw in iter(process.stdout.readline, b""):
                        line = decode_line(raw).rstrip("\r\n")
                        if not line:
                            continue
                        # BBDown 会把二维码用方块字符打印到控制台，过滤掉避免刷屏
                        if _QR_BLOCK_RE.match(_ANSI_RE.sub("", line)):
                            continue
                        recent.append(line)
                        if on_log:
                            on_log(mask_secrets(line))

                pump = threading.Thread(target=_pump, daemon=True)
                pump.start()

                deadline = time.time() + 180
                qr_sent = False
                while time.time() < deadline and process.poll() is None:
                    if not qr_sent and os.path.isfile(qr_path):
                        try:
                            with open(qr_path, "rb") as handle:
                                data = handle.read()
                            if data:
                                encoded = base64.b64encode(data).decode("ascii")
                                if on_qr:
                                    on_qr("data:image/png;base64," + encoded)
                                qr_sent = True
                        except OSError:
                            pass
                    time.sleep(0.25)

                if process.poll() is None:
                    try:
                        process.kill()
                    except OSError:
                        pass
                    if on_done:
                        on_done(False, "登录超时，请重试")
                    return

                return_code = process.returncode

                # BBDown 在 cwd 下保存登录凭证；统一挪回程序目录
                produced = os.path.join(qr_dir, "BBDown.data")
                if os.path.isfile(produced) and os.path.abspath(produced) != os.path.abspath(self.data_path):
                    try:
                        shutil.move(produced, self.data_path)
                    except OSError:
                        pass

                detail = f"：{recent[-1]}" if recent else ""
                state = self.account_state()
                if state["logged_in"]:
                    if on_done:
                        on_done(True, "登录成功")
                elif return_code == 0:
                    if on_done:
                        on_done(False, "登录未完成，请重新获取二维码" + detail)
                else:
                    if on_done:
                        on_done(False, f"登录失败（BBDown 退出码 {return_code}）" + detail)
            except Exception as exc:  # noqa: BLE001
                if on_done:
                    on_done(False, str(exc))
            finally:
                self._login_process = None
                try:
                    if os.path.isfile(qr_path):
                        os.remove(qr_path)
                except OSError:
                    pass

        threading.Thread(target=_worker, daemon=True, name="bbdown-login").start()

    def login_cancel(self):
        process = getattr(self, "_login_process", None)
        if process and process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass

    def logout(self):
        try:
            if os.path.isfile(self.data_path):
                os.remove(self.data_path)
        except OSError as exc:
            raise RuntimeError(f"删除登录信息失败: {exc}") from exc

    # ------------------------------------------------------------------ #
    #  输出解析
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_progress(line):
        """从 BBDown 输出行中解析百分比，返回 0-100 整数或 None。"""
        # 跳过包含链接的行，避免 URL 中的 %xx 转义造成误判
        if "://" in line:
            return None
        # 匹配 "85%" / "85.6%" / "85 %"
        match = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", line)
        if match:
            return min(100, max(0, int(float(match.group(1)))))
        # 匹配进度条 [========    ] 估算（BBDown 进度条固定宽度 40）
        match = re.search(r"\[(=+)\s*\]", line)
        if match:
            filled = len(match.group(1))
            return min(100, int(filled / 40 * 100))
        return None

    @staticmethod
    def _describe_failure(lines, return_code):
        """把 BBDown 的最后输出整理成可读的失败原因。"""
        joined = "\n".join(str(line) for line in lines)
        if "UnauthorizedAccess" in joined or "IODenied" in joined:
            return "下载失败：临时目录不可写，请检查 TEMP/TMP 环境变量"
        if "net_http" in joined or "ssl_connection" in joined:
            return "下载失败：无法与 B 站建立 HTTPS 连接（net_http_ssl_connection_failed），请检查网络或代理"

        last_line = ""
        for line in reversed(lines):
            text = str(line).strip()
            if not text:
                continue
            last_line = text
            break

        if last_line:
            return f"下载失败：{last_line}"
        if return_code is None or return_code == 0:
            return "下载未产生任何输出，请检查网络连接"
        return f"下载失败（BBDown 退出码 {return_code}），请检查网络连接"
