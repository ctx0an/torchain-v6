@echo off
setlocal EnableDelayedExpansion

REM ============================================================================
REM  torchain - Standalone internet recovery for Windows
REM
REM  This script restores normal networking without needing Python, the
REM  torchain package, or any saved state. Run this if torchain (or anything
REM  else) leaves you offline.
REM
REM  Run by double-clicking or from any terminal (it self-elevates).
REM ============================================================================

REM --- Colors ---
for /f "delims=" %%a in ('powershell -NoProfile -Command "[char]27"') do set "ESC=%%a"
if not "%ESC:~1%"=="" set "ESC="
set "CYAN=%ESC%[36m"
set "GREEN=%ESC%[32m"
set "YELLOW=%ESC%[33m"
set "RED=%ESC%[31m"
set "RESET=%ESC%[0m"

REM --- Self-elevate if not Administrator ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo !YELLOW!  [!!] Not running as Administrator - relaunching elevated...!RESET!
    powershell -NoProfile -Command "Start-Process cmd.exe -ArgumentList '/c', ('\"' + '%~f0' + '\"'), '%*' -Verb RunAs"
    exit /b 0
)

echo.
echo %CYAN%  torchain network recovery%RESET%
echo.

REM --- Check for deep reset argument ---
set "DEEP_RESET=0"
if /i "%~1"=="/deep" set "DEEP_RESET=1"
if /i "%~1"=="-deep" set "DEEP_RESET=1"

REM 1. Restore outbound default policy
echo %CYAN%  ==^> Restoring default outbound firewall policy...%RESET%
netsh advfirewall set allprofiles firewallpolicy blockinbound,allowoutbound >nul 2>&1
if %errorlevel% equ 0 (
    echo !GREEN!  [ok] Outbound firewall policy set to Allow!RESET!
) else (
    echo !RED!  [!!] Failed to restore outbound firewall policy!RESET!
)

REM 2. Delete torchain firewall rules
echo %CYAN%  ==^> Deleting torchain firewall rules...%RESET%
netsh advfirewall firewall delete rule name="torchain-allow-tor" >nul 2>&1
netsh advfirewall firewall delete rule name="torchain-allow-loopback" >nul 2>&1
netsh advfirewall firewall delete rule name="torchain-block-ipv6" >nul 2>&1
echo %GREEN%  [ok] Removed torchain firewall rules%RESET%

REM 3. Clear system (WinINET) proxy registry keys
echo %CYAN%  ==^> Disabling system proxy settings in Registry...%RESET%
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v AutoConfigURL /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul 2>&1
echo %GREEN%  [ok] Registry proxy settings cleared%RESET%

REM 4. Delete saved proxy state file
if exist "%ProgramData%\torchain\data\proxy_state.json" (
    del /f /q "%ProgramData%\torchain\data\proxy_state.json" >nul 2>&1
    echo !GREEN!  [ok] Deleted saved proxy state file!RESET!
)

REM 5. Refresh WinINET proxy settings to notify open applications
echo %CYAN%  ==^> Refreshing proxy settings...%RESET%
powershell -NoProfile -Command "$sig = '[DllImport(' + [char]34 + 'wininet.dll' + [char]34 + ')] public static extern bool InternetSetOption(IntPtr hInternet, int dwOption, IntPtr lpBuffer, int dwBufferLength);'; $wininet = Add-Type -MemberDefinition $sig -Name Win32WinInet -Namespace Win32Functions -PassThru; [void]$wininet::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0); [void]$wininet::InternetSetOption([IntPtr]::Zero, 37, [IntPtr]::Zero, 0)" >nul 2>&1
if %errorlevel% equ 0 (
    echo !GREEN!  [ok] Proxy settings refreshed!RESET!
) else (
    echo !YELLOW!  [!!] Proxy refresh notification skipped!RESET!
)

REM 6. Flush DNS & Renew DHCP
echo %CYAN%  ==^> Flushing DNS cache...%RESET%
ipconfig /flushdns >nul 2>&1
echo %GREEN%  [ok] DNS cache flushed%RESET%

echo %CYAN%  ==^> Renewing DHCP lease...%RESET%
ipconfig /renew >nul 2>&1
echo %GREEN%  [ok] DHCP lease renewed%RESET%

REM 7. Deep Reset if requested
if "%DEEP_RESET%"=="1" (
    echo.
    echo !YELLOW!  ==^> Performing deep stack reset (reboot required)...!RESET!
    netsh winsock reset >nul 2>&1
    if !errorlevel! equ 0 (
        echo !GREEN!  [ok] Winsock catalog reset!RESET!
    ) else (
        echo !RED!  [!!] Failed to reset Winsock!RESET!
    )
    
    netsh int ip reset >nul 2>&1
    if !errorlevel! equ 0 (
        echo !GREEN!  [ok] TCP/IP stack reset!RESET!
    ) else (
        echo !RED!  [!!] Failed to reset TCP/IP stack!RESET!
    )
    echo.
    echo !YELLOW!  Deep reset complete. Please REBOOT Windows to finish applying settings.!RESET!
) else (
    echo.
    echo !GREEN!  Recovery complete. If you are still offline, run: internet.bat /deep!RESET!
    echo !YELLOW!  (Note: deep reset requires a reboot afterwards).!RESET!
)
echo.
pause
exit /b 0
