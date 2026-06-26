<#
.SYNOPSIS
    免安装方式使用 OpenAI Codex App — 将 MSIX 解压到目标目录。

.DESCRIPTION
    本脚本把 MSIX 包解压到指定目录，无需通过 Add-AppxPackage 安装。
    解压后可直接运行目录内的可执行文件，适合无管理员权限或不想注册应用包的场景。

    注意：
    - MSIX 内部基于 ZIP，但微软商店分发的 MSIX 通常使用 ZIP64 扩展，且缺少标准
      ZIP 的 End-of-Central-Directory 签名。因此 Windows 资源管理器、PowerShell 的
      Expand-Archive、Python zipfile 等标准工具会报错“不是有效的 zip 文件”。
    - 本脚本优先使用 Windows 10/11 自带的 tar（基于 libarchive/bsdtar）或 7-Zip 解压。

    免安装方式无法使用 MSIX 的沙箱隔离、自动更新等特性，部分功能可能受限。

.PARAMETER MsixPath
    MSIX 文件路径。默认为脚本同目录下的 .msix 文件。

.PARAMETER DestDir
    解压目标目录。默认为脚本同目录下的 codex-portable 子文件夹。

.EXAMPLE
    .\extract-portable.ps1
    使用默认路径解压。

.EXAMPLE
    .\extract-portable.ps1 -MsixPath "C:\Downloads\Codex.msix" -DestDir "D:\Apps\Codex"
    指定自定义路径。
#>

param(
    [string]$MsixPath = "",
    [string]$DestDir = ""
)

$ErrorActionPreference = "Stop"

# --- Resolve MSIX path ---
if ([string]::IsNullOrWhiteSpace($MsixPath)) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $candidates = Get-ChildItem -Path $scriptDir -Filter "*.msix" -File -ErrorAction SilentlyContinue
    if ($candidates.Count -eq 0) {
        throw "未找到 .msix 文件。请用 -MsixPath 指定路径，或将 .msix 放在脚本同目录。"
    }
    if ($candidates.Count -gt 1) {
        Write-Host "找到多个 MSIX 文件，使用第一个：$($candidates[0].Name)"
    }
    $MsixPath = $candidates[0].FullName
}

if (-not (Test-Path -LiteralPath $MsixPath)) {
    throw "MSIX 文件不存在：$MsixPath"
}

# --- Resolve destination directory ---
if ([string]::IsNullOrWhiteSpace($DestDir)) {
    $DestDir = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "codex-portable"
}

$DestDir = [System.IO.Path]::GetFullPath($DestDir)

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Codex 免安装解压工具" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  MSIX 文件 : $MsixPath"
Write-Host "  解压目录   : $DestDir"
Write-Host ""

# --- Extract ---
if (Test-Path -LiteralPath $DestDir) {
    Write-Host "[1/3] 目标目录已存在，正在清空..." -ForegroundColor Yellow
    Remove-Item -LiteralPath $DestDir -Recurse -Force
}

Write-Host "[2/3] 正在解压 MSIX ..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path $DestDir -Force | Out-Null

$extracted = $false

# 1. Try Windows built-in tar (libarchive/bsdtar) - best MSIX/ZIP64 support
$tar = Get-Command -Name tar -ErrorAction SilentlyContinue
if ($tar) {
    Write-Host "  使用 tar (libarchive) 解压..." -ForegroundColor DarkYellow
    $proc = Start-Process -FilePath $tar.Source -ArgumentList @("-xf", $MsixPath, "-C", $DestDir) -NoNewWindow -Wait -PassThru
    if ($proc.ExitCode -eq 0 -or $proc.ExitCode -eq 1) {
        # bsdtar may return 1 on non-fatal decompression errors
        $extracted = $true
    }
}

# 2. Try 7-Zip
if (-not $extracted) {
    $sevenZipPaths = @(
        "${env:ProgramFiles}\7-Zip\7z.exe",
        "${env:ProgramFiles(x86)}\7-Zip\7z.exe",
        (Join-Path $env:LOCALAPPDATA "7-Zip\7z.exe")
    )
    foreach ($sevenZip in $sevenZipPaths) {
        if (Test-Path -LiteralPath $sevenZip) {
            Write-Host "  使用 7-Zip 解压：$sevenZip ..." -ForegroundColor DarkYellow
            $proc = Start-Process -FilePath $sevenZip -ArgumentList @("x", $MsixPath, "-o$DestDir", "-y") -NoNewWindow -Wait -PassThru
            if ($proc.ExitCode -eq 0) {
                $extracted = $true
                break
            }
        }
    }
}

# 3. Last resort: .NET ZipFile / Expand-Archive (unlikely to work for store MSIX)
if (-not $extracted) {
    Write-Host "  尝试使用 .NET ZipFile 解压（多数商店 MSIX 会失败）..." -ForegroundColor DarkYellow
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($MsixPath, $DestDir)
        $extracted = $true
    } catch {
        Write-Host "  .NET ZipFile 失败：$_" -ForegroundColor Red
        Write-Host "  请安装 7-Zip (https://www.7-zip.org/) 后重试。" -ForegroundColor Red
        throw "无法解压此 MSIX 文件。标准 ZIP 工具不支持该文件的 ZIP64 格式。"
    }
}

Write-Host "[3/3] 解压完成！" -ForegroundColor Green

# --- Find executable ---
Write-Host ""
Write-Host "查找可执行文件..." -ForegroundColor Cyan

$exeFiles = Get-ChildItem -Path $DestDir -Filter "*.exe" -File -Recurse -ErrorAction SilentlyContinue

if ($exeFiles) {
    Write-Host ""
    Write-Host "  发现以下可执行文件：" -ForegroundColor Green
    foreach ($exe in $exeFiles) {
        $relPath = $exe.FullName.Substring($DestDir.Length).TrimStart('\', '/')
        Write-Host "    $relPath" -ForegroundColor White
    }

    # The main executable is usually Codex.exe inside the app folder
    $mainExe = $exeFiles | Where-Object { $_.Name -ieq 'Codex.exe' } | Select-Object -First 1
    if (-not $mainExe) { $mainExe = $exeFiles | Where-Object { $_.Name -match 'codex' } | Select-Object -First 1 }
    if (-not $mainExe) { $mainExe = $exeFiles | Select-Object -First 1 }

    Write-Host ""
    Write-Host "  推荐启动: $($mainExe.FullName)" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "  快捷方式已创建：" -ForegroundColor Cyan
    $shortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "Codex.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $mainExe.FullName
    $shortcut.WorkingDirectory = Split-Path -Parent $mainExe.FullName
    $shortcut.IconLocation = $mainExe.FullName
    $shortcut.Save()
    Write-Host "    $shortcutPath" -ForegroundColor Green
} else {
    Write-Host "  未找到 .exe 文件，请检查解压目录内容。" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  解压完成！解压目录：$DestDir" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "提示：如果 tar 解压报错但生成了文件，通常可以忽略非主程序文件的解压错误。" -ForegroundColor DarkYellow
Write-Host ""
