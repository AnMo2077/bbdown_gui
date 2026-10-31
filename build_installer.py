#!/usr/bin/env python3
"""一键构建 BiliDownloader 安装包。

流程：
    1. PyInstaller 打包应用（onedir，内含 Web UI / pywebview / pythonnet）
    2. 复制 BBDown.exe、ffmpeg.exe、aria2c.exe、curl.exe 与运行库
    3. 打包卸载器 Uninstall.exe
    4. 压缩 payload.zip，再用 PyInstaller 生成单文件安装程序
产物：
    dist/BiliDownloader-Setup.exe

用法：
    py build_installer.py
"""
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
SPEC_DIR = BUILD / "spec"
APP_DIR_BUILD = BUILD / "app"
PAYLOAD = BUILD / "payload.zip"
ICON = BUILD / "app.ico"

APP_NAME = "BiliDownloader"
APP_VERSION = "2.0"
PUBLISHER = "AnMo_C"

BINARIES = [
    "BBDown.exe",
    "aria2c.exe",
    "ffmpeg.exe",
    "curl.exe",
    "curl-ca-bundle.crt",
]
DLL_PATTERNS = [
    "avcodec-*.dll",
    "avdevice-*.dll",
    "avfilter-*.dll",
    "avformat-*.dll",
    "avutil-*.dll",
    "postproc-*.dll",
    "swresample-*.dll",
    "swscale-*.dll",
    "libcurl-*.dll",
]

# 不进入安装包的本地数据（保留用户配置/登录态）
SKIP_NAMES = {
    "gui_config.json",
    "BBDown.data",
    "download_history.json",
    "BiliDownloader.log",
    "qrcode.png",
}


def run(cmd, cwd=ROOT):
    printable = " ".join(str(part) for part in cmd)
    print(f"\n> {printable}", flush=True)
    subprocess.run([str(part) for part in cmd], cwd=str(cwd), check=True)


def clean():
    for path in (BUILD, DIST):
        if path.exists():
            print(f"清理 {path}", flush=True)
            try:
                shutil.rmtree(path)
            except OSError as exc:
                raise SystemExit(
                    f"无法清理 {path}，请先关闭正在运行的 BiliDownloader 或安装程序。\n{exc}"
                )
    BUILD.mkdir(parents=True, exist_ok=True)
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)


def make_icon():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("未安装 Pillow，跳过图标生成", flush=True)
        return None

    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=58, fill=(10, 132, 208, 255))
    draw.polygon([(92, 68), (92, 188), (190, 128)], fill=(255, 255, 255, 255))
    image.save(
        ICON,
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return ICON


def write_version_file(path, internal_name, description):
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(2, 0, 0, 0),
    prodvers=(2, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', '{PUBLISHER}'),
        StringStruct('FileDescription', '{description}'),
        StringStruct('FileVersion', '{APP_VERSION}'),
        StringStruct('InternalName', '{internal_name}'),
        StringStruct('OriginalFilename', '{internal_name}.exe'),
        StringStruct('ProductName', '{APP_NAME}'),
        StringStruct('ProductVersion', '{APP_VERSION}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    path.write_text(content, encoding="utf-8")
    return path


def build_app(icon, version_file):
    dist = BUILD / "app"
    print("\n=== 1/4 打包应用 ===", flush=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(dist),
        "--workpath",
        str(BUILD / "work-app"),
        "--specpath",
        str(SPEC_DIR),
        "--add-data",
        f"{ROOT / 'app' / 'webui'};app/webui",
        "--hidden-import",
        "tkinter",
        "--hidden-import",
        "tkinter.filedialog",
        "--hidden-import",
        "tkinter.ttk",
        "--hidden-import",
        "segno",
    ]
    if icon:
        cmd += ["--icon", str(icon)]
        cmd += ["--add-data", f"{icon};."]
    if version_file:
        cmd += ["--version-file", str(version_file)]
    cmd.append("gui.py")
    run(cmd)
    return dist / APP_NAME


def copy_binaries(app_dir):
    print("\n=== 2/4 复制 BBDown / ffmpeg / 运行库 ===", flush=True)
    missing = []
    for name in BINARIES:
        source = ROOT / name
        if not source.exists():
            missing.append(name)
            continue
        shutil.copy2(source, app_dir / name)
        print(f"  + {name}", flush=True)
    for pattern in DLL_PATTERNS:
        for source in sorted(ROOT.glob(pattern)):
            shutil.copy2(source, app_dir / source.name)
            print(f"  + {source.name}", flush=True)
    if missing:
        print(f"  ! 缺少文件（安装包将不含这些文件）: {', '.join(missing)}", flush=True)
    if not (app_dir / "BBDown.exe").exists():
        raise SystemExit("BBDown.exe 不存在，无法生成可用的安装包")


def build_uninstaller(icon, version_file):
    print("\n=== 3/4 打包卸载器 ===", flush=True)
    dist = BUILD / "uninstall"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "Uninstall",
        "--distpath",
        str(dist),
        "--workpath",
        str(BUILD / "work-uninstall"),
        "--specpath",
        str(SPEC_DIR),
        "--hidden-import",
        "tkinter",
        "--hidden-import",
        "tkinter.ttk",
        "--hidden-import",
        "tkinter.messagebox",
        "--hidden-import",
        "winreg",
    ]
    if icon:
        cmd += ["--icon", str(icon)]
    if version_file:
        cmd += ["--version-file", str(version_file)]
    cmd.append("installer/uninstall.py")
    run(cmd)
    return dist / "Uninstall.exe"


def build_payload(app_dir):
    print("\n=== 压缩 payload ===", flush=True)
    count = 0
    with zipfile.ZipFile(PAYLOAD, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(app_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.name in SKIP_NAMES or ".bbdown-tmp" in path.parts:
                continue
            archive.write(path, path.relative_to(app_dir))
            count += 1

    # 安全校验：安装包绝不能带出本地配置、登录凭据、测试目录
    with zipfile.ZipFile(PAYLOAD) as archive:
        names = archive.namelist()
    sensitive_names = {
        "BBDown.data",
        "gui_config.json",
        "download_history.json",
        "BiliDownloader.log",
        "qrcode.png",
    }
    sensitive_parts = {
        "tests",
        ".test-tmp",
        ".bbdown-tmp",
        "__pycache__",
        ".build-venv",
        "_forensics",
        "1.7.8",
    }
    sensitive_markers = ("device.wvd", "mp4decrypt", "BBDown-1.7.8")
    leaked = []
    for name in names:
        base = name.rsplit("/", 1)[-1]
        parts = set(name.replace("\\", "/").split("/"))
        if (
            base in sensitive_names
            or base.startswith("BBDown.data")
            or parts & sensitive_parts
            or any(marker in name for marker in sensitive_markers)
        ):
            leaked.append(name)
    if leaked:
        PAYLOAD.unlink(missing_ok=True)
        raise SystemExit(
            "安装包包含本地配置/登录凭据/测试文件，已中止构建：\n  "
            + "\n  ".join(leaked[:20])
        )
    print("  已校验：不含本地配置、登录凭据、测试目录", flush=True)
    size_mb = PAYLOAD.stat().st_size / 1024 / 1024
    print(f"  payload.zip: {count} 个文件，{size_mb:.1f} MB", flush=True)


def build_installer(icon, version_file):
    print("\n=== 4/4 打包安装程序 ===", flush=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        f"{APP_NAME}-Setup-{APP_VERSION}",
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD / "work-installer"),
        "--specpath",
        str(SPEC_DIR),
        "--add-data",
        f"{PAYLOAD};.",
        "--add-data",
        f"{ROOT / 'app' / 'webui' / 'icon-192.png'};.",
        "--hidden-import",
        "tkinter",
        "--hidden-import",
        "tkinter.ttk",
        "--hidden-import",
        "tkinter.messagebox",
        "--hidden-import",
        "winreg",
    ]
    if icon:
        cmd += ["--add-data", f"{icon};.", "--icon", str(icon)]
    if version_file:
        cmd += ["--version-file", str(version_file)]
    cmd.append("installer/installer.py")
    run(cmd)
    return DIST / f"{APP_NAME}-Setup-{APP_VERSION}.exe"


def main():
    started = time.time()
    clean()
    icon = make_icon()
    app_version = write_version_file(
        BUILD / "version-app.txt", APP_NAME, f"{APP_NAME} 主程序"
    )
    uninstall_version = write_version_file(
        BUILD / "version-uninstall.txt", "Uninstall", f"{APP_NAME} 卸载程序"
    )
    setup_version = write_version_file(
        BUILD / "version-setup.txt", f"{APP_NAME}-Setup", f"{APP_NAME} 安装程序"
    )

    app_dir = build_app(icon, app_version)
    copy_binaries(app_dir)
    uninstaller = build_uninstaller(icon, uninstall_version)
    shutil.copy2(uninstaller, app_dir / "Uninstall.exe")
    build_payload(app_dir)
    setup = build_installer(icon, setup_version)

    elapsed = time.time() - started
    size_mb = setup.stat().st_size / 1024 / 1024
    print("\n构建完成", flush=True)
    print(f"  安装包: {setup}", flush=True)
    print(f"  大小:   {size_mb:.1f} MB", flush=True)
    print(f"  耗时:   {elapsed:.0f}s", flush=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(f"\n构建失败：{error}", file=sys.stderr, flush=True)
        sys.exit(1)
