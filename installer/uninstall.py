#!/usr/bin/env python3
"""BiliDownloader 卸载程序。

由 build_installer.py 打包为 Uninstall.exe 并放入安装目录。
只删除安装目录、桌面/开始菜单快捷方式和当前用户的卸载注册表项。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import winreg
from tkinter import messagebox

APP_NAME = "BiliDownloader"
APP_VERSION = "2.0"
PUBLISHER = "AnMo_C"
EXE_NAME = "BiliDownloader.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BiliDownloader"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def install_dir():
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.isfile(os.path.join(exe_dir, EXE_NAME)):
            return exe_dir
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "InstallLocation")
            if value and os.path.isdir(value):
                return value
    except OSError:
        pass
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", APP_NAME)


def shortcut_paths():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop", f"{APP_NAME}.lnk")
    start_menu = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs", f"{APP_NAME}.lnk",
    )
    return (desktop, start_menu)


def remove_shortcuts():
    for path in shortcut_paths():
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass


def remove_registry():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass


def cleanup(directory):
    time.sleep(1.2)
    for _ in range(20):
        try:
            if os.path.isdir(directory):
                shutil.rmtree(directory)
            break
        except OSError:
            time.sleep(0.4)


def run_cleanup(directory):
    remove_shortcuts()
    remove_registry()
    cleanup(directory)


def main():
    if "--cleanup" in sys.argv:
        index = sys.argv.index("--cleanup")
        target = sys.argv[index + 1] if index + 1 < len(sys.argv) else install_dir()
        run_cleanup(target)
        return

    root = tk.Tk()
    root.withdraw()
    if not messagebox.askyesno(
        f"卸载 {APP_NAME}",
        f"确定要卸载 {APP_NAME} {APP_VERSION} 吗？\n\n安装目录：\n{install_dir()}",
    ):
        return
    root.destroy()

    directory = install_dir()
    remove_shortcuts()
    remove_registry()

    temp_exe = os.path.join(tempfile.gettempdir(), f"BiliDownloader-Uninstall-{os.getpid()}.exe")
    try:
        shutil.copy2(sys.executable, temp_exe)
        subprocess.Popen(
            [temp_exe, "--cleanup", directory],
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        )
    except OSError:
        cleanup(directory)


if __name__ == "__main__":
    main()
