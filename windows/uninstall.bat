@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM  torchain - Windows uninstall (safe, clean removal of all installed files)
REM
REM  This script cleanly removes all traces of torchain from Windows:
REM    1. Stops and deletes the scheduled start-on-boot tasks.
REM    2. Kills running torchain, tor, or python processes.
REM    3. Restores default network/firewall settings (internet fix).
REM    4. Removes system environment variables and PATH entry.
REM    5. Deletes Start Menu and Desktop shortcuts.
REM    6. Deletes the application files in %ProgramData%\torchain.
REM
REM  Run by double-clicking or from any terminal (it self-elevates).
REM ============================================================================

REM --- Configuration ---
set "APPDIR=%ProgramData%\torchain\app"
set "SCRIPTDIR=%~dp0"
if "%SCRIPTDIR:~-1%"=="\" set "SCRIPTDIR=%SCRIPTDIR:~0,-1%"

REM --- Colors ---
for /f "delims=" %%a in ('powershell -NoProfile -Command "[char]27"') do set "ESC=%%a"
if not "%ESC:~1%"=="" set "ESC="
set "CYAN=%ESC%[36m"
set "GREEN=%ESC%[32m"
set "YELLOW=%ESC%[33m"
set "RED=%ESC%[31m"
set "MAGENTA=%ESC%[35m"
set "RESET=%ESC%[0m"

echo.
echo %MAGENTA%  torchain Windows uninstaller%RESET%
echo.

REM --- Check if we are running from the install directory ---
REM If we are, we must copy ourselves to temp first and run from there,
REM otherwise we cannot delete the app directory because of file locks.
set "CURRENT_DIR=%~dp0"
set "TEST_PATH=%ProgramData%\torchain"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"
if "%TEST_PATH:~-1%"=="\" set "TEST_PATH=%TEST_PATH:~0,-1%"

set "RUNNING_FROM_APP=0"
echo !CURRENT_DIR! | findstr /i /c:"!TEST_PATH!" >nul && set "RUNNING_FROM_APP=1"

if "!RUNNING_FROM_APP!"=="1" if not "%~1"=="/fromtemp" (
    echo !CYAN!  ==^> Running from installation folder. Copying to temp...!RESET!
    copy /Y "%~f0" "%TEMP%\torchain_uninstall.bat" >nul 2>&1
    start "" "%TEMP%\torchain_uninstall.bat" /fromtemp
    exit /b 0
)

REM --- Self-elevate if not Administrator ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo !YELLOW!  [!!] Not running as Administrator - relaunching elevated...!RESET!
    powershell -NoProfile -Command "Start-Process cmd.exe -ArgumentList '/c', ('\"' + '%~f0' + '\"'), '%*' -Verb RunAs"
    exit /b 0
)

REM --- Wait for caller process to exit and release file locks ---
if "%~1"=="/fromtemp" (
    echo !CYAN!  ==^> Waiting for active processes to release locks...!RESET!
    timeout /t 2 >nul 2>&1
)

REM =========================================================================
REM  Step 1: Disable and remove scheduled tasks
REM =========================================================================
echo %CYAN%  ==^> Removing scheduled tasks...%RESET%
schtasks /End /TN "torchain" >nul 2>&1
schtasks /Delete /TN "torchain" /F >nul 2>&1
schtasks /End /TN "torchain-watchdog" >nul 2>&1
schtasks /Delete /TN "torchain-watchdog" /F >nul 2>&1
echo %GREEN%  [ok] Scheduled tasks removed%RESET%

REM =========================================================================
REM  Step 2: Terminate active torchain processes
REM =========================================================================
echo %CYAN%  ==^> Terminating active torchain processes...%RESET%
powershell -NoProfile -Command "Get-Process | Where-Object { $_.Path -like '*\torchain\app\*' } | Stop-Process -Force -ErrorAction SilentlyContinue" >nul 2>&1
echo %GREEN%  [ok] Active processes terminated%RESET%

REM =========================================================================
REM  Step 3: Restore default network & firewall settings (Internet Fix)
REM =========================================================================
echo %CYAN%  ==^> Restoring default outbound firewall policy...%RESET%
netsh advfirewall set allprofiles firewallpolicy blockinbound,allowoutbound >nul 2>&1
if %errorlevel% equ 0 (
    echo !GREEN!  [ok] Outbound firewall policy set to Allow!RESET!
) else (
    echo !RED!  [!!] Failed to restore outbound firewall policy!RESET!
)

echo %CYAN%  ==^> Deleting torchain firewall rules...%RESET%
netsh advfirewall firewall delete rule name="torchain-allow-tor" >nul 2>&1
netsh advfirewall firewall delete rule name="torchain-allow-loopback" >nul 2>&1
netsh advfirewall firewall delete rule name="torchain-block-ipv6" >nul 2>&1
echo %GREEN%  [ok] Removed torchain firewall rules%RESET%

echo %CYAN%  ==^> Disabling system proxy settings in Registry...%RESET%
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v AutoConfigURL /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul 2>&1
echo %GREEN%  [ok] Registry proxy settings cleared%RESET%

echo %CYAN%  ==^> Refreshing proxy settings...%RESET%
powershell -NoProfile -Command "$sig = '[DllImport(' + [char]34 + 'wininet.dll' + [char]34 + ')] public static extern bool InternetSetOption(IntPtr hInternet, int dwOption, IntPtr lpBuffer, int dwBufferLength);'; $wininet = Add-Type -MemberDefinition $sig -Name Win32WinInet -Namespace Win32Functions -PassThru; [void]$wininet::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0); [void]$wininet::InternetSetOption([IntPtr]::Zero, 37, [IntPtr]::Zero, 0)" >nul 2>&1
if %errorlevel% equ 0 (
    echo !GREEN!  [ok] Proxy settings refreshed!RESET!
) else (
    echo !YELLOW!  [!!] Proxy refresh notification skipped!RESET!
)

echo %CYAN%  ==^> Flushing DNS cache...%RESET%
ipconfig /flushdns >nul 2>&1
echo %GREEN%  [ok] DNS cache flushed%RESET%

echo %CYAN%  ==^> Renewing DHCP lease...%RESET%
ipconfig /renew >nul 2>&1
echo %GREEN%  [ok] DHCP lease renewed%RESET%

REM =========================================================================
REM  Step 4: Remove shortcuts
REM =========================================================================
echo %CYAN%  ==^> Removing shortcuts...%RESET%
set "STARTMENU=%ProgramData%\Microsoft\Windows\Start Menu\Programs\Torchain"
if exist "%STARTMENU%" rmdir /s /q "%STARTMENU%" >nul 2>&1
if exist "%PUBLIC%\Desktop\Torchain.lnk" del /f /q "%PUBLIC%\Desktop\Torchain.lnk" >nul 2>&1
echo %GREEN%  [ok] Shortcuts removed%RESET%

REM =========================================================================
REM  Step 5: Clean up environment variables and system PATH
REM =========================================================================
echo %CYAN%  ==^> Cleaning up environment variables and system PATH...%RESET%
powershell -NoProfile -Command "[Environment]::SetEnvironmentVariable('TORCHAIN_PYTHON', $null, 'Machine'); [Environment]::SetEnvironmentVariable('TORCHAIN_TOR', $null, 'Machine');" >nul 2>&1

powershell -NoProfile -Command "$target = '%ProgramData%\torchain\app'; $current = [Environment]::GetEnvironmentVariable('Path', 'Machine'); $entries = $current -split ';' | Where-Object { $_.TrimEnd('\') -ne $target.TrimEnd('\') }; $newPath = $entries -join ';'; [Environment]::SetEnvironmentVariable('Path', $newPath, 'Machine'); $sig = '[DllImport(' + [char]34 + 'user32.dll' + [char]34 + ', SetLastError=true, CharSet=CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);'; Add-Type -Namespace Win32 -Name NativeMethods -MemberDefinition $sig; $r = [UIntPtr]::Zero; [Win32.NativeMethods]::SendMessageTimeout([IntPtr]0xFFFF, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$r) | Out-Null" >nul 2>&1
echo %GREEN%  [ok] Environment variables and PATH cleaned%RESET%

REM =========================================================================
REM  Step 6: Delete installation files
REM =========================================================================
echo %CYAN%  ==^> Deleting Torchain installation files...%RESET%
if exist "%ProgramData%\torchain" (
    rmdir /s /q "%ProgramData%\torchain" >nul 2>&1
    if exist "%ProgramData%\torchain" (
        echo !YELLOW!  [!!] Some files could not be deleted immediately. They will be removed on reboot.!RESET!
    ) else (
        echo !GREEN!  [ok] All Torchain files removed!RESET!
    )
)

echo.
echo %GREEN%  Torchain has been successfully uninstalled!%RESET%
echo.

if "%~1"=="/fromtemp" (
    echo   This temporary uninstaller script will self-delete.
    start /b "" cmd /c timeout /t 1 ^>nul ^& del /f /q "%~f0"
)
pause
exit /b 0
