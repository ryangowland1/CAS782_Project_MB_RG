param(
    [switch]$Mock,
    [double]$Interval = 1.0,
    [string]$CarlaRoot = "C:\carla-src\carla",
    [string]$CarlaAddress = "127.0.0.1",
    [int]$Port = 2000
)

$ErrorActionPreference = "Stop"

if (-not $Mock) {
    Write-Host "Starting CARLA server in a new PowerShell window..."
    $launchScript = Join-Path $PSScriptRoot "start_carla_server.ps1"
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-File", $launchScript,
        "-CarlaRoot", $CarlaRoot
    ) | Out-Null

    Write-Host "Waiting 15 seconds for CARLA server startup..."
    Start-Sleep -Seconds 15
}

Write-Host "Starting scene graph stream bridge in a new PowerShell window..."
$streamScript = Join-Path $PSScriptRoot "run_scenegraph_stream.ps1"
$startArgs = @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", $streamScript,
    "-Interval", "$Interval",
    "-CarlaAddress", $CarlaAddress,
    "-Port", "$Port"
)
if ($Mock) {
    $startArgs += "-Mock"
}
Start-Process powershell -ArgumentList $startArgs | Out-Null

Write-Host "Waiting 3 seconds before opening live view..."
Start-Sleep -Seconds 3

$viewScript = Join-Path $PSScriptRoot "open_live_view.ps1"
powershell -ExecutionPolicy Bypass -File $viewScript

Write-Host "dev_up complete."
Write-Host "- Live view should be open in your browser"
Write-Host "- Stream files are under data/stream"
if (-not $Mock) {
    Write-Host "- CARLA server should be running in its own window"
}
