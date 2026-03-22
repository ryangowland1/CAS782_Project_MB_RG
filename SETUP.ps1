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
    - Requires Python 3.8-3.12 in PATH (Python 3.12 recommended for included wheel)
    - Python 3.13+ is NOT supported
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
Write-Host "================================================================="
Write-Host "  CAS782 Project Setup Script"
Write-Host "  CARLA 0.9.16 + VIATRA Scene Graph Stream"
Write-Host "================================================================="
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
        $result = Invoke-Expression "$Command 2>&1"
        if ($LASTEXITCODE -eq 0 -or $result) {
            Write-Host "[OK]" -ForegroundColor Green
            return $true
        }
        else {
            Write-Host "[FAILED]" -ForegroundColor Red
            Write-Host "  Error: $ErrorMsg" -ForegroundColor Yellow
            return $false
        }
    }
    catch {
        Write-Host "[FAILED]" -ForegroundColor Red
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
        Write-Host "[OK]" -ForegroundColor Green
        return $true
    }
    else {
        Write-Host "[NOT FOUND]" -ForegroundColor Red
        Write-Host "  Expected: $Path" -ForegroundColor Yellow
        return $false
    }
}

Write-Host "STEP 1: Verifying Prerequisites"
Write-Host "-----------------------------------------------------------------"

$checks = @()

if (-not $SkipPythonCheck) {
    $checks += Check-Prerequisite -Name "Python 3.8+" -Command "python --version" `
        -ErrorMsg "Python not in PATH. See PREREQUISITES.md section 2.B"
}

$checks += Check-File -Path "$repoRoot\SceneGraphModel\model\sceneGraphModel.ecore" -Description "Metamodel (SceneGraph.ecore)"
$checks += Check-File -Path "$repoRoot\SceneGraphQueries\src\queries\scenegraph.vql" -Description "VIATRA queries (scenegraph.vql)"

if ($checks -contains $false) {
    Write-Host ""
    Write-Host "[X] SETUP FAILED: Some prerequisites are missing." -ForegroundColor Red
    Write-Host "  Please follow PREREQUISITES.md before running this script." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[OK] All prerequisites found" -ForegroundColor Green
Write-Host ""

# ============================================================================
# SECTION 2: Download and Install CARLA 0.9.16
# ============================================================================

Write-Host "STEP 2: Installing CARLA 0.9.16"
Write-Host "-----------------------------------------------------------------"

$carlaPath = "$repoRoot\CARLA_0.9.16"
$carlaExe = "$carlaPath\CarlaUE4.exe"

if (Test-Path $carlaExe) {
    Write-Host "  [OK] CARLA 0.9.16 already installed at: $carlaPath" -ForegroundColor Green
}
else {
    Write-Host "  Downloading CARLA 0.9.16 (this may take several minutes)..."
    Write-Host "  Download size: ~8GB | Extracted size: ~20GB"
    Write-Host ""
    
    $carlaUrl = "https://carla-releases.s3.us-east-005.backblazeb2.com/Windows/CARLA_0.9.16.zip"
    $carlaZip = "$repoRoot\CARLA_0.9.16.zip"
    
    try {
        # Download CARLA
        Write-Host "  Downloading from: $carlaUrl" -ForegroundColor Cyan
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $carlaUrl -OutFile $carlaZip -UseBasicParsing
        $ProgressPreference = 'Continue'
        Write-Host "  [OK] Download complete" -ForegroundColor Green
        
        # Extract CARLA
        Write-Host "  Extracting CARLA (this may take several minutes)..." -ForegroundColor Cyan
        Expand-Archive -Path $carlaZip -DestinationPath $carlaPath -Force
        Write-Host "  [OK] Extraction complete" -ForegroundColor Green
        
        # Clean up zip file
        Write-Host "  Cleaning up download file..." -NoNewline
        Remove-Item $carlaZip -Force
        Write-Host " [OK]" -ForegroundColor Green
        
        # Verify installation
        if (Test-Path $carlaExe) {
            Write-Host "  [OK] CARLA installed successfully at: $carlaPath" -ForegroundColor Green
        }
        else {
            Write-Host "  [X] CARLA installation verification failed" -ForegroundColor Red
            Write-Host "  Expected executable at: $carlaExe" -ForegroundColor Yellow
            exit 1
        }
    }
    catch {
        Write-Host "  [X] FAILED to download/install CARLA" -ForegroundColor Red
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "  You can manually download from: $carlaUrl" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""

# ============================================================================
# SECTION 3: Virtual Environment Setup
# ============================================================================

Write-Host "STEP 3: Setting Up Python Virtual Environment"
Write-Host "-----------------------------------------------------------------"

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
            Write-Host "[OK]" -ForegroundColor Green
            python -m venv $venvPath
        }
    }
}
else {
    Write-Host "  Creating virtual environment at: $venvPath"
    python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] FAILED to create venv" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Virtual environment created" -ForegroundColor Green
}

# Activate venv
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-Host "[X] FAILED: Cannot find activation script" -ForegroundColor Red
    exit 1
}

Write-Host "  Activating virtual environment ... " -NoNewline
& $activateScript
Write-Host "[OK]" -ForegroundColor Green

Write-Host ""

# ============================================================================
# SECTION 4: Install CARLA Python API
# ============================================================================

Write-Host "STEP 4: Installing CARLA Python API"
Write-Host "-----------------------------------------------------------------"

$wheelPath = Join-Path $repoRoot "PythonAPI\carla\dist\carla-0.9.16-cp312-cp312-win_amd64.whl"

Write-Host "  Installing: carla-0.9.16-cp312-cp312-win_amd64.whl"
Write-Host "  From: $wheelPath"
Write-Host ""

python -m pip install --upgrade pip --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [WARNING] pip upgrade had issues (continuing)" -ForegroundColor Yellow
}

python -m pip install "$wheelPath" --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] CARLA wheel installed successfully" -ForegroundColor Green
}
else {
    Write-Host "[X] FAILED to install CARLA wheel" -ForegroundColor Red
    Write-Host "  Try running: python -m pip install '$wheelPath'" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# ============================================================================
# SECTION 5: Verify CARLA Import
# ============================================================================

Write-Host "STEP 5: Verifying CARLA Module"
Write-Host "-----------------------------------------------------------------"

$testScript = @"
try:
    import carla
    print('CARLA module import OK')
    print('SUCCESS')
except Exception as e:
    print(f'ERROR: {e}')
"@

$output = python -c $testScript

if ($output -match "SUCCESS") {
    Write-Host "  [OK] CARLA module imports successfully" -ForegroundColor Green
    $versionLine = $output | Select-String "CARLA module"
    if ($versionLine) {
        Write-Host "  $versionLine"
    }
}
else {
    Write-Host "[X] FAILED to import CARLA module" -ForegroundColor Red
    Write-Host "  Output: $output" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# ============================================================================
# SECTION 6: Verify Directory Structure
# ============================================================================

Write-Host "STEP 6: Verifying Directory Structure"
Write-Host "-----------------------------------------------------------------"

$requiredDirs = @(
    "data",
    "data\stream",
    "data\stream\snapshots",
    "src",
    "scripts",
    "PythonAPI",
    "logs"
)

$missingDirs = @()

foreach ($dir in $requiredDirs) {
    $fullPath = Join-Path $repoRoot $dir
    if (Test-Path $fullPath) {
        Write-Host "  [OK] $dir" -ForegroundColor Green
    }
    else {
        Write-Host "  [X] $dir (MISSING - creating)" -ForegroundColor Yellow
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        $missingDirs += $dir
    }
}

if ($missingDirs.Count -gt 0) {
    Write-Host "  Created: $($missingDirs -join ', ')" -ForegroundColor Green
}

Write-Host ""

# ============================================================================
# SECTION 7: Summary & Next Steps
# ============================================================================

Write-Host "STEP 7: Setup Summary"
Write-Host "-----------------------------------------------------------------"
Write-Host ""
Write-Host "[OK] SETUP COMPLETE!" -ForegroundColor Green
Write-Host ""
Write-Host "Summary:"
Write-Host "  * Python virtual environment: $venvPath"
Write-Host "  * CARLA API: Installed (v0.9.16)"
Write-Host "  * CARLA Server: $carlaPath\WindowsNoEditor"
Write-Host "  * Metamodel: $repoRoot\SceneGraphModel\model\sceneGraphModel.ecore"
Write-Host "  * VIATRA Queries: $repoRoot\SceneGraphQueries\src\queries\scenegraph.vql"
Write-Host ""

Write-Host "================================================================="
Write-Host "NEXT STEPS:"
Write-Host "================================================================="
Write-Host ""
Write-Host "1. ACTIVATE VIRTUAL ENVIRONMENT (in each new terminal):"
Write-Host ""
Write-Host "   .\.venv\Scripts\Activate.ps1"
Write-Host ""

Write-Host "2. START CARLA SERVER:"
Write-Host ""
Write-Host "   .\CARLA_0.9.16\CarlaUE4.exe -quality-level=Low -windowed"
Write-Host "   (Server will listen on 127.0.0.1:2000 by default)"
Write-Host ""

Write-Host "3. TEST WITH MOCK MODE (alternative to CARLA server):"
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

Write-Host "================================================================="
Write-Host ""
Write-Host "Questions? See PREREQUISITES.md or contact your instructor."
Write-Host ""
