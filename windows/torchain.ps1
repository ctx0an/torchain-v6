<#
  torchain launcher (PowerShell) - locates Python, self-elevates, runs tcwin.
  Used both interactively and by the start-on-boot scheduled task.

  Usage:
      .\torchain.ps1 gui
      .\torchain.ps1 start
      .\torchain.ps1 repair --deep
#>
[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments = $true)] [string[]]$Args)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-Python {
    $bundled = Join-Path $AppDir "python\python.exe"
    if (Test-Path $bundled) { return $bundled }
    if ($env:TORCHAIN_PYTHON -and (Test-Path $env:TORCHAIN_PYTHON)) { return $env:TORCHAIN_PYTHON }
    foreach ($c in @("py", "python")) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$py = Resolve-Python
if (-not $py) {
    Write-Host "Python not found. Run windows\setup.bat first." -ForegroundColor Red
    exit 69
}

if (-not (Test-Admin)) {
    Write-Host "Administrator rights required - relaunching elevated..." -ForegroundColor Yellow
    $escapedArgs = $Args | ForEach-Object {
        $escaped = $_ -replace '"', '\"'
        if ($escaped -match '[\s"]') {
            '"' + $escaped + '"'
        } else {
            $escaped
        }
    }
    $inner = "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
    if ($escapedArgs) {
        $inner += " " + ($escapedArgs -join " ")
    }
    Start-Process powershell -Verb RunAs -ArgumentList $inner | Out-Null
    exit 0
}

Push-Location $AppDir
try {
    & $py -m tcwin @Args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
