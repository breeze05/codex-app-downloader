$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifest = Get-Content -Raw -LiteralPath (Join-Path $root "package-manifest.json") | ConvertFrom-Json
$packages = @($manifest.Packages | ForEach-Object {
    Get-Item -LiteralPath (Join-Path $root $_.FileName)
})
$main = $packages | Where-Object { $_.Name -like "$($manifest.PackageIdentityName)_*" } | Select-Object -First 1
if ($null -eq $main) {
    throw "The main application package was not found."
}
$dependencies = @($packages | Where-Object FullName -ne $main.FullName)
if ($dependencies.Count -gt 0) {
    Add-AppxPackage -Path $main.FullName -DependencyPath $dependencies.FullName
} else {
    Add-AppxPackage -Path $main.FullName
}
Write-Host "$($manifest.Title) v$($manifest.Packages[0].Version) installed successfully."
