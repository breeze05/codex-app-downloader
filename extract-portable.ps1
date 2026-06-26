<#
.SYNOPSIS
    免安装方式使用 OpenAI Codex App — 将 MSIX 当作 ZIP 解压到目标目录。

.DESCRIPTION
    MSIX 本质是 ZIP 压缩包。本脚本将其解压到指定目录，无需通过 Add-AppxPackage 安装。
    解压后可直接运行目录内的可执行文件，适合无管理员权限或不想注册应用包的场景。

    注意：免安装方式无法使用 MSIX 的沙箱隔离、自动更新等特性，部分功能可能受限。

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

# MSIX is a ZIP; use System.IO.Compression to extract
Add-Type -AssemblyName System.IO.Compression.FileSystem

try {
    [System.IO.Compression.ZipFile]::ExtractToDirectory($MsixPath, $DestDir)
} catch {
    # Fallback: use Expand-Archive (rename to .zip first)
    Write-Host "  System.IO.Compression 失败，尝试 Expand-Archive 备选方案..." -ForegroundColor DarkYellow
    $tempZip = [System.IO.Path]::ChangeExtension($MsixPath, ".zip")
    Copy-Item -LiteralPath $MsixPath -Destination $tempZip -Force
    try {
        Expand-Archive -LiteralPath $tempZip -DestinationPath $DestDir -Force
    } finally {
        Remove-Item -LiteralPath $tempZip -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "[3/3] 解压完成！" -ForegroundColor Green

# --- Find executable ---
Write-Host ""
Write-Host "查找可执行文件..." -ForegroundColor Cyan

$exeFiles = Get-ChildItem -Path $DestDir -Filter "*.exe" -File -Recurse -ErrorAction SilentlyContinue
$appxManifest = Get-ChildItem -Path $DestDir -Filter "AppxManifest.xml" -File -ErrorAction SilentlyContinue | Select-Object -First 1

if ($appxManifest) {
    Write-Host ""
    Write-Host "  应用清单: $($appxManifest.FullName)" -ForegroundColor Green
    try {
        [xml]$manifest = Get-Content -Raw -LiteralPath $appxManifest.FullName
        $appId = $manifest.Package.Applications.Application.Id
        $appExe = $manifest.Package.Applications.Application.Executable
        Write-Host "  应用 ID  : $appId" -ForegroundColor Green
        Write-Host "  可执行文件: $appExe" -ForegroundColor Green
    } catch {
        Write-Host "  (无法解析 AppxManifest.xml)" -ForegroundColor DarkYellow
    }
}

if ($exeFiles) {
    Write-Host ""
    Write-Host "  发现以下可执行文件：" -ForegroundColor Green
    foreach ($exe in $exeFiles) {
        $relPath = $exe.FullName.Substring($DestDir.Length).TrimStart('\', '/')
        Write-Host "    $relPath" -ForegroundColor White
    }

    # Highlight the main application executable
    $mainExe = $exeFiles | Where-Object { $_.Name -match 'codex' } | Select-Object -First 1
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
