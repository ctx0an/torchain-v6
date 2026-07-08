<#
  torchain - STANDALONE internet recovery for Windows.

  This is the safety net the rest of torchain leans on: it restores normal
  networking WITHOUT needing Python, the torchain package, or any saved state.
  Use it if torchain (or anything else) ever leaves you offline.

  SAFETY: by default it only performs reversible, connectivity-restoring steps
  (firewall policy back to allow-outbound, delete torchain rules, clear the
  WinINET proxy, flush DNS, renew DHCP). The aggressive stack reset (Winsock /
  TCP-IP, which needs a reboot and can disturb other VPN/proxy software) is
  OPT-IN via -Deep only.

  Usage (from any PowerShell - it self-elevates):
      .\internet.ps1            # safe repair
      .\internet.ps1 -Deep      # safe repair + stack reset (reboot after)
#>
[CmdletBinding()]
param([switch]$Deep)

$ErrorActionPreference = "Continue"

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "Relaunching internet recovery as Administrator..." -ForegroundColor Yellow
    $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($Deep) { $argList += " -Deep" }
    Start-Process powershell -Verb RunAs -ArgumentList $argList | Out-Null
    return
}

function Step($label, [scriptblock]$action) {
    try { & $action; Write-Host "  [ok] $label" -ForegroundColor Green }
    catch { Write-Host "  [!!] $label ($_)" -ForegroundColor Yellow }
}

Write-Host "torchain network recovery" -ForegroundColor Cyan

# 1. Restore the permissive default firewall policy FIRST (gets you online even
#    if every later step fails).
Step "restore default outbound firewall policy" {
    netsh advfirewall set allprofiles firewallpolicy blockinbound,allowoutbound | Out-Null
}

# 2. Delete every torchain firewall rule.
foreach ($r in @("torchain-allow-tor","torchain-allow-loopback","torchain-block-ipv6")) {
    netsh advfirewall firewall delete rule name=$r 2>$null | Out-Null
}
Write-Host "  [ok] removed torchain firewall rules" -ForegroundColor Green

# 3. Clear the per-user WinINET proxy (registry).
Step "clear system (WinINET) proxy" {
    $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    Set-ItemProperty -Path $key -Name ProxyEnable -Value 0 -Type DWord -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path $key -Name ProxyServer  -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path $key -Name AutoConfigURL -ErrorAction SilentlyContinue
}

# 4. Flush DNS + renew DHCP.
Step "flush DNS cache" { ipconfig /flushdns | Out-Null }
Step "renew DHCP lease" { ipconfig /renew   | Out-Null }

if ($Deep) {
    Write-Host "Deep stack reset (a reboot is required afterwards):" -ForegroundColor Yellow
    Step "reset Winsock catalog" { netsh winsock reset | Out-Null }
    Step "reset TCP/IP stack"    { netsh int ip reset  | Out-Null }
    Write-Host "Deep reset done. REBOOT Windows to finish applying it." -ForegroundColor Yellow
} else {
    Write-Host "Done. If still offline, run: .\internet.ps1 -Deep (then reboot)." -ForegroundColor Green
}
