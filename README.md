# Codex App Downloader

从 Microsoft Store 下载 OpenAI Codex Windows 桌面应用的 MSIX 安装包，无需访问 Microsoft Store 或联网的 Windows 机器。

适用于 Windows 电脑无法联网、无法使用 Microsoft Store 的离线安装场景。

## 工作原理

本项目通过 Microsoft Store 的 FE3 (FrontEnd 3) SOAP 服务和 Display Catalog API，模拟 Windows Update 客户端的行为来获取应用包的下载链接。核心技术基于 [StoreLib](https://github.com/nicehash/StoreLib)（MPL-2.0）。

流程：
1. 查询 Display Catalog API 获取产品信息（PackageIdentityName、WuCategoryId 等）
2. 通过 FE3 SOAP 服务获取加密 Cookie
3. 调用 SyncUpdates 获取所有可用更新包（包括不同架构）
4. 调用 GetExtendedUpdateInfo2 获取每个包的下载 URL
5. 下载 MSIX 文件并生成安装清单

## 使用方法

### 在 macOS / Linux / Windows 上下载 MSIX

```bash
python3 download-codex-msix.py --architecture x64 --output ./downloads
```

参数：
- `--product-id`：Microsoft Store 产品 ID（默认 `9PLM9XGG6VKS`，即 OpenAI Codex）
- `--architecture`：目标架构，可选 `x64` / `x86` / `arm64` / `arm` / `all`（默认 `x64`）
- `--output`：输出目录（默认 `./microsoft-store-downloads`）
- `--market`：市场区域（默认 `US`）
- `--language`：语言（默认 `en`）
- `--force`：覆盖已下载的文件

### 在 Windows 上离线安装

1. 将下载的 MSIX 文件和 `install.ps1` 复制到 Windows 电脑
2. 以管理员身份打开 PowerShell
3. 运行安装脚本：

```powershell
.\install.ps1
```

或手动安装：

```powershell
Add-AppxPackage -Path "OpenAI.Codex_26.623.3763.0_x64__2p2nqsd0c76g0.Msix"
```

## 从 Release 直接下载

如果你只需要安装包，可以直接从本项目的 [Releases](https://github.com/breeze05/codex-app-downloader/releases) 页面下载最新的 MSIX 文件，无需运行脚本。

## 当前版本

| 字段 | 值 |
|------|-----|
| 应用名称 | OpenAI Codex |
| 版本 | 26.623.3763.0 |
| 架构 | x64 |
| 文件名 | `OpenAI.Codex_26.623.3763.0_x64__2p2nqsd0c76g0.Msix` |
| 文件大小 | 619 MB |
| SHA256 | `5cd66b91712c09264009475dbe826664d1193ff39a172a24ef1b49d58ecb70e4` |
| Store Product ID | 9PLM9XGG6VKS |

## 文件说明

| 文件 | 说明 |
|------|------|
| `download-codex-msix.py` | 主下载脚本 |
| `WUIDRequest.xml` | FE3 SyncUpdates SOAP 请求模板 |
| `FE3FileUrl.xml` | FE3 GetExtendedUpdateInfo2 SOAP 请求模板 |
| `install.ps1` | Windows 离线安装脚本 |

## 致谢

- [StoreLib](https://github.com/nicehash/StoreLib) — MPL-2.0 许可证，提供了与 Microsoft Store FE3 服务交互的核心逻辑
- [microsoft-store-package-downloader-skill](https://github.com/hanyu1212/microsoft-store-package-downloader-skill) — 提供了 PowerShell 实现参考

## 许可证

本项目代码基于 StoreLib 的 MPL-2.0 许可证发布。下载的 MSIX 包版权归 OpenAI 所有。
