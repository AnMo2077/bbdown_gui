#!/usr/bin/env python3
"""BiliDownloader - 本地 Web UI 启动器。

界面位于 app/webui（HTML/CSS/JS，WinUI 3 Fluent 风格），
Python 只负责业务逻辑（BBDown 封装、配置、远程公告）与本地 HTTP 服务。

窗口宿主优先使用系统自带 Edge 的 App 模式（无地址栏，独立窗口），
找不到 Edge 时回退默认浏览器。

用法：
    py gui.py            # Edge App 窗口
    py gui.py --browser  # 强制使用默认浏览器
    py gui.py --serve    # 只启动本地服务（调试 / 自动化）
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
import traceback
import webbrowser

# 确保脚本目录在 sys.path 中（源码运行与 PyInstaller 打包后都可用）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# PyInstaller 安装版：数据目录固定为 exe 所在目录
if getattr(sys, "frozen", False):
    os.environ.setdefault("BILIDOWNLOADER_HOME", os.path.dirname(os.path.abspath(sys.executable)))

from app.server import AppServer  # noqa: E402


def app_dir():
    """程序所在目录：打包后为 exe 目录，源码运行为项目根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


LOG_PATH = os.path.join(app_dir(), "BiliDownloader.log")


def log(message):
    """写启动日志（窗口模式下没有控制台，便于用户反馈问题）。"""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except OSError:
        pass


def say(message):
    """窗口模式（PyInstaller --windowed）下 sys.stdout 为 None，不能直接 print。"""
    if sys.stdout is None:
        return
    try:
        print(message, flush=True)
    except Exception:  # noqa: BLE001
        pass


def report_error(exc):
    log("FATAL: " + "".join(traceback.format_exception(exc)))
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "BiliDownloader",
            f"程序遇到错误：\n{exc}\n\n详细信息已写入：\n{LOG_PATH}",
        )
        root.destroy()
    except Exception:  # noqa: BLE001 - GUI 弹窗失败时至少保留日志
        pass


def show_fallback_notice():
    """没有可用的 Edge/WebView2 窗口环境时提示用户改用浏览器。"""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(
            "BiliDownloader",
            "未检测到可用的 Microsoft Edge / WebView2 窗口环境。\n"
            "将自动使用系统默认浏览器打开界面。",
            parent=root,
        )
        root.destroy()
    except Exception:  # noqa: BLE001 - 提示失败时静默回退
        pass


def show_browser_error(url):
    """连默认浏览器也无法启动时给出兜底提示。"""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror(
            "BiliDownloader",
            f"无法自动打开默认浏览器。\n请手动访问：\n{url}",
            parent=root,
        )
        root.destroy()
    except Exception:  # noqa: BLE001
        pass


def find_edge():
    """查找系统自带 Microsoft Edge。"""
    candidates = [
        os.path.join(
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            "Microsoft", "Edge", "Application", "msedge.exe",
        ),
        os.path.join(
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            "Microsoft", "Edge", "Application", "msedge.exe",
        ),
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Microsoft", "Edge", "Application", "msedge.exe",
        ),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    try:
        import winreg

        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"
                with winreg.OpenKey(root, key_path) as key:
                    path, _ = winreg.QueryValueEx(key, "")
                if path and os.path.isfile(path):
                    return path
            except OSError:
                continue
    except ImportError:
        pass
    return ""


def run_edge_app(url, server):
    """用 Edge 的 App 模式打开独立窗口，等待窗口关闭或前端请求退出。"""
    edge = find_edge()
    if not edge:
        log("未找到 Microsoft Edge，改用默认浏览器")
        return False

    # 每次使用独立的临时配置目录，避免残留进程导致 “profile in use”
    profile = os.path.join(
        os.environ.get("LOCALAPPDATA", app_dir()),
        "BiliDownloader",
        "profiles",
        f"{os.getpid()}-{int(time.time())}",
    )
    try:
        os.makedirs(profile, exist_ok=True)
    except OSError:
        profile = os.path.join(app_dir(), ".browser", str(os.getpid()))
        os.makedirs(profile, exist_ok=True)

    arguments = [
        edge,
        f"--app={url}",
        "--window-size=1120,760",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        "--disable-sync",
        # 关闭硬件加速：老显卡/远程桌面下更稳定，界面动画仍由软件合成
        "--disable-gpu",
        "--disable-features=msEdgeSidebarV2,msEdgeCollections",
    ]
    if getattr(sys, "frozen", False):
        # PyInstaller 的 Job 对象与 Chromium 沙箱不兼容，打包版需关闭沙箱；
        # 该窗口只加载 127.0.0.1 本地页面，不用于浏览外部网站。
        arguments.append("--no-sandbox")
        # 抑制 Chromium 对 --no-sandbox 的“不受支持命令行标记”提示条
        arguments.append("--test-type")
    try:
        process = subprocess.Popen(arguments)
    except OSError as exc:
        log(f"Edge 启动失败，改用默认浏览器: {exc}")
        return False

    log(f"Edge App 窗口已启动 pid={process.pid}")
    time.sleep(1.2)
    if process.poll() is not None:
        log(f"Edge App 进程提前退出 (code={process.returncode})，改用默认浏览器")
        shutil.rmtree(profile, ignore_errors=True)
        return False

    try:
        while process.poll() is None:
            if server.quit_requested:
                log("收到退出请求，正在关闭 Edge 窗口")
                try:
                    process.terminate()
                except OSError:
                    pass
                break
            time.sleep(0.25)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
    except KeyboardInterrupt:
        try:
            process.terminate()
        except OSError:
            pass
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    log("Edge App 窗口已关闭")
    return True


def dialog_icon():
    """优先取打包内 app.ico，源码运行时回退到 build/app.ico。"""
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(os.path.join(sys._MEIPASS, "app.ico"))
    candidates.append(os.path.join(app_dir(), "app.ico"))
    candidates.append(os.path.join(app_dir(), "build", "app.ico"))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def ask_window_mode(server):
    """安装版首次启动时选择默认窗口方式。"""
    try:
        import tkinter as tk
    except Exception:  # noqa: BLE001
        return "edge"

    choice = {"value": "edge"}
    root = tk.Tk()
    root.title("BiliDownloader")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    icon = dialog_icon()
    if icon:
        try:
            root.iconbitmap(icon)
        except tk.TclError:
            pass

    tk.Label(root, text="欢迎使用 BiliDownloader", font=("Segoe UI", 16, "bold")).pack(
        anchor="w", padx=24, pady=(22, 4)
    )
    tk.Label(
        root,
        text="首次启动，请选择界面打开方式（之后可在设置中更改）：",
        foreground="#555555",
    ).pack(anchor="w", padx=24)
    var = tk.StringVar(value="edge")
    tk.Radiobutton(
        root, text="内置窗口（WebView / Edge，推荐）", variable=var, value="edge"
    ).pack(anchor="w", padx=24, pady=(14, 2))
    tk.Radiobutton(root, text="默认浏览器", variable=var, value="browser").pack(
        anchor="w", padx=24
    )

    def confirm():
        choice["value"] = var.get()
        try:
            server.config.set("window_mode", choice["value"])
            server.config.save()
        except Exception:  # noqa: BLE001
            pass
        root.destroy()

    ok_button = tk.Button(root, text="确定", width=12, command=confirm)
    ok_button.pack(anchor="e", padx=24, pady=(18, 0))
    ok_button.focus_set()
    root.bind("<Return>", lambda event: confirm())
    root.protocol("WM_DELETE_WINDOW", confirm)
    root.update_idletasks()
    width, height = 480, 268
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.mainloop()
    return choice["value"]


def open_default_browser(url, server):
    opened = webbrowser.open(url)
    if opened is False:
        log("无法打开默认浏览器")
        show_browser_error(url)
        say("无法自动打开浏览器")
        return
    log("已在默认浏览器打开界面")
    say("已在默认浏览器打开界面；按 Ctrl+C 结束服务。")
    while not server.quit_requested:
        time.sleep(0.3)


def webview2_runtime_installed():
    """检测 WebView2 Evergreen 运行时是否安装。"""
    bases = [
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("PROGRAMFILES"),
        os.environ.get("LOCALAPPDATA"),
    ]
    for base in bases:
        if not base:
            continue
        application = os.path.join(base, "Microsoft", "EdgeWebView", "Application")
        try:
            versions = os.listdir(application)
        except OSError:
            continue
        for version in versions:
            if os.path.isfile(os.path.join(application, version, "msedgewebview2.exe")):
                return True
    return False


WEBVIEW2_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"


def ask_webview_fallback():
    """内置窗口不可用时，让用户选择下载 WebView2 或改用浏览器。"""
    try:
        import tkinter as tk
    except Exception:  # noqa: BLE001
        return "browser"

    choice = {"value": "browser"}
    root = tk.Tk()
    root.title("BiliDownloader")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    icon = dialog_icon()
    if icon:
        try:
            root.iconbitmap(icon)
        except tk.TclError:
            pass

    tk.Label(root, text="未检测到可用的 WebView", font=("Segoe UI", 15, "bold")).pack(
        anchor="w", padx=24, pady=(20, 6)
    )
    detail = "内置窗口需要 Microsoft Edge 或 WebView2 运行时。"
    if webview2_runtime_installed():
        detail = "已检测到 WebView2 运行时，但未找到 Microsoft Edge 浏览器。"
    tk.Label(root, text=detail, foreground="#555555").pack(anchor="w", padx=24)
    tk.Label(
        root,
        text="可以下载 WebView2 后重试，或本次改用默认浏览器打开界面。",
        foreground="#555555",
    ).pack(anchor="w", padx=24, pady=(4, 0))

    def choose(value):
        choice["value"] = value
        root.destroy()

    row = tk.Frame(root)
    row.pack(anchor="e", padx=24, pady=(22, 0))
    tk.Button(row, text="退出", width=8, command=lambda: choose("quit")).pack(side="left", padx=(0, 8))
    tk.Button(row, text="使用默认浏览器", width=14, command=lambda: choose("browser")).pack(side="left", padx=(0, 8))
    tk.Button(row, text="下载 WebView2", width=14, command=lambda: choose("download")).pack(side="left")
    root.protocol("WM_DELETE_WINDOW", lambda: choose("quit"))
    root.update_idletasks()
    width, height = 520, 270
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.mainloop()
    return choice["value"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="BiliDownloader")
    parser.add_argument("--browser", action="store_true", help="强制使用默认浏览器")
    parser.add_argument("--serve", action="store_true", help="只启动本地服务，不打开窗口")
    parser.add_argument("--port", type=int, default=0, help="本地服务端口（默认随机）")
    args = parser.parse_args(argv)

    log(f"启动 (frozen={getattr(sys, 'frozen', False)}, dir={app_dir()})")
    server = AppServer()
    server.start(args.port)
    url = server.url
    log(f"本地服务: {url}")
    say(f"BiliDownloader UI: {url}")

    mode = str(server.config.get("window_mode") or "").strip().lower()
    if mode not in ("edge", "browser"):
        if getattr(sys, "frozen", False) and not args.browser and not args.serve:
            mode = ask_window_mode(server)
        else:
            mode = "edge"

    try:
        if args.serve:
            while not server.quit_requested:
                time.sleep(0.3)
        elif args.browser or mode == "browser":
            open_default_browser(url, server)
        elif not find_edge():
            choice = ask_webview_fallback()
            if choice == "download":
                log("未检测到 WebView，打开 WebView2 下载页")
                webbrowser.open(WEBVIEW2_URL)
                say("已打开 WebView2 下载页；本次使用默认浏览器。")
            if choice in ("download", "browser"):
                open_default_browser(url, server)
        elif not run_edge_app(url, server):
            show_fallback_notice()
            open_default_browser(url, server)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        log("服务已停止")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 - 窗口模式下的最后一道兜底
        report_error(error)
        sys.exit(1)
