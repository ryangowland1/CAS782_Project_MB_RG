#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Complete demo script for CARLA + VIATRA scene graph pipeline

.DESCRIPTION
    This script walks through:
    1. Testing scene graph generation in mock mode
    2. Starting CARLA server (if not running)
    3. Connecting to live CARLA and generating scene graphs
    4. Instructions for importing into VIATRA/Eclipse

.PARAMETER SkipMock
    Skip the mock mode demo

.PARAMETER CarlaOnly
    Only test CARLA connection, skip VIATRA instructions

.EXAMPLE
    .\scripts\demo_carla_viatra.ps1
    Run full demo with all steps

.EXAMPLE
    .\scripts\demo_carla_viatra.ps1 -SkipMock
    Skip mock mode and go straight to CARLA
#>

param(
    [switch]$SkipMock,
    [switch]$CarlaOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "`n╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  CARLA + VIATRA Scene Graph Demo                          ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝`n" -ForegroundColor Cyan

# ============================================================================
# STEP 1: Mock Mode Test
# ============================================================================
if (-not $SkipMock) {
    Write-Host "[Step 1/5] Testing Mock Scene Graph Generation" -ForegroundColor Yellow
    Write-Host "─────────────────────────────────────────────────────────────`n" -ForegroundColor DarkGray
    
    $mockOutput = Join-Path $repoRoot "data" "scene_mock_demo.xmi"
    
    Push-Location $repoRoot
    try {
        $pythonExe = Join-Path $repoRoot ".venv" "Scripts" "python.exe"
        & $pythonExe .\src\carla_scenegraph_export.py --mock --output $mockOutput
        
        if (Test-Path $mockOutput) {
            Write-Host "`n✓ Mock scene graph created successfully!" -ForegroundColor Green
            Write-Host "  Location: $mockOutput" -ForegroundColor Cyan
            Write-Host "`n  Preview:" -ForegroundColor Gray
            Get-Content $mockOutput | Select-Object -First 15 | ForEach-Object {
                Write-Host "    $_" -ForegroundColor DarkGray
            }
        }
    }
    finally {
        Pop-Location
    }
    
    Write-Host "`nPress Enter to continue..." -ForegroundColor Yellow
    Read-Host
}

# ============================================================================
# STEP 2: Check CARLA Server Status
# ============================================================================
Write-Host "`n[Step 2/5] Checking CARLA Server Status" -ForegroundColor Yellow
Write-Host "─────────────────────────────────────────────────────────────`n" -ForegroundColor DarkGray

$carlaRunning = $false
try {
    $pythonExe = Join-Path $repoRoot ".venv" "Scripts" "python.exe"
    $testScriptFile = Join-Path $repoRoot "data" "test_carla_connection.py"
    
    # Create test script file
    $testScriptContent = @'
import carla
import sys
try:
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(2.0)
    world = client.get_world()
    print('Connected to CARLA world: ' + world.get_map().name)
    sys.exit(0)
except Exception as e:
    print('Cannot connect to CARLA: ' + str(e))
    sys.exit(1)
'@
    Set-Content -Path $testScriptFile -Value $testScriptContent
    
    $result = & $pythonExe $testScriptFile 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ CARLA server is running!" -ForegroundColor Green
        Write-Host "  $result" -ForegroundColor Cyan
        $carlaRunning = $true
    }
    else {
        Write-Host "✗ CARLA server is not running" -ForegroundColor Red
        Write-Host "  $result" -ForegroundColor DarkGray
    }
}
catch {
    Write-Host "✗ Could not connect to CARLA" -ForegroundColor Red
}

# ============================================================================
# STEP 3: Start CARLA Server (if needed)
# ============================================================================
if (-not $carlaRunning) {
    Write-Host "`n[Step 3/5] Starting CARLA Server" -ForegroundColor Yellow
    Write-Host "─────────────────────────────────────────────────────────────`n" -ForegroundColor DarkGray
    
    Write-Host "To start CARLA server, open a new terminal and run ONE of:" -ForegroundColor Cyan
    Write-Host "`n  Option 1 - Using helper script:" -ForegroundColor White
    Write-Host "    pwsh .\scripts\start_carla_server.ps1" -ForegroundColor Green
    
    Write-Host "`n  Option 2 - Direct make command:" -ForegroundColor White
    Write-Host "    cd C:\carla-src\carla" -ForegroundColor Green
    Write-Host "    make launch" -ForegroundColor Green
    
    Write-Host "`n  Option 3 - Using Unreal Editor (if built):" -ForegroundColor White
    Write-Host "    cd C:\carla-src\carla" -ForegroundColor Green
    Write-Host "    Unreal\CarlaUE4\Binaries\Win64\CarlaUE4-Win64-Shipping.exe" -ForegroundColor Green
    
    Write-Host "`n  The CARLA window will open. Wait for it to fully load." -ForegroundColor Yellow
    Write-Host "  You should see the main menu or the simulation view.`n" -ForegroundColor Yellow
    
    Write-Host "Press Enter once CARLA server is running..." -ForegroundColor Yellow
    Read-Host
    
    # Re-check connection
    Write-Host "Checking connection again..." -ForegroundColor Cyan
    $result = & $pythonExe $testScriptFile 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ CARLA server is now running!" -ForegroundColor Green
        $carlaRunning = $true
    }
    else {
        Write-Host "✗ Still cannot connect. Check CARLA server output for errors." -ForegroundColor Red
        Write-Host "  Continuing with demo anyway..." -ForegroundColor Yellow
    }
}

# ============================================================================
# STEP 4: Generate Scene Graph from Live CARLA
# ============================================================================
if ($carlaRunning) {
    Write-Host "`n[Step 4/5] Generating Scene Graph from Live CARLA" -ForegroundColor Yellow
    Write-Host "─────────────────────────────────────────────────────────────`n" -ForegroundColor DarkGray
    
    $liveOutput = Join-Path $repoRoot "data" "scene_live_demo.xmi"
    
    Push-Location $repoRoot
    try {
        Write-Host "Connecting to CARLA and exporting scene graph..." -ForegroundColor Cyan
        $pythonExe = Join-Path $repoRoot ".venv" "Scripts" "python.exe"
        & $pythonExe .\src\carla_scenegraph_export.py --output $liveOutput
        
        if (Test-Path $liveOutput) {
            Write-Host "`n✓ Live scene graph created!" -ForegroundColor Green
            Write-Host "  Location: $liveOutput" -ForegroundColor Cyan
            
            $fileInfo = Get-Item $liveOutput
            Write-Host "  Size: $($fileInfo.Length) bytes" -ForegroundColor Cyan
            Write-Host "  Modified: $($fileInfo.LastWriteTime)" -ForegroundColor Cyan
        }
    }
    catch {
        Write-Host "✗ Failed to generate live scene graph: $_" -ForegroundColor Red
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "`n[Step 4/5] Skipping live CARLA export (server not running)" -ForegroundColor Yellow
}

# ============================================================================
# STEP 5: VIATRA Setup Instructions
# ============================================================================
if (-not $CarlaOnly) {
    Write-Host "`n[Step 5/5] VIATRA Setup & Query Execution" -ForegroundColor Yellow
    Write-Host "─────────────────────────────────────────────────────────────`n" -ForegroundColor DarkGray
    
    Write-Host "To analyze the scene graphs with VIATRA:" -ForegroundColor Cyan
    
    Write-Host "`n  1. Install Eclipse with VIATRA:" -ForegroundColor White
    Write-Host "     - Download Eclipse Modeling Tools from eclipse.org" -ForegroundColor Gray
    Write-Host "     - Help > Install New Software" -ForegroundColor Gray
    Write-Host "     - Add: http://download.eclipse.org/viatra/updates/release/latest" -ForegroundColor Gray
    Write-Host "     - Install 'VIATRA Query and Transformation SDK'" -ForegroundColor Gray
    
    Write-Host "`n  2. Import the metamodel:" -ForegroundColor White
    Write-Host "     - File > New > Project > Empty EMF Project" -ForegroundColor Gray
    Write-Host "     - Import model\SceneGraph.ecore" -ForegroundColor Green
    Write-Host "     - Right-click .ecore > Register EPackages" -ForegroundColor Gray
    
    Write-Host "`n  3. Import a scene graph instance:" -ForegroundColor White
    $mockPath = Join-Path $repoRoot "data" "scene_mock_demo.xmi"
    Write-Host "     - File > Import > General > File System" -ForegroundColor Gray
    Write-Host "     - Select: $mockPath" -ForegroundColor Green
    
    Write-Host "`n  4. Create VIATRA queries:" -ForegroundColor White
    Write-Host "     - File > New > VIATRA Query Project" -ForegroundColor Gray
    Write-Host "     - Import queries\scenegraph.vql" -ForegroundColor Green
    Write-Host "     - Available patterns:" -ForegroundColor Gray
    Write-Host "       • fastVehicle - finds vehicles moving > 50 km/h" -ForegroundColor Cyan
    Write-Host "       • connected - generic connectivity pattern" -ForegroundColor Cyan
    Write-Host "       • vehiclePedestrianSharedRoad - potential conflict detection" -ForegroundColor Cyan
    
    Write-Host "`n  5. Run queries on the scene:" -ForegroundColor White
    Write-Host "     - Right-click XMI file > VIATRA > Load model to Query Explorer" -ForegroundColor Gray
    Write-Host "     - Open Query Explorer view" -ForegroundColor Gray
    Write-Host "     - Select patterns to execute" -ForegroundColor Gray
    Write-Host "     - View matches in the Results view" -ForegroundColor Gray
    
    Write-Host "`n  6. Real-time streaming (advanced):" -ForegroundColor White
    Write-Host "     - Run: pwsh .\scripts\run_scenegraph_stream.ps1" -ForegroundColor Green
    Write-Host "     - Open: data\stream\live_view.html" -ForegroundColor Green
    Write-Host "     - Configure VIATRA incremental query engine for streaming updates" -ForegroundColor Gray
}

# ============================================================================
# Summary
# ============================================================================
Write-Host "`n╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║  Demo Complete!                                            ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝`n" -ForegroundColor Green

Write-Host "Generated Files:" -ForegroundColor Cyan
Get-ChildItem (Join-Path $repoRoot "data") -Filter "scene_*_demo.xmi" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  • $($_.Name) - $([math]::Round($_.Length/1KB, 2)) KB" -ForegroundColor White
}

Write-Host "`nNext Steps:" -ForegroundColor Cyan
Write-Host "  • Import XMI files into Eclipse/VIATRA" -ForegroundColor White
Write-Host "  • Run VIATRA queries on scene graphs" -ForegroundColor White
Write-Host "  • Start streaming: .\scripts\run_scenegraph_stream.ps1 -Mock" -ForegroundColor White
Write-Host "  • View live updates: .\scripts\open_live_view.ps1" -ForegroundColor White

Write-Host "`nDocumentation:" -ForegroundColor Cyan
Write-Host "  • docs\windows_setup_carla_viatra.md" -ForegroundColor White
Write-Host "  • docs\architecture.md" -ForegroundColor White
Write-Host "  • docs\viatra_stream_integration.md`n" -ForegroundColor White
