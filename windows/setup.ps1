<#
  torchain - Windows 11 installer / dependency bootstrapper.

  Installs the two dependencies torchain needs:
    1. Python 3 (for torchain itself)
    2. tor.exe   (the Tor daemon - reused from the Tor Expert Bundle / Browser)

  PACKAGE-MANAGER STRATEGY (the key design point):
    * Prefer winget (built into Windows 11).
    * If winget is missing (LTSC, stripped images, older builds), fall back to
      Chocolatey if it is installed.
    * If neither package manager exists, fall back to a direct HTTPS download
      from the official python.org and Tor Project servers - so torchain can
      always be installed with no package manager at all.

  This script ONLY installs dependencies and copies torchain into place. It
  never changes firewall / proxy / network settings, so running it can't break
  your connectivity.

  Run from an elevated PowerShell:
      Set-ExecutionPolicy -Scope Process Bypass -Force
      .\windows\setup.ps1
#>
[CmdletBinding()]
param(
    [string]$TorVersion = "13.5.6",            # Tor Expert Bundle version for the direct-download fallback
    [switch]$SkipPython,
    [switch]$SkipTor
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Write-Warn2($m){ Write-Host "  [!!] $m" -ForegroundColor Yellow }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Warn2 "Not running as Administrator - relaunching elevated..."
    Start-Process powershell -Verb RunAs -ArgumentList (
        "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" " +
        "-TorVersion $TorVersion") | Out-Null
    return
}

function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function Install-WithWinget($id) {
    if (-not (Have winget)) { return $false }
    Write-Step "winget install $id"
    try {
        winget install --id $id -e --accept-source-agreements --accept-package-agreements --silent
        return $true
    } catch { Write-Warn2 "winget failed for ${id}: $_"; return $false }
}

function Install-WithChoco($pkg) {
    if (-not (Have choco)) { return $false }
    Write-Step "choco install $pkg"
    try { choco install $pkg -y; return $true }
    catch { Write-Warn2 "choco failed for ${pkg}: $_"; return $false }
}

$ProgramData = $env:ProgramData
$AppDir = Join-Path $ProgramData "torchain\app"
$TorDir = Join-Path $AppDir "tor"
$PyDir  = Join-Path $AppDir "python"   # self-contained Python lives next to torchain

# --------------------------------------------------------------------------
# 1. Python
# --------------------------------------------------------------------------
function Install-EmbeddedPython {
    # No package manager available: drop a small, self-contained Python right
    # next to torchain (in $PyDir) and keep its packages in the SAME dir. This
    # is the python.org "embeddable" build - a few MB, no system-wide install,
    # nothing added to PATH, fully removable by deleting the folder.
    Write-Warn2 "No package manager - installing a lightweight, self-contained Python into $PyDir"
    $ver = "3.12.4"
    $zipName = "python-$ver-embed-amd64.zip"
    $url = "https://www.python.org/ftp/python/$ver/$zipName"
    $tmp = Join-Path $env:TEMP $zipName
    Write-Step "GET $url"
    Invoke-WebRequest -Uri $url -OutFile $tmp
    New-Item -ItemType Directory -Force -Path $PyDir | Out-Null
    Write-Step "Extracting embeddable Python to $PyDir"
    Expand-Archive -Path $tmp -DestinationPath $PyDir -Force
    Remove-Item $tmp -ErrorAction SilentlyContinue

    # The embeddable build ships locked down. Enable 'import site' and add both
    # Lib\site-packages (for pip packages) and '..' (so 'import tcwin' resolves
    # from the app dir). Paths in ._pth are relative to python.exe.
    $pth = Get-ChildItem -Path $PyDir -Filter "python*._pth" | Select-Object -First 1
    if ($pth) {
        $lines = Get-Content $pth.FullName
        $lines = $lines -replace '^#\s*import site', 'import site'
        if ($lines -notcontains 'Lib\site-packages') { $lines += 'Lib\site-packages' }
        if ($lines -notcontains '..')                { $lines += '..' }
        Set-Content -Path $pth.FullName -Value $lines -Encoding ASCII
    }

    $py = Join-Path $PyDir "python.exe"

    # Bootstrap pip INTO this same dir.
    try {
        $getpip = Join-Path $env:TEMP "get-pip.py"
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip
        & $py $getpip --no-warn-script-location | Out-Null
        Remove-Item $getpip -ErrorAction SilentlyContinue
        Write-Ok "pip ready inside $PyDir"
    } catch { Write-Warn2 "pip bootstrap failed (torchain core is pure stdlib, so this is usually fine): $_" }

    # Install any required packages into the SAME dir. torchain's core has no
    # third-party deps, so requirements.txt is normally empty / absent.
    $repoRoot = Split-Path $PSScriptRoot -Parent
    $req = Join-Path $repoRoot "windows\requirements.txt"
    if (Test-Path $req) {
        try { & $py -m pip install -r $req --no-warn-script-location | Out-Null; Write-Ok "required packages installed into $PyDir" }
        catch { Write-Warn2 "pip install of requirements failed: $_" }
    }

    if (Test-Path $py) {
        [Environment]::SetEnvironmentVariable("TORCHAIN_PYTHON", $py, "Machine")
        Write-Ok "Lightweight Python ready: $py"
        Write-Warn2 "Note: the embeddable Python has no Tcl/Tk, so the 'gui' command needs a full python.org install. The CLI and kill-switch work fully on it."
        return $py
    }
    Write-Warn2 "Embeddable Python setup failed; install Python manually from python.org"
    return $null
}

function Ensure-Python {
    if ((Have python) -or (Have py)) { Write-Ok "Python already present"; return }
    Write-Step "Installing Python 3"
    if (Install-WithWinget "Python.Python.3.12") { Write-Ok "Python via winget"; return }
    if (Install-WithChoco  "python")            { Write-Ok "Python via choco";  return }
    # Last resort, no package manager: self-contained Python in the app dir.
    Install-EmbeddedPython | Out-Null
}

# --------------------------------------------------------------------------
# 2. tor.exe
# --------------------------------------------------------------------------
function Find-Tor {
    # PATH
    $p = Get-Command tor -ErrorAction SilentlyContinue
    if ($p) { return $p.Source }
    # torchain bundled
    $b = Join-Path $TorDir "tor.exe"
    if (Test-Path $b) { return $b }
    # Tor Browser common roots
    $roots = @(
        "$env:LOCALAPPDATA\Tor Browser",
        "$env:USERPROFILE\Desktop\Tor Browser",
        "$env:PROGRAMFILES\Tor Browser",
        "${env:PROGRAMFILES(X86)}\Tor Browser"
    )
    foreach ($r in $roots) {
        $cand = Join-Path $r "Browser\TorBrowser\Tor\tor.exe"
        if (Test-Path $cand) { return $cand }
    }
    return $null
}

function Download-TorExpertBundle {
    Write-Warn2 "No package manager - downloading the Tor Expert Bundle directly"
    $arch = "x86_64"
    $name = "tor-expert-bundle-windows-$arch-$TorVersion.tar.gz"
    $url  = "https://dist.torproject.org/torbrowser/$TorVersion/$name"
    $tmp  = Join-Path $env:TEMP $name
    Write-Step "GET $url"
    Invoke-WebRequest -Uri $url -OutFile $tmp
    New-Item -ItemType Directory -Force -Path $TorDir | Out-Null
    Write-Step "Extracting to $TorDir"
    # tar ships with Windows 10/11.
    tar -xzf $tmp -C $TorDir
    Remove-Item $tmp -ErrorAction SilentlyContinue
    # The bundle lays out tor\tor.exe (and pluggable_transports\). find_tor()
    # checks both <app>\tor\tor.exe and <app>\tor\Tor\tor.exe.
    if (Test-Path (Join-Path $TorDir "tor\tor.exe")) {
        return (Join-Path $TorDir "tor\tor.exe")
    }
    if (Test-Path (Join-Path $TorDir "tor.exe")) {
        return (Join-Path $TorDir "tor.exe")
    }
    return $null
}

function Ensure-Tor {
    $existing = Find-Tor
    if ($existing) { Write-Ok "tor.exe found: $existing"; return }
    Write-Step "Installing Tor"
    if (Install-WithWinget "TorProject.TorBrowser") {
        $t = Find-Tor; if ($t) { Write-Ok "Tor via winget: $t"; return }
    }
    if (Install-WithChoco "tor-browser") {
        $t = Find-Tor; if ($t) { Write-Ok "Tor via choco: $t"; return }
    }
    try {
        $t = Download-TorExpertBundle
        if ($t) {
            Write-Ok "Tor (Expert Bundle) installed: $t"
            [Environment]::SetEnvironmentVariable("TORCHAIN_TOR", $t, "Machine")
            Write-Ok "Set machine env TORCHAIN_TOR=$t"
            return
        }
    } catch { Write-Warn2 "Direct Tor download failed: $_" }
    Write-Warn2 "Could not install Tor automatically."
    Write-Warn2 "Manual option: install Tor Browser from https://www.torproject.org/download/"
    Write-Warn2 "or set TORCHAIN_TOR to a tor.exe path, then re-run 'torchain doctor'."
}

# --------------------------------------------------------------------------
# 3. Copy torchain (the tcwin package) into the app dir
# --------------------------------------------------------------------------
function Install-Torchain {
    Write-Step "Installing torchain into $AppDir"
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    $repoRoot = Split-Path $PSScriptRoot -Parent
    $src = Join-Path $repoRoot "tcwin"
    if (-not (Test-Path $src)) { throw "tcwin package not found next to this script ($src)" }
    Copy-Item $src -Destination $AppDir -Recurse -Force
    Copy-Item (Join-Path $PSScriptRoot "torchain.ps1") -Destination $AppDir -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $PSScriptRoot "torchain.cmd") -Destination $AppDir -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $PSScriptRoot "internet.ps1") -Destination $AppDir -Force -ErrorAction SilentlyContinue
    Write-Ok "torchain copied. Launch with: $AppDir\torchain.cmd gui"
}

Write-Host "torchain Windows setup" -ForegroundColor Magenta
if (-not $SkipPython) { Ensure-Python }
if (-not $SkipTor)    { Ensure-Tor }
Install-Torchain

Write-Host ""
Write-Step "Verifying"
try {
    Push-Location $AppDir
    & cmd /c "torchain.cmd doctor"
} catch { Write-Warn2 "doctor check could not run automatically: $_" }
finally { Pop-Location }

Write-Host ""
Write-Ok "Setup complete. Open an elevated shell and run 'torchain gui'."
Write-Host "If you ever lose internet, run:  $AppDir\internet.ps1" -ForegroundColor Yellow
