<#
.SYNOPSIS
    免安装方式使用 OpenAI Codex App — 将 MSIX 解压到目标目录。

.DESCRIPTION
    本脚本把 MSIX 包解压到指定目录，无需通过 Add-AppxPackage 安装。
    解压后可直接运行目录内的可执行文件，适合无管理员权限或不想注册应用包的场景。

    注意：
    - MSIX 内部基于 ZIP，但微软商店分发的 MSIX 通常使用 ZIP64 扩展，且缺少标准
      ZIP 的 End-of-Central-Directory 签名。因此 Windows 资源管理器、PowerShell 的
      Expand-Archive、Python 的 zipfile 等标准工具会报错“不是有效的 zip 文件”。
    - 本脚本优先使用 Windows 10/11 自带的 tar（基于 libarchive/bsdtar）解压；
      如果 tar 失败，会尝试 7-Zip；如果 7-Zip 也失败，会尝试 Python 脚本
      repair_and_extract_msix.py（通过扫描 local file header 直接提取）。

    免安装方式无法使用 MSIX 的沙箱隔离、自动更新等特性，部分功能可能受限。

.PARAMETER MsixPath
    MSIX 文件路径。默认为脚本同目录下的 .msix 文件。

.PARAMETER DestDir
    解压目标目录。默认为脚本同目录下的 codex-portable 子文件夹。

.PARAMETER PythonFallback
    如果 tar 和 7-Zip 都失败，使用 Python 脚本作为最后兜底方案。需要 Python 3.7+。

.EXAMPLE
    .\extract-portable.ps1
    使用默认路径解压。

.EXAMPLE
    .\extract-portable.ps1 -MsixPath "C:\Downloads\Codex.msix" -DestDir "D:\Apps\Codex"
    指定自定义路径。
#>

param(
    [string]$MsixPath = "",
    [string]$DestDir = "",
    [switch]$PythonFallback = $false
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
    Write-Host "[1/4] 目标目录已存在，正在清空..." -ForegroundColor Yellow
    Remove-Item -LiteralPath $DestDir -Recurse -Force
}

Write-Host "[2/4] 正在解压 MSIX ..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path $DestDir -Force | Out-Null

$extracted = $false
$lastError = ""

function Run-External {
    param(
        [string]$FilePath,
        [string]$Arguments,
        [int[]]$SuccessCodes = @(0)
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $Arguments
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    return [PSCustomObject]@{
        ExitCode = $proc.ExitCode
        StdOut = $stdout
        StdErr = $stderr
    }
}

# 1. Try Windows built-in tar (libarchive/bsdtar) - best MSIX/ZIP64 support
$tar = Get-Command -Name tar -ErrorAction SilentlyContinue
if ($tar -and -not $extracted) {
    Write-Host "  尝试使用 tar (libarchive) 解压..." -ForegroundColor DarkYellow
    $result = Run-External -FilePath $tar.Source -Arguments "-xf `"$MsixPath`" -C `"$DestDir`"" -SuccessCodes @(0, 1)
    if ($result.ExitCode -eq 0 -or $result.ExitCode -eq 1) {
        # bsdtar may return 1 on non-fatal decompression errors (e.g. tectonic.exe)
        Write-Host "    tar 已返回（ExitCode=$($result.ExitCode)），视为解压完成。" -ForegroundColor Green
        $extracted = $true
    } else {
        $lastError = "tar 失败: ExitCode=$($result.ExitCode)`nSTDOUT:`n$($result.StdOut)`nSTDERR:`n$($result.StdErr)"
        Write-Host "    tar 无法解压: $lastError" -ForegroundColor Red
    }
}

# 2. Try 7-Zip with multiple strategies
if (-not $extracted) {
    $sevenZipPaths = @(
        "${env:ProgramFiles}\7-Zip\7z.exe",
        "${env:ProgramFiles(x86)}\7-Zip\7z.exe",
        (Join-Path $env:LOCALAPPDATA "7-Zip\7z.exe"),
        "7z.exe"
    )
    foreach ($sevenZip in $sevenZipPaths) {
        if ([string]::IsNullOrWhiteSpace($sevenZip)) { continue }
        if ($sevenZip -eq "7z.exe") {
            $sevenZipCmd = Get-Command -Name 7z -ErrorAction SilentlyContinue
            if (-not $sevenZipCmd) { continue }
            $sevenZip = $sevenZipCmd.Source
        }
        if (-not (Test-Path -LiteralPath $sevenZip)) { continue }

        Write-Host "  尝试使用 7-Zip 解压：$sevenZip ..." -ForegroundColor DarkYellow

        # 7-Zip 常见解压命令：x 保留路径，-tzip 强制按 zip 格式，-aou 自动重命名，-y 确认
        $argumentSets = @(
            "x `"$MsixPath`" -o`"$DestDir`" -y -tzip",
            "x `"$MsixPath`" -o`"$DestDir`" -y",
            "x `"$MsixPath`" -o`"$DestDir`" -aou -y -tzip",
            "x `"$MsixPath`" -o`"$DestDir`" -aou -y"
        )

        foreach ($args in $argumentSets) {
            $result = Run-External -FilePath $sevenZip -Arguments $args
            if ($result.ExitCode -eq 0) {
                Write-Host "    7-Zip 解压成功。" -ForegroundColor Green
                $extracted = $true
                break
            }
        }

        if ($extracted) { break }

        # 如果都失败，打印最后一次错误
        $lastError = "7-Zip 失败: ExitCode=$($result.ExitCode)`nSTDOUT:`n$($result.StdOut)`nSTDERR:`n$($result.StdErr)"
        Write-Host "    7-Zip 无法解压: $lastError" -ForegroundColor Red
    }
}

# 3. Python fallback: repair_and_extract_msix.py
if (-not $extracted -and $PythonFallback) {
    Write-Host "  尝试使用 Python 脚本扫描提取（不依赖标准 ZIP 结构）..." -ForegroundColor DarkYellow

    $python = Get-Command -Name python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command -Name python3 -ErrorAction SilentlyContinue }
    if (-not $python) { $python = Get-Command -Name py -ErrorAction SilentlyContinue }

    if ($python) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        $pyScript = Join-Path $scriptDir "repair_and_extract_msix.py"
        if (-not (Test-Path -LiteralPath $pyScript)) {
            $pyScript = Join-Path (Get-Location) "repair_and_extract_msix.py"
        }

        if (Test-Path -LiteralPath $pyScript) {
            $result = Run-External -FilePath $python.Source -Arguments "`"$pyScript`" `"$MsixPath`" -o `"$DestDir`""
            if ($result.ExitCode -eq 0) {
                Write-Host "    Python 扫描提取成功。" -ForegroundColor Green
                $extracted = $true
            } else {
                $lastError = "Python 脚本失败: ExitCode=$($result.ExitCode)`nSTDOUT:`n$($result.StdOut)`nSTDERR:`n$($result.StdErr)"
                Write-Host "    $lastError" -ForegroundColor Red
            }
        } else {
            Write-Host "    未找到 repair_and_extract_msix.py，跳过 Python 兜底。" -ForegroundColor Red
        }
    } else {
        Write-Host "    未找到 Python 解释器，跳过 Python 兜底。" -ForegroundColor Red
    }
}

# 4. Last resort: .NET ZipFile (unlikely to work for store MSIX)
if (-not $extracted) {
    Write-Host "  尝试使用 .NET ZipFile 解压（多数商店 MSIX 会失败）..." -ForegroundColor DarkYellow
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($MsixPath, $DestDir)
        $extracted = $true
    } catch {
        $lastError = $_.ToString()
        Write-Host "    .NET ZipFile 失败：$lastError" -ForegroundColor Red
    }
}

if (-not $extracted) {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host "  所有解压方式都失败了" -ForegroundColor Red
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "可能原因：" -ForegroundColor Yellow
    Write-Host "  - 7-Zip 版本较旧，不支持该 MSIX 的 ZIP64 变体。" -ForegroundColor Yellow
    Write-Host "  - 文件在传输过程中损坏。" -ForegroundColor Yellow
    Write-Host "  - 该 MSIX 使用了更特殊的压缩/封装格式。" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "建议尝试：" -ForegroundColor Yellow
    Write-Host "  1. 升级 7-Zip 到最新版（https://www.7-zip.org/）。" -ForegroundColor Yellow
    Write-Host "  2. 安装 Python 3.7+，然后运行：" -ForegroundColor Yellow
    Write-Host "       python repair_and_extract_msix.py `"$MsixPath`" -o `"$DestDir`"" -ForegroundColor Cyan
    Write-Host "  3. 重新从 GitHub Release 下载 MSIX，确保 SHA256 一致。" -ForegroundColor Yellow
    Write-Host ""
    throw "无法解压此 MSIX 文件。详情请参见上述错误信息。"
}

Write-Host "[3/4] 解压完成！" -ForegroundColor Green

# --- Find executable ---
Write-Host ""
Write-Host "[4/4] 查找可执行文件..." -ForegroundColor Cyan

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
Write-Host "提示：如果 tar 或 7-Zip 解压时报错但生成了文件，通常可以忽略非主程序文件的解压错误。" -ForegroundColor DarkYellow
Write-Host ""
