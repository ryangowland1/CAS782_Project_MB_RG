param(
    [string]$ViewPath = ".\data\stream\live_view.html"
)

$ErrorActionPreference = "Stop"

$resolved = [System.IO.Path]::GetFullPath($ViewPath)
if (-not (Test-Path $resolved)) {
    Write-Error "Live view file not found at $resolved"
    exit 1
}

Write-Host "Opening $resolved"
Start-Process $resolved
