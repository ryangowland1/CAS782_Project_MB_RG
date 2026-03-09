# Prerequisites & Setup Instructions

Before running the setup script (`SETUP.ps1`), you must complete the prerequisites below. These are **manual, one-time** setup steps required for your system.


## Prerequisites (Do These First)

### 1. Operating System
- **Windows 10 or Windows 11** (64-bit)
- Recommended: 16+ GB RAM, SSD with 50+ GB free space

### 2. Required Software (Add to PATH)

Install and verify these tools in order. After installation, verify each command works in a **new PowerShell terminal**:

#### A. Git
- Download: https://git-scm.com/download/win
- Minimal installation
- **Verify:** Run in PowerShell:
  ```powershell
  git --version
  ```

#### B. Python 3.8 or later
- Download: https://www.python.org/downloads/
- **Important:** Check "Add Python to PATH" during installation
- Recommend: Python 3.10, 3.11, or 3.12 (avoid 3.13; CARLA may not support it yet)
- **Verify:** Run in PowerShell:
  ```powershell
  python --version
  python -m pip --version
  ```

#### C. Visual C++ Build Tools (or Visual Studio 2022)
Required for building Python packages from source.

**Option 1: Standalone Build Tools** (lightweight)
- Download: https://visualstudio.microsoft.com/downloads/
- Search for "Build Tools for Visual Studio 2022"
- Install: Select "Desktop development with C++"

**Option 2: Full Visual Studio 2022** (if you want IDE)
- Download: https://visualstudio.microsoft.com/downloads/
- Install: Select "Desktop development with C++"

**Verify:** 
```powershell
# Should not error
python -c "import setuptools; print('C++ build tools OK')"
```

### 3. Disk Space for CARLA

The SETUP.ps1 script will automatically download and install CARLA 0.9.16.

**Required disk space:**
- Download size: ~8GB
- Extracted size: ~20GB
- Total temporary space needed: ~28GB (during installation)

**Note:** CARLA will be installed to `<repo>\CARLA_0.9.16\` automatically during setup. The download is handled by the setup script and requires a stable internet connection.

### 4. PowerShell Execution Policy

The setup script must run with unrestricted execution. **One-time setup** (requires admin):

```powershell
# Run as Administrator, then execute:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
```

This allows local scripts to run while protecting against remote scripts.

**Verify:**
```powershell
Get-ExecutionPolicy -Scope CurrentUser
# Should output: RemoteSigned
```

---

## Checklist Before Running SETUP.ps1

Before you run the setup script, verify all of these:

- [ ] Windows 10/11 (64-bit)
- [ ] `git --version` works in PowerShell
- [ ] `python --version` works and is 3.12.x (for included CARLA wheel)
- [ ] `pip --version` works
- [ ] C++ Build Tools or Visual Studio 2022 installed
- [ ] PowerShell ExecutionPolicy set to `RemoteSigned` (run as admin)
- [ ] At least 30 GB free disk space (for CARLA installation)
- [ ] Stable internet connection (for CARLA download)

---

## Next Steps

Once all prerequisites are complete:

1. Open PowerShell (no admin needed for setup script)
2. Navigate to repo root:
   ```powershell
   cd <path-to-CAS782_Project_MB_RG>
   ```
3. Run the setup script:
   ```powershell
   .\SETUP.ps1
   ```

The script will:
- Download and install CARLA 0.9.16 (~8GB download, ~20GB extracted)
- Create Python virtual environment (`.venv/`)
- Install CARLA Python API from the included wheel
- Verify directory structure
- Create necessary data directories
- Validate all components

**Note:** The CARLA download may take 10-30 minutes depending on your internet speed.

---

## Troubleshooting Prerequisites

### "Python not found"
- Reinstall Python 3.10+ from https://www.python.org/downloads/
- **Important:** Check "Add Python to PATH" during installation
- Open a **new PowerShell terminal** after installing

### "Permission denied" running SETUP.ps1
- Set ExecutionPolicy as admin (see section 4 above)
- Or run once with: `powershell -ExecutionPolicy Bypass -File SETUP.ps1`

### "Can't build C extensions"
- Install C++ Build Tools: https://visualstudio.microsoft.com/downloads/
- Or install full Visual Studio 2022 with "Desktop development with C++"

### "CARLA download failed"
- Check your internet connection
- Ensure you have at least 30GB free disk space
- The setup script will attempt to download from: https://carla-releases.s3.us-east-005.backblazeb2.com/Windows/CARLA_0.9.16.zip
- If download repeatedly fails, you can manually download and extract to `<repo>\CARLA_0.9.16\`

### Port 2000/2001 blocked
- CARLA uses ports 2000-2001 by default
- Check your firewall: Windows Security → Firewall & Network Protection → Allow app through
- Or configure your router to allow these ports

---

## Additional Resources

- **CARLA Docs:** https://carla.readthedocs.io/
- **VIATRA Docs:** https://wiki.eclipse.org/VIATRA
- **Project Setup Guide:** [`VIATRA_STREAM_GUIDE.md`](VIATRA_STREAM_GUIDE.md)
- **Quick Start:** [`QUICKSTART.md`](QUICKSTART.md)

---

**Questions?** See [`STREAM_REFERENCE.md`](STREAM_REFERENCE.md) or contact your instructor.
