@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo  BiliDownloader 安装包构建
echo ========================================
py build_installer.py
if errorlevel 1 (
    echo.
    echo [失败] 构建未完成，请查看上方日志。
    pause
    exit /b 1
)
echo.
echo [完成] 产物在 dist\BiliDownloader-Setup.exe
pause
