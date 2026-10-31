#!/usr/bin/env python3
"""BiliDownloader 安装程序。

由 build_installer.py 用 PyInstaller 打包为单文件 Setup.exe，
payload.zip 作为数据文件内置。安装过程只做三件事：
    1. 解压到 %LOCALAPPDATA%\\Programs\\BiliDownloader
    2. 创建桌面 / 开始菜单快捷方式
    3. 写入当前用户的卸载注册表项

不请求管理员权限，不写入自启动项，不联网。
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import winreg
import zipfile
from tkinter import filedialog, messagebox, ttk

APP_NAME = "BiliDownloader"
APP_VERSION = "2.0"
PUBLISHER = "AnMo_C"
EXE_NAME = "BiliDownloader.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BiliDownloader"
CREATE_NO_WINDOW = 0x08000000


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


def write_uninstall_registry(directory):
    exe = os.path.join(directory, EXE_NAME)
    uninstaller = os.path.join(directory, "Uninstall.exe")
    try:
        size_mb = sum(
            os.path.getsize(os.path.join(root, name))
            for root, _, files in os.walk(directory)
            for name in files
            if os.path.isfile(os.path.join(root, name))
        ) // 1024
    except OSError:
        size_mb = 0
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, directory)
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, exe)
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller}"')
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, max(1, size_mb))


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


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION} 安装程序")
        self.resizable(False, False)
        self.geometry("560x360")
        self.configure(padx=26, pady=22)
        self.events = queue.Queue()
        self.target_dir = install_dir()

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

        ttk.Label(self, text=f"安装 {APP_NAME}", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(
            self,
            text=f"版本 {APP_VERSION}    ·    作者 {PUBLISHER}",
            foreground="#666666",
        ).pack(anchor="w", pady=(4, 14))
        ttk.Label(self, text="安装位置", foreground="#666666").pack(anchor="w")
        path_row = ttk.Frame(self)
        path_row.pack(fill="x", pady=(4, 12))
        self.path_var = tk.StringVar(value=install_dir())
        tk.Entry(path_row, textvariable=self.path_var).pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="浏览…", command=self.choose_dir).pack(side="left", padx=(8, 0))
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(4, 8))
        self.status = ttk.Label(self, text="准备就绪", foreground="#666666")
        self.status.pack(anchor="w")
        self.run_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text=f"安装完成后运行 {APP_NAME}", variable=self.run_var).pack(
            anchor="w", pady=(14, 0)
        )
        self.install_button = ttk.Button(self, text="安装", command=self.start_install)
        self.install_button.pack(anchor="e", pady=(16, 0))

        self.after(120, self.poll_events)

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
                    self.install_button.config(state="normal", text="完成")
                    self.install_button.config(command=self.finish)
                elif kind == "error":
                    self.install_button.config(state="normal")
                    self.status.config(text="安装失败")
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
        directory = os.path.abspath(self.path_var.get().strip())
        if not self.path_var.get().strip():
            messagebox.showerror("安装失败", "请填写安装位置。", parent=self)
            return
        if os.path.exists(directory) and not os.path.isdir(directory):
            messagebox.showerror("安装失败", "安装位置已被文件占用，请选择其他目录。", parent=self)
            return
        drive, tail = os.path.splitdrive(directory)
        if tail in ("\\", "/", ""):
            messagebox.showerror("安装失败", "请不要直接安装到磁盘根目录。", parent=self)
            return
        if is_running():
            messagebox.showwarning("请先关闭程序", "BiliDownloader 正在运行，请退出后再安装。", parent=self)
            return
        self.target_dir = directory
        self.path_var.set(directory)
        self.install_button.config(state="disabled")
        self.status.config(text="正在安装…")
        threading.Thread(target=self.install_worker, args=(archive, directory), daemon=True).start()

    def install_worker(self, archive, directory):
        try:
            os.makedirs(directory, exist_ok=True)
            for done, total in extract_payload(archive, directory):
                if done % 5 == 0 or done == total:
                    self.events.put(("progress", (done, total)))
            exe = os.path.join(directory, EXE_NAME)
            if not os.path.isfile(exe):
                raise RuntimeError("安装包缺少主程序 BiliDownloader.exe")
            desktop = os.path.join(os.path.expanduser("~"), "Desktop", f"{APP_NAME}.lnk")
            start_menu = os.path.join(
                os.environ.get("APPDATA", ""),
                "Microsoft", "Windows", "Start Menu", "Programs", f"{APP_NAME}.lnk",
            )
            create_shortcut(desktop, exe, directory)
            create_shortcut(start_menu, exe, directory)
            write_uninstall_registry(directory)
            self.events.put(("done", None))
        except Exception as exc:  # noqa: BLE001
            self.events.put(("error", str(exc)))

    def finish(self):
        directory = self.target_dir or install_dir()
        exe = os.path.join(directory, EXE_NAME)
        if self.run_var.get() and os.path.isfile(exe):
            try:
                subprocess.Popen([exe], cwd=directory)
            except OSError:
                pass
        self.destroy()


def main():
    app = InstallerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
