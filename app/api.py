"""远程 API 模块 - 获取公告、版本信息、更新日志。

只依赖标准库（urllib），避免给打包环境引入额外依赖。
"""
import threading
import urllib.request


class RemoteAPI:
    """从远程服务器获取公告与版本数据。

    远端文本格式（逐行 key=value）::

        prog_ver=2.0
        ad=公告内容
        log=更新日志
        update=y
        url=https://example.com/
    """

    DATA_URL = "https://api2.nzs233.xyz/bilidown.txt"
    HELP_URL = "https://api2.nzs233.xyz/bilidownhelp.txt"
    LICENSE_URL = "https://api2.nzs233.xyz/bilidownlicense.txt"
    DONATE_URL = "https://api2.nzs233.xyz/eat"

    TIMEOUT = 8
    USER_AGENT = "BiliDownloader/2.0 (+https://github.com/AnMo2077/bbdown_gui)"

    def __init__(self):
        self.ad = "正在获取公告..."
        self.log = ""
        self.prog_ver = ""
        self.update = ""
        self.url = ""
        self.fetched = False
        self.error = None

    def fetch(self, on_done=None):
        """异步获取远程数据，完成后回调 on_done(success: bool)。"""
        def _worker():
            try:
                request = urllib.request.Request(
                    self.DATA_URL,
                    headers={"User-Agent": self.USER_AGENT, "Cache-Control": "no-cache"},
                )
                with urllib.request.urlopen(request, timeout=self.TIMEOUT) as response:
                    if response.status != 200:
                        raise RuntimeError(f"服务器返回 {response.status}")
                    data = self._decode(response.read())

                self.ad = self._unescape(self._parse(data, "ad=")) or "暂无公告"
                self.log = self._unescape(self._parse(data, "log="))
                self.prog_ver = self._parse(data, "prog_ver=")
                self.update = self._parse(data, "update=").strip().lower()
                self.url = self._parse(data, "url=")
                self.fetched = True
                self.error = None
                if on_done:
                    on_done(True)
            except Exception as exc:  # noqa: BLE001 - 网络失败不应影响主流程
                self.error = str(exc)
                if on_done:
                    on_done(False)

        threading.Thread(target=_worker, daemon=True, name="remote-api").start()

    @staticmethod
    def _decode(content: bytes) -> str:
        """兼容不同服务端编码：优先 UTF-8，失败再按 GB18030（兼容 GBK）。"""
        if content.startswith(b"\xef\xbb\xbf"):
            return content.decode("utf-8-sig", errors="replace")
        for encoding in ("utf-8", "gb18030"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace")

    @staticmethod
    def _unescape(text: str) -> str:
        """把远端文本中的字面量 \\n / \\r 转成真正的换行符。"""
        return text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")

    @staticmethod
    def _parse(data: str, key: str) -> str:
        for line in data.splitlines():
            if line.startswith(key):
                return line[len(key):].strip()
        return ""
