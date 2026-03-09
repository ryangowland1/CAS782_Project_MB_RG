<#
.SYNOPSIS
    Complete one-file setup script for CAS782 CARLA + VIATRA project.

.DESCRIPTION
    This script automates all post-clone setup steps:
    - Creates Python virtual environment (.venv)
    - Installs CARLA wheel from included source
    - Verifies directory structure
    - Validates all components

    PREREQUISITES: See PREREQUISITES.md before running this script.

.EXAMPLE
    .\SETUP.ps1

.NOTES
    - Requires Python 3.8+ in PATH
    - Requires PowerShell ExecutionPolicy set to RemoteSigned (see PREREQUISITES.md)
    - Run from repository root directory
#>

param(
    [switch]$SkipPythonCheck = $false,
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = $scriptDir

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════╗"
Write-Host "║  CAS782 Project Setup Script                                  ║"
Write-Host "║  CARLA 0.9.16 + VIATRA Scene Graph Stream                     ║"
Write-Host "╚════════════════════════════════════════════════════════════════╝"
Write-Host ""

# ============================================================================
# SECTION 1: Prerequisite Checks
# ============================================================================

function Check-Prerequisite {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$ErrorMsg
    )

    Write-Host "  Checking: $Name ... " -NoNewline

    try {
        $null = & $Command 2>$null
        Write-Host "✓" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "✗ FAILED" -ForegroundColor Red
        Write-Host "  Error: $ErrorMsg" -ForegroundColor Yellow
        return $false
    }
}

function Check-File {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Description
    )

    Write-Host "  Checking: $Description ... " -NoNewline

    if (Test-Path $Path) {
        Write-Host "✓" -ForegroundColor Green
        return $true
    }
    else {
        Write-Host "✗ NOT FOUND" -ForegroundColor Red
        Write-Host "  Expected: $Path" -ForegroundColor Yellow
        return $false
    }
}

Write-Host "STEP 1: Verifying Prerequisites"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$checks = @()

if (-not $SkipPythonCheck) {
    $checks += Check-Prerequisite -Name "Python 3.8+" -Command "python --version" `
        -ErrorMsg "Python not in PATH. See PREREQUISITES.md section 2.B"
}

$checks += Check-File -Path "$repoRoot\CarlaUE4.exe" -Description "CARLA binary (CarlaUE4.exe)"
$checks += Check-File -Path "$repoRoot\PythonAPI\carla\dist\carla-0.9.16-cp312-cp312-win_amd64.whl" `
    -Description "CARLA Python wheel"
$checks += Check-File -Path "$repoRoot\queries\SceneGraph.ecore" -Description "Metamodel (SceneGraph.ecore)"
$checks += Check-File -Path "$repoRoot\queries\scenegraph.vql" -Description "VIATRA queries (scenegraph.vql)"

if ($checks -contains $false) {
    Write-Host ""
    Write-Host "✗ SETUP FAILED: Some prerequisites are missing." -ForegroundColor Red
    Write-Host "  Please follow PREREQUISITES.md before running this script." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✓ All prerequisites found" -ForegroundColor Green
Write-Host ""

# ============================================================================
# SECTION 2: Virtual Environment Setup
# ============================================================================

Write-Host "STEP 2: Setting Up Python Virtual Environment"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$venvPath = Join-Path $repoRoot ".venv"

if (Test-Path $venvPath) {
    Write-Host "  Virtual environment already exists at: $venvPath"
    if (-not $Force) {
        $response = Read-Host "  Remove and recreate? (y/n)"
        if ($response -ne "y") {
            Write-Host "  Skipping venv recreation"
        }
        else {
            Write-Host "  Removing old venv ... " -NoNewline
            Remove-Item -Recurse -Force $venvPath | Out-Null
            Write-Host "✓" -ForegroundColor Green
            python -m venv $venvPath
        }
    }
}
else {
    Write-Host "  Creating virtual environment at: $venvPath"
    python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ FAILED to create venv" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ Virtual environment created" -ForegroundColor Green
}

# Activate venv
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-Host "✗ FAILED: Cannot find activation script" -ForegroundColor Red
    exit 1
}

Write-Host "  Activating virtual environment ... " -NoNewline
& $activateScript
Write-Host "✓" -ForegroundColor Green

Write-Host ""

# ============================================================================
# SECTION 3: Install CARLA Python API
# ============================================================================

Write-Host "STEP 3: Installing CARLA Python API"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$wheelPath = Join-Path $repoRoot "PythonAPI\carla\dist\carla-0.9.16-cp312-cp312-win_amd64.whl"

Write-Host "  Installing: carla-0.9.16-cp312-cp312-win_amd64.whl"
Write-Host "  From: $wheelPath"
Write-Host ""

python -m pip install --upgrade pip --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠ Warning: pip upgrade had issues (continuing)" -ForegroundColor Yellow
}

python -m pip install "$wheelPath" --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ CARLA wheel installed successfully" -ForegroundColor Green
}
else {
    Write-Host "✗ FAILED to install CARLA wheel" -ForegroundColor Red
    Write-Host "  Try running: python -m pip install '$wheelPath'" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# ============================================================================
# SECTION 4: Verify CARLA Import
# ============================================================================

Write-Host "STEP 4: Verifying CARLA Module"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$testScript = @"
try:
    import carla
    print(f'CARLA version: {carla.__version__}')
    print('SUCCESS')
except Exception as e:
    print(f'ERROR: {e}')
"@

$output = python -c $testScript

if ($output -match "SUCCESS") {
    Write-Host "  ✓ CARLA module imports successfully" -ForegroundColor Green
    Write-Host "  Version: $($output -match 'CARLA version: \d+\.\d+\.\d+' | ForEach-Object { $_ })"
}
else {
    Write-Host "✗ FAILED to import CARLA module" -ForegroundColor Red
    Write-Host "  Output: $output" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# ============================================================================
# SECTION 5: Verify Directory Structure
# ============================================================================

Write-Host "STEP 5: Verifying Directory Structure"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$requiredDirs = @(
    "data",
    "data\stream",
    "data\stream\snapshots",
    "src",
    "scripts",
    "queries",
    "PythonAPI",
    "logs"
)

$missingDirs = @()

foreach ($dir in $requiredDirs) {
    $fullPath = Join-Path $repoRoot $dir
    if (Test-Path $fullPath) {
        Write-Host "  ✓ $dir" -ForegroundColor Green
    }
    else {
        Write-Host "  ✗ $dir (MISSING - creating)" -ForegroundColor Yellow
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        $missingDirs += $dir
    }
}

if ($missingDirs.Count -gt 0) {
    Write-Host "  Created: $($missingDirs -join ', ')" -ForegroundColor Green
}

Write-Host ""

# ============================================================================
# SECTION 6: Summary & Next Steps
# ============================================================================

Write-Host "STEP 6: Setup Summary"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host ""
Write-Host "✓ SETUP COMPLETE!" -ForegroundColor Green
Write-Host ""
Write-Host "Summary:"
Write-Host "  • Python virtual environment: $venvPath"
Write-Host "  • CARLA API: Installed (v0.9.16)"
Write-Host "  • Metamodel: $repoRoot\queries\SceneGraph.ecore"
Write-Host "  • VIATRA Queries: $repoRoot\queries\scenegraph.vql"
Write-Host "  • CARLA Binary: $repoRoot\CarlaUE4.exe"
Write-Host ""

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "NEXT STEPS:"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host ""
Write-Host "1. ACTIVATE VIRTUAL ENVIRONMENT (in each new terminal):"
Write-Host ""
Write-Host "   .\.venv\Scripts\Activate.ps1"
Write-Host ""

Write-Host "2. VERIFY CARLA SERVER:"
Write-Host ""
Write-Host "   .\CarlaUE4.exe -quality-level=Low -windowed 2>/dev/null &"
Write-Host "   (Server will listen on 127.0.0.1:2000 by default)"
Write-Host ""

Write-Host "3. RUN A DEMO (in a new terminal with .venv activated):"
Write-Host ""
Write-Host "   python .\src\carla_scenegraph_export.py --mock --output .\data\demo.xmi"
Write-Host ""

Write-Host "4. START LIVE STREAM BRIDGE:"
Write-Host ""
Write-Host "   python .\src\scenegraph_stream_bridge.py --ticks 0"
Write-Host ""

Write-Host "5. READ QUICK START GUIDE:"
Write-Host ""
Write-Host "   See QUICKSTART.md for full instructions"
Write-Host "   See STREAM_REFERENCE.md for stream file locations"
Write-Host "   See VIATRA_STREAM_GUIDE.md for Eclipse integration"
Write-Host ""

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host ""
Write-Host "Questions? See PREREQUISITES.md or contact your instructor."
Write-Host ""
