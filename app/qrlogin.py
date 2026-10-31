"""B 站网页扫码登录。

BBDown 1.6.3 的 `login` 在当前 B 站接口下只能拿到空 SESSDATA，
因此这里自行实现：
    1. 调 passport 的 qrcode/generate 获取 url + qrcode_key；
    2. 用 segno 生成 SVG 二维码给前端；
    3. 轮询 qrcode/poll，从 Set-Cookie（或回调 URL 参数）取 SESSDATA 等；
    4. 写成 BBDown 能识别的 BBDown.data。
"""
import base64
import http.client
import json
import os
import ssl
import threading
import time
import urllib.parse

try:
    import segno
except ImportError:  # pragma: no cover - 缺少库时由调用方给出提示
    segno = None

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
}
_COOKIE_KEYS = ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "sid")


class QRLoginError(RuntimeError):
    """二维码登录过程中的可预期错误。"""


def _get(path):
    context = ssl.create_default_context()
    conn = http.client.HTTPSConnection("passport.bilibili.com", timeout=15, context=context)
    try:
        conn.request("GET", path, headers=_HEADERS)
        response = conn.getresponse()
        body = response.read()
        set_cookies = response.msg.get_all("Set-Cookie") or []
        return response.status, body, set_cookies
    finally:
        conn.close()


def _cookies_from_headers(set_cookies):
    result = {}
    for raw in set_cookies:
        first = raw.split(";", 1)[0]
        if "=" in first:
            name, value = first.split("=", 1)
            result[name.strip()] = value
    return result


def _cookies_from_url(url):
    result = {}
    try:
        query = urllib.parse.urlparse(url or "").query
        for name, value in urllib.parse.parse_qsl(query):
            if name in _COOKIE_KEYS:
                result[name] = value
    except ValueError:
        pass
    return result


class BiliQRLogin:
    """管理一次扫码登录的生命周期（生成 → 轮询 → 落盘）。"""

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.data_path = os.path.join(base_dir, "BBDown.data")
        self.key = ""
        self.qr = ""
        self.status = "idle"  # idle | waiting | scanned | success | failed
        self.message = ""
        self._stop = False

    # ------------------------------------------------------------------ #
    def start(self):
        if segno is None:
            raise QRLoginError("缺少 segno 库，无法生成登录二维码")
        try:
            _, body, _ = _get("/x/passport-login/web/qrcode/generate")
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise QRLoginError(f"获取二维码失败：{exc}") from exc

        if payload.get("code") != 0:
            raise QRLoginError(f"获取二维码失败：{payload.get('message')}")
        info = payload.get("data") or {}
        self.key = info.get("qrcode_key") or ""
        url = info.get("url") or ""
        if not self.key or not url:
            raise QRLoginError("二维码数据不完整")

        qr = segno.make(url, error="m")
        # 用 PNG data URI（segno 自带编码器，无需 Pillow）；
        # svg_inline() 缺少 xmlns，作为 <img> 独立图片无法渲染。
        self.qr = qr.png_data_uri(scale=10, border=4)
        self.status = "waiting"
        self.message = "请用 B 站 App 扫码，并在手机上点击“确认登录”"
        self._stop = False
        threading.Thread(target=self._poll_loop, daemon=True, name="bili-qr-poll").start()
        return self.snapshot()

    def cancel(self):
        self._stop = True

    def snapshot(self):
        return {"qr": self.qr, "status": self.status, "message": self.message}

    # ------------------------------------------------------------------ #
    def _poll_loop(self):
        deadline = time.time() + 180
        while not self._stop and time.time() < deadline:
            try:
                _, body, set_cookies = _get(
                    "/x/passport-login/web/qrcode/poll?qrcode_key="
                    + urllib.parse.quote(self.key)
                )
                payload = json.loads(body.decode("utf-8"))
                data = payload.get("data") or {}
                code = data.get("code")

                if code == 0:
                    cookies = _cookies_from_url(data.get("url"))
                    cookies.update(_cookies_from_headers(set_cookies))
                    if not cookies.get("SESSDATA"):
                        self.status = "failed"
                        self.message = "扫码已确认，但未获取到 SESSDATA，请重试"
                        return
                    self._write_cookie(cookies)
                    self.status = "success"
                    self.message = "登录成功"
                    return
                if code == 86090:
                    self.status = "scanned"
                    self.message = "已扫码，请在手机上点击“确认登录”"
                elif code == 86038:
                    self.status = "failed"
                    self.message = "二维码已过期，请重新获取"
                    return
                else:
                    self.status = "waiting"
            except Exception as exc:  # noqa: BLE001
                self.message = f"轮询失败：{exc}"
            time.sleep(1.5)

        if self.status not in ("success", "failed"):
            self.status = "failed"
            self.message = "登录超时，请重试"

    def _write_cookie(self, cookies):
        parts = [f"{key}={cookies[key]}" for key in _COOKIE_KEYS if cookies.get(key)]
        text = "; ".join(parts)
        tmp = self.data_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, self.data_path)
