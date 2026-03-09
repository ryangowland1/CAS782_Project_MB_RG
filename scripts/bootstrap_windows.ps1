param(
    [string]$CarlaRoot = "C:\carla-src\carla",
    [string]$UnrealRoot = "C:\carla-src\UnrealEngine"
)

$ErrorActionPreference = "Stop"

function Test-Tool {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Command
    )

    try {
        $null = Get-Command $Command -ErrorAction Stop
        Write-Host "[OK] $Name found ($Command)"
        return $true
    }
    catch {
        Write-Warning "[MISSING] $Name not found in PATH ($Command)"
        return $false
    }
}

Write-Host "Checking Windows prerequisites for CARLA + VIATRA..."

$checks = @(
    (Test-Tool -Name "Git" -Command "git"),
    (Test-Tool -Name "CMake" -Command "cmake"),
    (Test-Tool -Name "GNU Make" -Command "make"),
    (Test-Tool -Name "Python" -Command "python")
)

if ($env:UE4_ROOT) {
    Write-Host "[OK] UE4_ROOT is set to: $($env:UE4_ROOT)"
}
else {
    Write-Warning "UE4_ROOT is not set. Set it to your Unreal Engine CARLA fork path."
}

if (Test-Path $CarlaRoot) {
    Write-Host "[OK] CARLA root exists: $CarlaRoot"
}
else {
    Write-Warning "CARLA root not found at: $CarlaRoot"
}

if (Test-Path $UnrealRoot) {
    Write-Host "[OK] Unreal root exists: $UnrealRoot"
}
else {
    Write-Warning "Unreal root not found at: $UnrealRoot"
}

if ($checks -contains $false) {
    Write-Warning "Some prerequisites are missing. See docs/windows_setup_carla_viatra.md"
    exit 1
}

Write-Host "All command-line prerequisite checks completed."
Write-Host "Next steps:"
Write-Host "  1) Build Unreal fork"
Write-Host "  2) Build CARLA (make PythonAPI, make launch)"
Write-Host "  3) Install VIATRA in Eclipse from release update site"
