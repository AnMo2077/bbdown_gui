@echo off
chcp 65001 >nul
title BiliDownloader
cd /d "%~dp0"

py -3 gui.py %*
if not errorlevel 1 exit /b

where python >nul 2>nul
if not errorlevel 1 (
    python gui.py %*
    if not errorlevel 1 exit /b
)

echo.
echo [错误] 未找到可用的 Python，请安装 Python 3.10+ 并加入 PATH。
echo 下载地址: https://www.python.org/downloads/
echo.
pause
