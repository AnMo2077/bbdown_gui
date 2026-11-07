#!/usr/bin/env python3
"""BiliDownloader 安装程序（WinUI / Fluent 风格）。

由 build_installer.py 用 PyInstaller 打包为单文件 Setup.exe，
payload.zip 作为数据文件内置。安装过程只做三件事：
    1. 解压到用户选择的安装目录（默认 %LOCALAPPDATA%\\Programs\\BiliDownloader）
    2. 按选项创建桌面 / 开始菜单快捷方式
    3. 写入当前用户的卸载注册表项

不请求管理员权限，不写入自启动项，不联网。
"""
import ctypes
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import winreg
import zipfile
from tkinter import filedialog, messagebox, ttk

APP_NAME = "BiliDownloader"
APP_VERSION = "2.1"
PUBLISHER = "AnMo_C"
EXE_NAME = "BiliDownloader.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BiliDownloader"
CREATE_NO_WINDOW = 0x08000000

# Fluent / WinUI 3 深色配色（与主程序保持一致）
COLOR_BG = "#1e1e1e"
COLOR_CARD = "#272727"
COLOR_CARD_2 = "#2d2d2d"
COLOR_STROKE = "#3a3a3a"
COLOR_TEXT = "#f3f3f3"
COLOR_TEXT_2 = "#a8a8a8"
COLOR_ACCENT = "#4cc2ff"
COLOR_ACCENT_INK = "#00243a"
COLOR_ACCENT_SOFT = "#20343f"
COLOR_DANGER = "#ff5c5c"
COLOR_OK = "#3ddc84"


def install_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", APP_NAME)


def payload_path():
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, "payload.zip")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "payload.zip")


def resource_path(name):
    if getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, name)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", name)


def detect_installed():
    """读取旧版本安装信息（HKCU 优先，其次 HKLM）。"""
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, UNINSTALL_KEY) as key:
                try:
                    version = str(winreg.QueryValueEx(key, "DisplayVersion")[0])
                except OSError:
                    version = ""
                try:
                    location = str(winreg.QueryValueEx(key, "InstallLocation")[0])
                except OSError:
                    location = ""
        except OSError:
            continue
        if location and os.path.isdir(location):
            return {"version": version or "未知", "path": location}
        if version:
            return {"version": version, "path": ""}
    return None


def is_running():
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq BiliDownloader.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
        return "BiliDownloader.exe" in (completed.stdout or "")
    except Exception:  # noqa: BLE001
        return False


def create_shortcut(link_path, target, workdir):
    link = link_path.replace("'", "''")
    exe = target.replace("'", "''")
    folder = workdir.replace("'", "''")
    script = (
        "$W=New-Object -ComObject WScript.Shell;"
        f"$S=$W.CreateShortcut('{link}');"
        f"$S.TargetPath='{exe}';"
        f"$S.WorkingDirectory='{folder}';"
        f"$S.IconLocation='{exe},0';"
        "$S.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )


def remove_file(path):
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def shortcut_paths():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop", f"{APP_NAME}.lnk")
    start_menu = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        f"{APP_NAME}.lnk",
    )
    return desktop, start_menu


def write_uninstall_registry(directory):
    exe = os.path.join(directory, EXE_NAME)
    uninstaller = os.path.join(directory, "Uninstall.exe")
    try:
        size_kb = sum(
            os.path.getsize(os.path.join(root, name))
            for root, _, files in os.walk(directory)
            for name in files
            if os.path.isfile(os.path.join(root, name))
        ) // 1024
    except OSError:
        size_kb = 0
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, directory)
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, exe)
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller}"')
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, max(1, size_kb))


def extract_payload(archive_path, destination):
    base = os.path.realpath(destination)
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        total = max(1, len(members))
        for index, member in enumerate(members):
            target = os.path.realpath(os.path.join(destination, member.filename))
            if not (target == base or target.startswith(base + os.sep)):
                raise RuntimeError("安装包内容路径非法")
            archive.extract(member, destination)
            yield index + 1, total


def enable_dark_titlebar(window):
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        for attribute in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:  # noqa: BLE001
        pass


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION} 安装程序")
        self.resizable(False, False)
        self.geometry("660x720")
        self.configure(bg=COLOR_BG)
        self.events = queue.Queue()
        self.old = detect_installed()
        self.target_dir = self.old["path"] if self.old and self.old["path"] else install_dir()
        self._icon_photo = None
        self._photo = None

        try:
            icon_file = resource_path("app.ico")
            self.iconbitmap(icon_file)
            self.iconbitmap(default=icon_file)
        except tk.TclError:
            pass
        try:
            self._icon_photo = tk.PhotoImage(file=resource_path("icon-192.png"))
            self.iconphoto(True, self._icon_photo)
        except tk.TclError:
            self._icon_photo = None

        self.font_title = tkfont.Font(family="Segoe UI", size=20, weight="bold")
        self.font_sub = tkfont.Font(family="Segoe UI", size=9)
        self.font_base = tkfont.Font(family="Segoe UI", size=10)
        self.font_small = tkfont.Font(family="Segoe UI", size=9)

        self._build()
        self.after(120, self.poll_events)
        self.after(50, lambda: enable_dark_titlebar(self))

    # ------------------------------------------------------------------ #
    #  UI
    # ------------------------------------------------------------------ #
    def _card(self, parent, padding=16):
        card = tk.Frame(parent, bg=COLOR_CARD, highlightbackground=COLOR_STROKE,
                        highlightthickness=1, bd=0)
        inner = tk.Frame(card, bg=COLOR_CARD)
        inner.pack(fill="both", expand=True, padx=padding, pady=padding)
        return card, inner

    def _button(self, parent, text, command, accent=False, width=10):
        bg = COLOR_ACCENT if accent else COLOR_CARD_2
        fg = COLOR_ACCENT_INK if accent else COLOR_TEXT
        active = "#6fd0ff" if accent else "#3a3a3a"
        button = tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            bg=bg,
            fg=fg,
            activebackground=active,
            activeforeground=fg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            font=self.font_base,
            padx=8,
            pady=6,
        )
        return button

    def _build(self):
        header = tk.Frame(self, bg=COLOR_BG)
        header.pack(fill="x", padx=26, pady=(22, 14))

        if self._icon_photo is not None:
            try:
                self._photo = self._icon_photo.subsample(4, 4)
            except tk.TclError:
                self._photo = None
        if self._photo is not None:
            tk.Label(header, image=self._photo, bg=COLOR_BG).pack(side="left", padx=(0, 14))
        else:
            tk.Label(
                header, text="▶", bg=COLOR_ACCENT, fg=COLOR_ACCENT_INK,
                font=("Segoe UI", 18, "bold"), width=2, height=1
            ).pack(side="left", padx=(0, 14))

        title_box = tk.Frame(header, bg=COLOR_BG)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box, text=f"安装 {APP_NAME}", bg=COLOR_BG, fg=COLOR_TEXT,
            font=self.font_title, anchor="w"
        ).pack(anchor="w")
        tk.Label(
            title_box, text=f"版本 {APP_VERSION}    ·    作者 {PUBLISHER}",
            bg=COLOR_BG, fg=COLOR_TEXT_2, font=self.font_sub, anchor="w"
        ).pack(anchor="w", pady=(2, 0))

        if self.old:
            card, inner = self._card(self)
            card.pack(fill="x", padx=26, pady=(0, 12))
            inner.configure(bg=COLOR_ACCENT_SOFT)
            card.configure(bg=COLOR_ACCENT_SOFT, highlightbackground="#35505f")
            title = f"检测到已安装版本 {self.old['version']}"
            tk.Label(
                inner, text=title, bg=COLOR_ACCENT_SOFT, fg=COLOR_ACCENT,
                font=self.font_base, anchor="w"
            ).pack(anchor="w")
            path_text = self.old["path"] or "（未记录安装路径）"
            tk.Label(
                inner, text=path_text, bg=COLOR_ACCENT_SOFT, fg=COLOR_TEXT_2,
                font=self.font_small, anchor="w", wraplength=540, justify="left"
            ).pack(anchor="w", pady=(4, 0))
            tk.Label(
                inner, text="将覆盖安装到该目录（可在下方修改）", bg=COLOR_ACCENT_SOFT,
                fg=COLOR_TEXT_2, font=self.font_small, anchor="w"
            ).pack(anchor="w", pady=(2, 0))

        path_card, path_inner = self._card(self)
        path_card.pack(fill="x", padx=26, pady=(0, 12))
        tk.Label(
            path_inner, text="安装位置", bg=COLOR_CARD, fg=COLOR_TEXT_2,
            font=self.font_small, anchor="w"
        ).pack(anchor="w")
        row = tk.Frame(path_inner, bg=COLOR_CARD)
        row.pack(fill="x", pady=(6, 0))
        self.path_var = tk.StringVar(value=self.target_dir)
        entry = tk.Entry(
            row, textvariable=self.path_var, bg=COLOR_BG, fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT, relief="flat", highlightthickness=1,
            highlightbackground=COLOR_STROKE, highlightcolor=COLOR_ACCENT,
            font=self.font_small
        )
        entry.pack(side="left", fill="x", expand=True, ipady=5)
        self._button(row, "浏览…", self.choose_dir, width=8).pack(side="left", padx=(8, 0))
        tk.Label(
            path_inner, text="安装到当前用户，无需管理员权限", bg=COLOR_CARD,
            fg=COLOR_TEXT_2, font=self.font_small, anchor="w"
        ).pack(anchor="w", pady=(6, 0))

        options_card, options_inner = self._card(self)
        options_card.pack(fill="x", padx=26, pady=(0, 12))
        tk.Label(
            options_inner, text="安装选项", bg=COLOR_CARD, fg=COLOR_TEXT_2,
            font=self.font_small, anchor="w"
        ).pack(anchor="w", pady=(0, 4))

        self.desktop_var = tk.BooleanVar(value=True)
        self.start_menu_var = tk.BooleanVar(value=True)
        self.run_var = tk.BooleanVar(value=False)
        for text, variable in (
            ("创建桌面快捷方式", self.desktop_var),
            ("创建开始菜单快捷方式", self.start_menu_var),
            (f"安装完成后运行 {APP_NAME}", self.run_var),
        ):
            tk.Checkbutton(
                options_inner, text=text, variable=variable,
                bg=COLOR_CARD, fg=COLOR_TEXT, activebackground=COLOR_CARD,
                activeforeground=COLOR_TEXT, selectcolor=COLOR_BG,
                highlightthickness=0, bd=0, anchor="w", font=self.font_base,
            ).pack(anchor="w", pady=2)

        progress_card, progress_inner = self._card(self)
        progress_card.pack(fill="x", padx=26, pady=(0, 12))
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Fluent.Horizontal.TProgressbar",
            troughcolor=COLOR_BG,
            background=COLOR_ACCENT,
            bordercolor=COLOR_CARD,
            lightcolor=COLOR_ACCENT,
            darkcolor=COLOR_ACCENT,
            thickness=6,
        )
        self.progress = ttk.Progressbar(
            progress_inner, mode="determinate", maximum=100,
            style="Fluent.Horizontal.TProgressbar"
        )
        self.progress.pack(fill="x")
        self.status = tk.Label(
            progress_inner, text="准备就绪", bg=COLOR_CARD, fg=COLOR_TEXT_2,
            font=self.font_small, anchor="w"
        )
        self.status.pack(anchor="w", pady=(8, 0))

        footer = tk.Frame(self, bg=COLOR_BG)
        footer.pack(fill="x", padx=26, pady=(4, 22))
        self.cancel_button = self._button(footer, "取消", self.destroy, width=8)
        self.cancel_button.pack(side="right")
        self.install_button = self._button(
            footer, "安装", self.start_install, accent=True, width=12
        )
        self.install_button.pack(side="right", padx=(0, 10))

    # ------------------------------------------------------------------ #
    #  行为
    # ------------------------------------------------------------------ #
    def poll_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    done, total = value
                    self.progress["value"] = int(done * 100 / total)
                    self.status.config(text=f"正在复制文件… {done}/{total}")
                elif kind == "done":
                    self.progress["value"] = 100
                    self.status.config(text="安装完成")
                    self.cancel_button.config(state="disabled")
                    self.install_button.config(state="normal", text="完成", command=self.destroy)
                elif kind == "error":
                    self.install_button.config(state="normal")
                    self.status.config(text="安装失败", fg=COLOR_DANGER)
                    messagebox.showerror("安装失败", value, parent=self)
        except queue.Empty:
            pass
        self.after(120, self.poll_events)

    def choose_dir(self):
        selected = filedialog.askdirectory(
            initialdir=self.path_var.get() or install_dir(),
            parent=self,
            title="选择安装位置",
        )
        if selected:
            self.path_var.set(os.path.normpath(selected))

    def start_install(self):
        archive = payload_path()
        if not os.path.isfile(archive):
            messagebox.showerror("安装失败", "安装包数据缺失，请重新下载安装程序。", parent=self)
            return
        raw = self.path_var.get().strip()
        if not raw:
            messagebox.showerror("安装失败", "请填写安装位置。", parent=self)
            return
        directory = os.path.abspath(raw)
        if os.path.exists(directory) and not os.path.isdir(directory):
            messagebox.showerror("安装失败", "安装位置已被文件占用，请选择其他目录。", parent=self)
            return
        _, tail = os.path.splitdrive(directory)
        if tail in ("\\", "/", ""):
            messagebox.showerror("安装失败", "请不要直接安装到磁盘根目录。", parent=self)
            return
        if is_running():
            messagebox.showwarning("请先关闭程序", "BiliDownloader 正在运行，请退出后再安装。", parent=self)
            return
        self.target_dir = directory
        self.path_var.set(directory)
        self.install_button.config(state="disabled")
        self.cancel_button.config(state="disabled")
        self.status.config(text="正在安装…", fg=COLOR_TEXT_2)
        threading.Thread(
            target=self.install_worker,
            args=(
                archive,
                directory,
                self.desktop_var.get(),
                self.start_menu_var.get(),
                self.run_var.get(),
            ),
            daemon=True,
        ).start()

    def install_worker(self, archive, directory, desktop, start_menu, run_after):
        try:
            os.makedirs(directory, exist_ok=True)
            for done, total in extract_payload(archive, directory):
                if done % 5 == 0 or done == total:
                    self.events.put(("progress", (done, total)))
            exe = os.path.join(directory, EXE_NAME)
            if not os.path.isfile(exe):
                raise RuntimeError("安装包缺少主程序 BiliDownloader.exe")

            desktop_link, start_menu_link = shortcut_paths()
            if desktop:
                create_shortcut(desktop_link, exe, directory)
            else:
                remove_file(desktop_link)
            if start_menu:
                create_shortcut(start_menu_link, exe, directory)
            else:
                remove_file(start_menu_link)

            write_uninstall_registry(directory)
            if run_after:
                try:
                    subprocess.Popen([exe], cwd=directory)
                except OSError:
                    pass
            self.events.put(("done", None))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("error", str(exc)))


def main():
    app = InstallerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
