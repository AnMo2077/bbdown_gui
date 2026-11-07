#!/usr/bin/env python3
"""BiliDownloader 安装程序（Fluent 横版布局）。

由 build_installer.py 用 PyInstaller 打包为单文件 Setup.exe，
payload.zip 作为数据文件内置。安装过程只做三件事：
    1. 解压到用户选择的安装目录（默认 %LOCALAPPDATA%\\Programs\\BiliDownloader）
    2. 按选项创建桌面 / 开始菜单快捷方式
    3. 写入当前用户的卸载注册表项

不请求管理员权限，不写入自启动项，不联网。
"""
import ctypes
import math
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import winreg
import zipfile
from tkinter import filedialog, messagebox

# 必须在创建 Tk 根窗口前声明 DPI 感知，否则高缩放下字体会被位图放大而发虚
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass

import customtkinter as ctk

APP_NAME = "BiliDownloader"
APP_VERSION = "2.2"
PUBLISHER = "AnMo_C"
EXE_NAME = "BiliDownloader.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BiliDownloader"
CREATE_NO_WINDOW = 0x08000000

# 与主程序 dark 主题一致的配色
COLOR_BG = "#1b1b1b"
COLOR_SIDE = "#1a1a1a"
COLOR_CARD = "#232323"
COLOR_CARD_2 = "#2d2d2d"
COLOR_STROKE = "#3a3a3a"
COLOR_TEXT = "#f3f3f3"
COLOR_TEXT_2 = "#a8a8a8"
COLOR_ACCENT = "#4cc2ff"
COLOR_ACCENT_INK = "#00243a"
COLOR_ACCENT_HOVER = "#6fd0ff"
COLOR_ACCENT_SOFT = "#20343f"
COLOR_ACCENT_STROKE = "#35505f"
COLOR_DANGER = "#ff5c5c"

ctk.set_appearance_mode("dark")


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


def _blend(start, end, t):
    start = start.lstrip("#")
    end = end.lstrip("#")
    values = []
    for index in (0, 2, 4):
        a = int(start[index:index + 2], 16)
        b = int(end[index:index + 2], 16)
        values.append(round(a + (b - a) * t))
    return "#" + "".join(f"{value:02x}" for value in values)


class RoundedButton(tk.Canvas):
    """4px 圆角按钮；文字由原生 Label 渲染，保证清晰，并带 120ms 悬停过渡。"""

    def __init__(
        self,
        master,
        text,
        command,
        width=112,
        height=36,
        radius=4,
        normal=COLOR_CARD_2,
        hover="#3a3a3a",
        text_color=COLOR_TEXT,
        border=COLOR_STROKE,
        border_width=1,
        bg_color=COLOR_CARD,
        font=("Segoe UI", 10),
    ):
        super().__init__(
            master, width=width, height=height, bg=bg_color,
            highlightthickness=0, bd=0, cursor="hand2", takefocus=0,
        )
        self._btn_w = width
        self._btn_h = height
        self._radius = radius
        self._normal = normal
        self._hover = hover
        self._text_color = text_color
        self._command = command
        self._enabled = True
        self._animation = None
        self._current = normal
        self._shape = self.create_polygon(
            *self._rounded_points(radius),
            fill=normal,
            outline=border if border_width else "",
            width=border_width,
        )
        self._label = tk.Label(
            self, text=text, bg=normal, fg=text_color, font=font,
            bd=0, padx=0, pady=0,
        )
        self.create_window(width / 2, height / 2, window=self._label)
        for widget in (self, self._label):
            widget.bind("<Button-1>", self._invoke, add="+")
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")

    def _rounded_points(self, radius):
        points = []
        corners = (
            (radius, radius, 180),
            (self._btn_w - radius, radius, 270),
            (self._btn_w - radius, self._btn_h - radius, 0),
            (radius, self._btn_h - radius, 90),
        )
        for cx, cy, start in corners:
            for step in range(5):
                angle = math.radians(start + step * 22.5)
                points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        return points

    def _set_color(self, color):
        self._current = color
        self.itemconfigure(self._shape, fill=color)
        self._label.configure(bg=color)

    def _animate(self, target):
        if not self._enabled:
            return
        if self._animation:
            try:
                self.after_cancel(self._animation)
            except tk.TclError:
                pass
            self._animation = None
        start = self._current
        steps = 8

        def step(index):
            if index > steps:
                self._animation = None
                return
            self._set_color(_blend(start, target, index / steps))
            self._animation = self.after(15, lambda: step(index + 1))

        step(0)

    def _on_enter(self, _event=None):
        self._animate(self._hover)

    def _on_leave(self, _event=None):
        self._animate(self._normal)

    def _invoke(self, _event=None):
        if self._enabled and self._command:
            self._command()

    def configure(self, **kwargs):
        if "text" in kwargs:
            self._label.configure(text=kwargs.pop("text"))
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            state = kwargs.pop("state")
            self._enabled = state != "disabled"
            self.configure(cursor="hand2" if self._enabled else "arrow")
            self._label.configure(fg=self._text_color if self._enabled else "#6a6a6a")
        if kwargs:
            super().configure(**kwargs)


class CheckBox(tk.Frame):
    """与主程序一致的方形圆角勾选框，文字使用原生 Label 渲染。"""

    def __init__(self, master, text, variable, bg=COLOR_CARD, font=("Segoe UI", 10)):
        super().__init__(master, bg=bg)
        self.var = variable
        self._bg = bg
        self._hover = False
        self.canvas = tk.Canvas(
            self, width=17, height=17, bg=bg, highlightthickness=0, bd=0, cursor="hand2"
        )
        self.canvas.pack(side="left")
        self.label = tk.Label(
            self, text=text, bg=bg, fg=COLOR_TEXT, font=font, bd=0, padx=0, pady=0,
            cursor="hand2",
        )
        self.label.pack(side="left", padx=(8, 0))
        self.var.trace_add("write", lambda *_: self._draw())
        for widget in (self.canvas, self.label):
            widget.bind("<Button-1>", self._toggle, add="+")
            widget.bind("<Enter>", self._enter, add="+")
            widget.bind("<Leave>", self._leave, add="+")
        self._draw()

    def _toggle(self, _event=None):
        self.var.set(not bool(self.var.get()))

    def _enter(self, _event=None):
        self._hover = True
        self._draw()

    def _leave(self, _event=None):
        self._hover = False
        self._draw()

    def _draw(self):
        self.canvas.delete("all")
        checked = bool(self.var.get())
        fill = COLOR_ACCENT if checked else self._bg
        outline = COLOR_ACCENT if (checked or self._hover) else COLOR_STROKE
        radius = 4
        points = []
        corners = (
            (radius, radius, 180),
            (17 - radius, radius, 270),
            (17 - radius, 17 - radius, 0),
            (radius, 17 - radius, 90),
        )
        for cx, cy, start in corners:
            for step in range(4):
                angle = math.radians(start + step * 30)
                points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        self.canvas.create_polygon(
            *points, fill=fill, outline=outline, width=1
        )
        if checked:
            self.canvas.create_line(
                4, 9, 7.5, 13, 14, 4.5, fill="#ffffff", width=2,
                capstyle=tk.ROUND, joinstyle=tk.ROUND,
            )


class InstallerApp(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=COLOR_BG)
        self.title(f"{APP_NAME} {APP_VERSION} 安装程序")
        self.resizable(False, False)
        self.geometry("980x620")
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

        self.font_title = ("Segoe UI", 22, "bold")
        self.font_heading = ("Segoe UI", 15, "bold")
        self.font_sub = ("Segoe UI", 9)
        self.font_base = ("Segoe UI", 10)
        self.font_small = ("Segoe UI", 9)

        self._build()
        self.after(120, self.poll_events)
        self.after(50, lambda: enable_dark_titlebar(self))

    # ------------------------------------------------------------------ #
    #  UI
    # ------------------------------------------------------------------ #
    def _label(self, parent, text, font=None, fg=COLOR_TEXT, bg=COLOR_CARD,
               anchor="w", justify="left", wraplength=0):
        label = tk.Label(
            parent, text=text, font=font or self.font_base, fg=fg, bg=bg,
            anchor=anchor, justify=justify, bd=0, padx=0, pady=0,
        )
        if wraplength:
            label.configure(wraplength=wraplength)
        return label

    def _card(self, parent, padding=18):
        card = ctk.CTkFrame(
            parent,
            corner_radius=8,
            fg_color=COLOR_CARD,
            border_width=1,
            border_color=COLOR_STROKE,
        )
        inner = ctk.CTkFrame(card, corner_radius=0, fg_color=COLOR_CARD)
        inner.pack(fill="both", expand=True, padx=padding, pady=padding)
        return card, inner

    def _button(self, parent, text, command, accent=False, width=112, height=36,
                bg_color=COLOR_CARD):
        if accent:
            return RoundedButton(
                parent, text, command, width=width, height=height,
                normal=COLOR_ACCENT, hover=COLOR_ACCENT_HOVER,
                text_color=COLOR_ACCENT_INK, border_width=0,
                bg_color=bg_color, font=self.font_base,
            )
        return RoundedButton(
            parent, text, command, width=width, height=height,
            normal=COLOR_CARD_2, hover="#3a3a3a",
            text_color=COLOR_TEXT, border=COLOR_STROKE, border_width=1,
            bg_color=bg_color, font=self.font_base,
        )

    def _check(self, parent, text, variable):
        return CheckBox(parent, text, variable, bg=COLOR_CARD, font=self.font_base)

    def _build(self):
        self.grid_columnconfigure(0, weight=0, minsize=320)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self, fg_color=COLOR_SIDE, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        right = ctk.CTkFrame(self, fg_color=COLOR_BG, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")

        left_inner = ctk.CTkFrame(left, fg_color=COLOR_SIDE, corner_radius=0)
        left_inner.pack(fill="both", expand=True, padx=26, pady=28)

        if self._icon_photo is not None:
            try:
                self._photo = self._icon_photo.subsample(4, 4)
            except tk.TclError:
                self._photo = None
        if self._photo is not None:
            tk.Label(left_inner, image=self._photo, bg=COLOR_SIDE, bd=0).pack(anchor="w")
        else:
            ctk.CTkLabel(
                left_inner, text="▶", width=48, height=48, corner_radius=8,
                fg_color=COLOR_ACCENT, text_color=COLOR_ACCENT_INK,
                font=("Segoe UI", 18, "bold"),
            ).pack(anchor="w")

        self._label(left_inner, APP_NAME, self.font_title, bg=COLOR_SIDE).pack(
            anchor="w", pady=(16, 2)
        )
        self._label(left_inner, f"安装程序 · {APP_VERSION}", self.font_sub,
                    fg=COLOR_TEXT_2, bg=COLOR_SIDE).pack(anchor="w")
        self._label(left_inner, f"作者 {PUBLISHER}", self.font_small,
                    fg=COLOR_TEXT_2, bg=COLOR_SIDE).pack(anchor="w", pady=(2, 0))

        if self.old:
            card, inner = self._card(left_inner, padding=14)
            card.configure(fg_color=COLOR_ACCENT_SOFT, border_color=COLOR_ACCENT_STROKE)
            inner.configure(fg_color=COLOR_ACCENT_SOFT)
            card.pack(fill="x", pady=(26, 0))
            self._label(inner, f"检测到已安装版本 {self.old['version']}",
                        self.font_base, fg=COLOR_ACCENT, bg=COLOR_ACCENT_SOFT).pack(anchor="w")
            self._label(inner, self.old["path"] or "（未记录安装路径）",
                        self.font_small, fg=COLOR_TEXT_2, bg=COLOR_ACCENT_SOFT,
                        wraplength=230).pack(anchor="w", pady=(6, 0))
            self._label(inner, "将覆盖安装，可在右侧修改目录",
                        self.font_small, fg=COLOR_TEXT_2, bg=COLOR_ACCENT_SOFT).pack(
                anchor="w", pady=(4, 0)
            )
        else:
            card, inner = self._card(left_inner, padding=14)
            card.pack(fill="x", pady=(26, 0))
            self._label(inner, "未检测到旧版本", self.font_base).pack(anchor="w")
            self._label(inner, "将进行全新安装", self.font_small, fg=COLOR_TEXT_2).pack(
                anchor="w", pady=(4, 0)
            )

        right_inner = ctk.CTkFrame(right, fg_color=COLOR_BG, corner_radius=0)
        right_inner.pack(fill="both", expand=True, padx=30, pady=28)

        footer = ctk.CTkFrame(right_inner, fg_color=COLOR_BG, corner_radius=0)
        footer.pack(side="bottom", fill="x", pady=(16, 0))
        self.cancel_button = self._button(
            footer, "取消", self.destroy, width=88, bg_color=COLOR_BG
        )
        self.cancel_button.pack(side="right")
        self.install_button = self._button(
            footer, "安装", self.start_install, accent=True, width=116, bg_color=COLOR_BG
        )
        self.install_button.pack(side="right", padx=(0, 10))

        self._label(right_inner, "安装设置", self.font_heading, bg=COLOR_BG).pack(anchor="w")
        self._label(right_inner, "选择安装位置与快捷方式", self.font_sub,
                    fg=COLOR_TEXT_2, bg=COLOR_BG).pack(anchor="w", pady=(2, 0))

        path_card, path_inner = self._card(right_inner)
        path_card.pack(fill="x", pady=(16, 0))
        self._label(path_inner, "安装位置", self.font_small, fg=COLOR_TEXT_2).pack(anchor="w")
        row = tk.Frame(path_inner, bg=COLOR_CARD)
        row.pack(fill="x", pady=(6, 0))
        self.path_var = tk.StringVar(value=self.target_dir)
        ctk.CTkEntry(
            row,
            textvariable=self.path_var,
            height=38,
            corner_radius=6,
            fg_color=COLOR_BG,
            border_color=COLOR_STROKE,
            border_width=1,
            text_color=COLOR_TEXT,
            font=self.font_base,
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._button(row, "浏览…", self.choose_dir, width=84, bg_color=COLOR_CARD).pack(side="left")
        self._label(path_inner, "安装到当前用户，无需管理员权限",
                    self.font_small, fg=COLOR_TEXT_2).pack(anchor="w", pady=(6, 0))

        options_card, options_inner = self._card(right_inner)
        options_card.pack(fill="x", pady=(12, 0))
        self._label(options_inner, "安装选项", self.font_small, fg=COLOR_TEXT_2).pack(
            anchor="w", pady=(0, 4)
        )

        self.desktop_var = tk.BooleanVar(value=True)
        self.start_menu_var = tk.BooleanVar(value=True)
        self.run_var = tk.BooleanVar(value=False)
        self._check(options_inner, "创建桌面快捷方式", self.desktop_var).pack(anchor="w", pady=3)
        self._check(options_inner, "创建开始菜单快捷方式", self.start_menu_var).pack(anchor="w", pady=3)
        self._check(options_inner, f"安装完成后运行 {APP_NAME}", self.run_var).pack(anchor="w", pady=3)

        progress_card, progress_inner = self._card(right_inner)
        progress_card.pack(fill="x", pady=(12, 0))
        self.progress = ctk.CTkProgressBar(
            progress_inner, height=6, corner_radius=3,
            fg_color=COLOR_BG, progress_color=COLOR_ACCENT,
        )
        self.progress.pack(fill="x")
        self.progress.set(0)
        self.status = self._label(progress_inner, "准备就绪", self.font_small, fg=COLOR_TEXT_2)
        self.status.pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------ #
    #  行为
    # ------------------------------------------------------------------ #
    def poll_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    done, total = value
                    self.progress.set(min(1.0, done / total))
                    self.status.configure(text=f"正在复制文件… {done}/{total}")
                elif kind == "done":
                    self.progress.set(1.0)
                    self.status.configure(text="安装完成", fg=COLOR_TEXT)
                    self.cancel_button.configure(state="disabled")
                    self.install_button.configure(
                        state="normal", text="完成", command=self.destroy
                    )
                elif kind == "error":
                    self.install_button.configure(state="normal")
                    self.status.configure(text="安装失败", fg=COLOR_DANGER)
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
        self.install_button.configure(state="disabled")
        self.cancel_button.configure(state="disabled")
        self.status.configure(text="正在安装…", fg=COLOR_TEXT_2)
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

