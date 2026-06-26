$ErrorActionPreference = "Stop"

<#
.SYNOPSIS
    离线安装 OpenAI Codex App（MSIX 包）。

.DESCRIPTION
    本脚本在目标 Windows 电脑上调用 Add-AppxPackage 注册 MSIX 应用包。

    权限说明：
    - 在大多数 Windows 10/11 家庭版/专业版上，Add-AppxPackage 可以为当前用户
      安装应用包，无需管理员权限。
    - 但在企业环境、组策略限制旁加载（sideloading）或 Developer mode 未开启的
      电脑上，可能需要以管理员身份运行 PowerShell。
    - 如果没有管理员权限且安装被拒绝，请改用 extract-portable.ps1 进行免安装
      解压，直接运行解压后的 Codex.exe。

.PARAMETER MsixPath
    MSIX 文件路径。默认为脚本同目录下的 .msix 文件。

.EXAMPLE
    .\install.ps1
    使用默认路径安装。

.EXAMPLE
    .\install.ps1 -MsixPath "C:\Downloads\OpenAI.Codex_26.623.3763.0_x64__2p2nqsd0c76g0.Msix"
    指定自定义路径。
#>

param(
    [string]$MsixPath = ""
)

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

$MsixPath = [System.IO.Path]::GetFullPath($MsixPath)

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Codex 离线安装脚本" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  MSIX 文件 : $MsixPath"
Write-Host ""

# --- Install ---
try {
    Add-AppxPackage -Path $MsixPath
    Write-Host ""
    Write-Host "安装成功。" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "安装失败：$_" -ForegroundColor Red
    Write-Host ""
    Write-Host "可能的原因：" -ForegroundColor Yellow
    Write-Host "  1. 当前 PowerShell 不是以管理员身份运行，且系统策略禁止旁加载应用包。" -ForegroundColor Yellow
    Write-Host "  2. 系统未开启 Developer mode 或 Sideload apps。" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "解决方案：" -ForegroundColor Yellow
    Write-Host "  - 以管理员身份运行 PowerShell 后重试：" -ForegroundColor Yellow
    Write-Host "      .\install.ps1" -ForegroundColor Yellow
    Write-Host "  - 或改用免安装解压脚本（无需管理员权限）：" -ForegroundColor Yellow
    Write-Host "      .\extract-portable.ps1" -ForegroundColor Yellow
    throw
}
