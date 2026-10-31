# 下载 BiliDownloader 安装包所需的第三方二进制（固定版本）
# 用法：pwsh -File scripts/fetch-binaries.ps1
# 产物：项目根目录下的 BBDown.exe / ffmpeg.exe / aria2c.exe / curl.exe 及运行库
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Root = Split-Path -Parent $PSScriptRoot
$Vendor = Join-Path $Root "vendor"
$Extract = Join-Path $Vendor "extract"
New-Item -ItemType Directory -Force -Path $Vendor, $Extract | Out-Null

$Packages = @(
    @{
        Name = "bbdown"
        Url  = "https://github.com/nilaoda/BBDown/releases/download/1.6.3/BBDown_1.6.3_20240814_win-x64.zip"
        File = "bbdown.zip"
    },
    @{
        Name = "aria2"
        Url  = "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip"
        File = "aria2.zip"
    },
    @{
        Name = "ffmpeg"
        Url  = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full-shared.7z"
        File = "ffmpeg.7z"
    },
    @{
        Name = "curl"
        Url  = "https://curl.se/windows/dl-8.23.0_6/curl-8.23.0_6-win64-mingw.zip"
        File = "curl.zip"
    }
)

foreach ($Package in $Packages) {
    $Archive = Join-Path $Vendor $Package.File
    if (-not (Test-Path $Archive) -or (Get-Item $Archive).Length -lt 1024) {
        Write-Host "下载 $($Package.Name): $($Package.Url)"
        Invoke-WebRequest -Uri $Package.Url -OutFile $Archive -UseBasicParsing -TimeoutSec 600
    } else {
        Write-Host "复用缓存 $($Package.File)"
    }

    $Target = Join-Path $Extract $Package.Name
    if (Test-Path $Target) {
        Remove-Item $Target -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    if ($Package.File.EndsWith(".7z")) {
        $SevenZip = (Get-Command 7z.exe -ErrorAction SilentlyContinue).Source
        if (-not $SevenZip) {
            $SevenZip = "C:\Program Files\7-Zip\7z.exe"
        }
        if (-not (Test-Path $SevenZip)) {
            throw "未找到 7z.exe，无法解压 ffmpeg"
        }
        & $SevenZip x $Archive "-o$Target" -y | Out-Null
    } else {
        Expand-Archive -Path $Archive -DestinationPath $Target -Force
    }
}

function Copy-FirstMatch {
    param([string]$Base, [string]$Filter, [string]$Destination)
    $File = Get-ChildItem $Base -Recurse -File -Filter $Filter -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $File) { throw "未在压缩包中找到 $Filter" }
    Copy-Item $File.FullName (Join-Path $Root $Destination) -Force
    Write-Host "  + $Destination"
    return $File.DirectoryName
}

$BbdownDir = Copy-FirstMatch -Base (Join-Path $Extract "bbdown") -Filter "BBDown.exe" -Destination "BBDown.exe"
Copy-FirstMatch -Base (Join-Path $Extract "aria2") -Filter "aria2c.exe" -Destination "aria2c.exe" | Out-Null

$FfmpegDir = Copy-FirstMatch -Base (Join-Path $Extract "ffmpeg") -Filter "ffmpeg.exe" -Destination "ffmpeg.exe"
Get-ChildItem $FfmpegDir -File -Filter "*.dll" | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $Root $_.Name) -Force
    Write-Host "  + $($_.Name)"
}

$CurlDir = Copy-FirstMatch -Base (Join-Path $Extract "curl") -Filter "curl.exe" -Destination "curl.exe"
Copy-FirstMatch -Base (Join-Path $Extract "curl") -Filter "libcurl-x64.dll" -Destination "libcurl-x64.dll" | Out-Null

$CaFile = Get-ChildItem (Join-Path $Extract "curl") -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @("curl-ca-bundle.crt", "cacert.pem") } |
    Select-Object -First 1
if ($CaFile) {
    Copy-Item $CaFile.FullName (Join-Path $Root "curl-ca-bundle.crt") -Force
    Write-Host "  + curl-ca-bundle.crt"
} else {
    Write-Host "未在 curl 包中找到 CA 证书，改为下载 cacert.pem"
    Invoke-WebRequest -Uri "https://curl.se/ca/cacert.pem" -OutFile (Join-Path $Root "curl-ca-bundle.crt") -UseBasicParsing -TimeoutSec 120
    Write-Host "  + curl-ca-bundle.crt (cacert.pem)"
}

$Required = @("BBDown.exe", "ffmpeg.exe", "aria2c.exe", "curl.exe", "libcurl-x64.dll", "curl-ca-bundle.crt")
$Missing = $Required | Where-Object { -not (Test-Path (Join-Path $Root $_)) }
if ($Missing) {
    throw "缺少必要文件: $($Missing -join ', ')"
}

Write-Host ""
Write-Host "第三方二进制就绪："
Get-ChildItem $Root -File | Where-Object {
    $_.Name -in $Required -or $_.Extension -eq ".dll"
} | Select-Object Name, Length | Format-Table -AutoSize



