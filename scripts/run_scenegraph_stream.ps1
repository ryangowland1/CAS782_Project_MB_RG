param(
    [switch]$Mock,
    [int]$Ticks = 0,
    [double]$Interval = 1.0,
    [string]$CarlaAddress = "127.0.0.1",
    [int]$Port = 2000,
    [string]$OutDir = ".\data\stream"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$python = [System.IO.Path]::GetFullPath($python)

if (-not (Test-Path $python)) {
    Write-Error "Python venv not found at $python"
    exit 1
}

$script = Join-Path $PSScriptRoot "..\src\scenegraph_stream_bridge.py"
$script = [System.IO.Path]::GetFullPath($script)

$argsList = @(
    $script,
    "--out-dir", $OutDir,
    "--interval", "$Interval",
    "--ticks", "$Ticks",
    "--carla-address", $CarlaAddress,
    "--port", "$Port"
)

if ($Mock) {
    $argsList += "--mock"
}

Write-Host "Running scene graph stream bridge..."
Write-Host "  Script: $script"
Write-Host "  Output: $OutDir"
Write-Host "  Mock:   $Mock"

& $python @argsList
