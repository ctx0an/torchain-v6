@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM  torchain - Windows setup (zero package-manager dependencies)
REM
REM  This script installs everything torchain needs:
REM    1. Python 3 (full install with Tcl/Tk for GUI support)
REM    2. tor.exe  (extracted from the bundled Tor.zip in this directory)
REM
REM  No winget, no chocolatey, no scoop - just direct HTTPS downloads and the
REM  zip file already shipped with torchain.
REM
REM  Run by double-clicking or from any terminal (it self-elevates).
REM ============================================================================

REM --- Configuration ---
set "PY_VERSION=3.12.4"
set "PY_INSTALLER=python-%PY_VERSION%-amd64.exe"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/%PY_INSTALLER%"

set "APPDIR=%ProgramData%\torchain\app"
set "PYDIR=%APPDIR%\python"
set "TORDIR=%APPDIR%\tor"
set "SCRIPTDIR=%~dp0"
REM Remove trailing backslash from SCRIPTDIR for clean path joins
if "%SCRIPTDIR:~-1%"=="\" set "SCRIPTDIR=%SCRIPTDIR:~0,-1%"
set "REPOROOT=%SCRIPTDIR%\.."

REM --- Colors ---
for /f "delims=" %%a in ('powershell -NoProfile -Command "[char]27"') do set "ESC=%%a"
if not "%ESC:~1%"=="" set "ESC="
set "CYAN=%ESC%[36m"
set "GREEN=%ESC%[32m"
set "YELLOW=%ESC%[33m"
set "RED=%ESC%[31m"
set "MAGENTA=%ESC%[35m"
set "RESET=%ESC%[0m"

REM --- Self-elevate if not Administrator ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo !YELLOW!  [!!] Not running as Administrator - relaunching elevated...!RESET!
    powershell -NoProfile -Command "Start-Process cmd.exe -ArgumentList '/c', ('\"' + '%~f0' + '\"'), '%*' -Verb RunAs"
    exit /b 0
)

echo.
echo %MAGENTA%  torchain Windows setup (no package manager required)%RESET%
echo.

REM =========================================================================
REM  Step 0: Install Microsoft Visual C++ Redistributable dependency
REM =========================================================================
if not exist "%SystemRoot%\System32\vcruntime140.dll" (
    echo %CYAN%  ==^> Downloading and installing Visual C++ Redistributable dependency...%RESET%
    
    REM Kill any stuck installer service to release the lock
    taskkill /f /im msiexec.exe >nul 2>&1
    
    set "VC_REDIST=%TEMP%\vc_redist.x64.exe"
    if exist "!VC_REDIST!" del "!VC_REDIST!" >nul 2>&1
    
    powershell -NoProfile -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $env:VC_REDIST"
    
    if exist "!VC_REDIST!" (
        echo %CYAN%  ==^> Installing Visual C++ Redistributable...%RESET%
        "!VC_REDIST!" /install /quiet /norestart
        del "!VC_REDIST!" >nul 2>&1
        
        if exist "%SystemRoot%\System32\vcruntime140.dll" (
            echo !GREEN!  [ok] Visual C++ Redistributable installed successfully!RESET!
        ) else (
            echo !YELLOW!  [!!] Silent VC++ Redistributable installation failed. Trying passive mode...!RESET!
            powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $env:VC_REDIST"
            if exist "!VC_REDIST!" (
                "!VC_REDIST!" /install /passive /norestart
                del "!VC_REDIST!" >nul 2>&1
            )
        )
    ) else (
        echo !RED!  [!!] Failed to download Visual C++ Redistributable. Python might fail to run.!RESET!
    )
) else (
    echo !GREEN!  [ok] Visual C++ Redistributable already installed!RESET!
)
echo.


REM =========================================================================
REM  Step 1: Install Python (full, with tkinter/GUI support)
REM =========================================================================
if exist "%PYDIR%\python.exe" (
    echo !GREEN!  [ok] Python already installed: %PYDIR%\python.exe!RESET!
    goto :skip_python
)
if exist "%PYDIR%\bin\python.exe" (
    echo !GREEN!  [ok] Portable Python already installed: %PYDIR%\bin\python.exe!RESET!
    goto :skip_python
)

REM Check if Python is already on the system PATH
where python >nul 2>&1
if %errorlevel% equ 0 (
    echo !GREEN!  [ok] Python already on PATH!RESET!
    goto :skip_python
)
where py >nul 2>&1
if %errorlevel% equ 0 (
    echo !GREEN!  [ok] Python launcher [py] already on PATH!RESET!
    goto :skip_python
)

echo %CYAN%  ==^> Downloading Python %PY_VERSION% (full installer with GUI support)...%RESET%
set "PY_TMP=%TEMP%\%PY_INSTALLER%"

REM Clean up any existing installer from temp. If it's locked, we detect it here.
if exist "%PY_TMP%" (
    taskkill /f /im "python-%PY_VERSION%-amd64.exe" >nul 2>&1
    del "%PY_TMP%" >nul 2>&1
    if exist "%PY_TMP%" (
        echo !RED!  [!!] The installer file is currently locked by another process.!RESET!
        echo !YELLOW!  Please close any running Python installers or reboot your machine, then try again.!RESET!
        goto :skip_python
    )
)

REM Download using PowerShell (built-in, not a package manager)
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri $env:PY_URL -OutFile $env:PY_TMP"
if not exist "%PY_TMP%" (
    echo !RED!  [!!] Download failed. Check your internet connection.!RESET!
    echo !YELLOW!  You can manually download Python from https://www.python.org/downloads/!RESET!
    goto :skip_python
)


echo %CYAN%  ==^> Installing Python to %PYDIR% (unattended progress bar, with tkinter)...%RESET%

REM Use the official installer in passive mode (shows progress bar, but no user input needed):
REM   - TargetDir       : installs into our app folder (not system-wide)
REM   - InstallAllUsers : 0 = per-directory, no system changes
REM   - PrependPath     : 0 = don't touch the system PATH
REM   - Include_tcltk   : 1 = include Tcl/Tk (required for GUI)
REM   - Include_pip     : 1 = include pip
REM   - Include_test    : 0 = skip test suite to save space
REM   - Include_launcher: 0 = don't install the py.exe launcher system-wide
REM   - AssociateFiles  : 0 = don't register file associations
REM   - Shortcuts       : 0 = no start menu shortcuts
"%PY_TMP%" /passive InstallAllUsers=0 TargetDir="%PYDIR%" ^
    Include_tcltk=1 Include_pip=1 Include_test=0 ^
    Include_launcher=0 AssociateFiles=0 Shortcuts=0 ^
    PrependPath=0

if exist "%PYDIR%\python.exe" (
    echo !GREEN!  [ok] Python %PY_VERSION% installed: %PYDIR%\python.exe!RESET!
    REM Set machine env so the launcher can find it
    setx TORCHAIN_PYTHON "%PYDIR%\python.exe" /M >nul 2>&1
    echo !GREEN!  [ok] Set TORCHAIN_PYTHON=%PYDIR%\python.exe!RESET!
) else (
    echo !YELLOW!  [!!] Standard Python installer failed [Windows Installer engine may be stuck].!RESET!
    echo !CYAN!  ==^> Falling back to downloading portable pre-built Python 3.9 from GitHub...!RESET!
    
    set "PORTABLE_PY_URL=https://github.com/bjia56/portable-python/releases/download/cpython-v3.9.25-build.0/python-full-3.9.25-windows-x86_64.zip"
    set "PORTABLE_PY_ZIP=%TEMP%\portable_py.zip"
    
    REM Clean up any stale zip first
    if exist "!PORTABLE_PY_ZIP!" del "!PORTABLE_PY_ZIP!" >nul 2>&1
    
    REM Download portable python zip
    powershell -NoProfile -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri $env:PORTABLE_PY_URL -OutFile $env:PORTABLE_PY_ZIP"
    
    if not exist "!PORTABLE_PY_ZIP!" (
        echo !RED!  [!!] Fallback download failed. Check your internet connection.!RESET!
        goto :skip_python
    )
    
    echo !CYAN!  ==^> Extracting portable Python to %PYDIR%...!RESET!
    if not exist "%PYDIR%" mkdir "%PYDIR%"
    
    REM Extract zip contents to temp folder
    set "PORTABLE_TMP=%TEMP%\portable_py_extracted"
    if exist "!PORTABLE_TMP!" rmdir /s /q "!PORTABLE_TMP!" >nul 2>&1
    mkdir "!PORTABLE_TMP!"
    powershell -NoProfile -Command "$ProgressPreference = 'SilentlyContinue'; Expand-Archive -Path $env:PORTABLE_PY_ZIP -DestinationPath $env:PORTABLE_TMP -Force"
    
    REM Move files from extracted subfolder directly to %PYDIR%
    xcopy "!PORTABLE_TMP!\python-full-3.9.25-windows-x86_64\*" "%PYDIR%\" /E /I /Y /Q >nul 2>&1
    
    REM Clean up temp files
    del "!PORTABLE_PY_ZIP!" >nul 2>&1
    rmdir /s /q "!PORTABLE_TMP!" >nul 2>&1
    
    REM Verify if portable python is now in place
    if exist "%PYDIR%\bin\python.exe" (
        echo !GREEN!  [ok] Portable Python 3.9 successfully installed to %PYDIR%\bin\python.exe!RESET!
        setx TORCHAIN_PYTHON "%PYDIR%\bin\python.exe" /M >nul 2>&1
        echo !GREEN!  [ok] Set TORCHAIN_PYTHON=%PYDIR%\bin\python.exe!RESET!
    ) else (
        echo !RED!  [!!] Portable Python installation failed.!RESET!
        goto :skip_python
    )
)

REM Clean up the installer
del "%PY_TMP%" >nul 2>&1

:skip_python

REM =========================================================================
REM  Step 2: Extract tor.exe from bundled Tor.zip
REM =========================================================================
REM Look for tor.exe in the expected locations first
set "TOR_FOUND="
if exist "%TORDIR%\Tor\tor.exe" (
    set "TOR_FOUND=%TORDIR%\Tor\tor.exe"
)
if not defined TOR_FOUND if exist "%TORDIR%\tor.exe" (
    set "TOR_FOUND=%TORDIR%\tor.exe"
)

if defined TOR_FOUND (
    echo !GREEN!  [ok] tor.exe already present: !TOR_FOUND!!RESET!
    goto :skip_tor
)

REM Check if the Tor.zip bundle exists in the script directory
set "TOR_ZIP=%SCRIPTDIR%\Tor.zip"
if not exist "%TOR_ZIP%" (
    echo !RED!  [!!] Tor.zip not found at %TOR_ZIP%!RESET!
    echo !YELLOW!  Expected the bundled Tor.zip in the windows\ directory.!RESET!
    goto :skip_tor
)

echo %CYAN%  ==^> Extracting Tor from bundled Tor.zip...%RESET%

REM Create the tor directory
if not exist "%TORDIR%" mkdir "%TORDIR%"

REM Extract using PowerShell's Expand-Archive (built into Windows 10/11)
powershell -NoProfile -Command "$ProgressPreference = 'SilentlyContinue'; Expand-Archive -Path $env:TOR_ZIP -DestinationPath $env:TORDIR -Force"

REM Find tor.exe after extraction (could be in a subfolder)
set "TOR_EXE="
if exist "%TORDIR%\Tor\tor.exe" (
    set "TOR_EXE=%TORDIR%\Tor\tor.exe"
)
if not defined TOR_EXE if exist "%TORDIR%\tor\tor.exe" (
    set "TOR_EXE=%TORDIR%\tor\tor.exe"
)
if not defined TOR_EXE if exist "%TORDIR%\tor.exe" (
    set "TOR_EXE=%TORDIR%\tor.exe"
)
REM Search recursively as a last resort
if not defined TOR_EXE (
    for /r "%TORDIR%" %%f in (tor.exe) do (
        if not defined TOR_EXE set "TOR_EXE=%%f"
    )
)

if defined TOR_EXE (
    echo !GREEN!  [ok] tor.exe extracted: !TOR_EXE!!RESET!
    setx TORCHAIN_TOR "!TOR_EXE!" /M >nul 2>&1
    echo !GREEN!  [ok] Set TORCHAIN_TOR=!TOR_EXE!!RESET!
) else (
    echo !RED!  [!!] tor.exe not found after extraction.!RESET!
    echo !YELLOW!  Check that Tor.zip contains a valid Tor bundle.!RESET!
)

:skip_tor

REM =========================================================================
REM  Step 3: Copy torchain (the tcwin package) into the app dir
REM =========================================================================
echo %CYAN%  ==^> Installing torchain into %APPDIR%...%RESET%

if not exist "%APPDIR%" mkdir "%APPDIR%"

REM Copy the tcwin package
set "TCWIN_SRC=%REPOROOT%\tcwin"
if not exist "%TCWIN_SRC%" (
    echo !RED!  [!!] tcwin package not found at %TCWIN_SRC%!RESET!
    goto :done
)

REM Use xcopy for recursive directory copy
xcopy "%TCWIN_SRC%" "%APPDIR%\tcwin\" /E /I /Y /Q >nul 2>&1
if %errorlevel% equ 0 (
    echo !GREEN!  [ok] tcwin package copied!RESET!
) else (
    echo !RED!  [!!] Failed to copy tcwin package!RESET!
)

REM Copy launcher scripts
if exist "%SCRIPTDIR%\torchain.cmd" (
    copy /Y "%SCRIPTDIR%\torchain.cmd" "%APPDIR%\" >nul 2>&1
    echo !GREEN!  [ok] torchain.cmd copied!RESET!
)
if exist "%SCRIPTDIR%\torchain.ps1" (
    copy /Y "%SCRIPTDIR%\torchain.ps1" "%APPDIR%\" >nul 2>&1
    echo !GREEN!  [ok] torchain.ps1 copied!RESET!
)
if exist "%SCRIPTDIR%\internet.ps1" (
    copy /Y "%SCRIPTDIR%\internet.ps1" "%APPDIR%\" >nul 2>&1
    echo !GREEN!  [ok] internet.ps1 copied!RESET!
)
if exist "%SCRIPTDIR%\internet.bat" (
    copy /Y "%SCRIPTDIR%\internet.bat" "%APPDIR%\" >nul 2>&1
    echo !GREEN!  [ok] internet.bat copied!RESET!
)
if exist "%SCRIPTDIR%\uninstall.bat" (
    copy /Y "%SCRIPTDIR%\uninstall.bat" "%APPDIR%\" >nul 2>&1
    echo !GREEN!  [ok] uninstall.bat copied!RESET!
)
if exist "%SCRIPTDIR%\diagnose.bat" (
    copy /Y "%SCRIPTDIR%\diagnose.bat" "%APPDIR%\" >nul 2>&1
    echo !GREEN!  [ok] diagnose.bat copied!RESET!
)



REM =========================================================================
REM  Step 4: Add torchain to system PATH
REM =========================================================================
echo %CYAN%  ==^> Adding torchain to system PATH...%RESET%

REM Use PowerShell to safely append to Machine PATH (no 1024-char limit).
REM Checks for duplicates first, and broadcasts WM_SETTINGCHANGE so new
REM terminals pick it up immediately.
powershell -NoProfile -Command "$target = '%APPDIR%'; $current = [Environment]::GetEnvironmentVariable('Path', 'Machine'); $entries = $current -split ';' | ForEach-Object { $_.TrimEnd('\') }; $clean = $target.TrimEnd('\'); if ($entries -contains $clean) { Write-Host '  Already in PATH'; exit 0 }; $newPath = $current.TrimEnd(';') + ';' + $target; [Environment]::SetEnvironmentVariable('Path', $newPath, 'Machine'); Write-Host '  Added to PATH'; $sig = '[DllImport(' + [char]34 + 'user32.dll' + [char]34 + ', SetLastError=true, CharSet=CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);'; Add-Type -Namespace Win32 -Name NativeMethods -MemberDefinition $sig; $r = [UIntPtr]::Zero; [Win32.NativeMethods]::SendMessageTimeout([IntPtr]0xFFFF, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$r) | Out-Null"

echo %GREEN%  [ok] torchain is now available from any terminal%RESET%

REM =========================================================================
REM  Step 5: Create Start Menu & Desktop shortcuts
REM =========================================================================
echo %CYAN%  ==^> Creating shortcuts...%RESET%

REM Start Menu (All Users) - makes torchain searchable in Windows Search
set "STARTMENU=%ProgramData%\Microsoft\Windows\Start Menu\Programs\Torchain"
if not exist "%STARTMENU%" mkdir "%STARTMENU%"

REM Create the GUI shortcut using PowerShell COM (built into every Windows)
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$s = $ws.CreateShortcut('%STARTMENU%\Torchain.lnk'); " ^
  "$s.TargetPath = '%APPDIR%\torchain.cmd'; " ^
  "$s.Arguments = 'gui'; " ^
  "$s.WorkingDirectory = '%APPDIR%'; " ^
  "$s.Description = 'Torchain - System-wide Tor anonymizer'; " ^
  "$s.Save()"
if exist "%STARTMENU%\Torchain.lnk" (
    echo !GREEN!  [ok] Start Menu shortcut created!RESET!
) else (
    echo !YELLOW!  [!!] Start Menu shortcut failed!RESET!
)

REM Create an internet recovery shortcut in Start Menu
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$s = $ws.CreateShortcut('%STARTMENU%\Torchain - Fix Internet.lnk'); " ^
  "$s.TargetPath = 'powershell.exe'; " ^
  "$s.Arguments = '-NoProfile -ExecutionPolicy Bypass -File \"%APPDIR%\internet.ps1\"'; " ^
  "$s.WorkingDirectory = '%APPDIR%'; " ^
  "$s.Description = 'Restore normal internet if torchain left you offline'; " ^
  "$s.Save()"
if exist "%STARTMENU%\Torchain - Fix Internet.lnk" (
    echo !GREEN!  [ok] Start Menu internet recovery shortcut created!RESET!
) else (
    echo !YELLOW!  [!!] Internet recovery shortcut failed!RESET!
)

REM Desktop shortcut for the GUI
set "DESKTOP=%PUBLIC%\Desktop"
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$s = $ws.CreateShortcut('%DESKTOP%\Torchain.lnk'); " ^
  "$s.TargetPath = '%APPDIR%\torchain.cmd'; " ^
  "$s.Arguments = 'gui'; " ^
  "$s.WorkingDirectory = '%APPDIR%'; " ^
  "$s.Description = 'Torchain - System-wide Tor anonymizer'; " ^
  "$s.Save()"
if exist "%DESKTOP%\Torchain.lnk" (
    echo !GREEN!  [ok] Desktop shortcut created!RESET!
) else (
    echo !YELLOW!  [!!] Desktop shortcut failed!RESET!
)

REM =========================================================================
REM  Step 6: Summary
REM =========================================================================
:done
echo.
echo %CYAN%  ==^> Setup Summary%RESET%
echo.

REM Check Python
set "FINAL_PY="
if exist "%PYDIR%\python.exe" (
    set "FINAL_PY=%PYDIR%\python.exe"
    echo !GREEN!  [ok] Python  : %PYDIR%\python.exe!RESET!
) else if exist "%PYDIR%\bin\python.exe" (
    set "FINAL_PY=%PYDIR%\bin\python.exe"
    echo !GREEN!  [ok] Python  : %PYDIR%\bin\python.exe!RESET!
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        echo !GREEN!  [ok] Python  : system PATH!RESET!
        set "FINAL_PY=python"
    ) else (
        echo !RED!  [!!] Python  : NOT FOUND!RESET!
    )
)

REM Check Tor
set "FINAL_TOR="
if defined TOR_EXE (
    echo !GREEN!  [ok] tor.exe : !TOR_EXE!!RESET!
    set "FINAL_TOR=!TOR_EXE!"
) else if defined TOR_FOUND (
    echo !GREEN!  [ok] tor.exe : !TOR_FOUND!!RESET!
    set "FINAL_TOR=!TOR_FOUND!"
) else (
    echo !RED!  [!!] tor.exe : NOT FOUND!RESET!
)

REM Check tcwin
if exist "%APPDIR%\tcwin\__init__.py" (
    echo !GREEN!  [ok] tcwin   : %APPDIR%\tcwin!RESET!
) else (
    echo !RED!  [!!] tcwin   : NOT FOUND!RESET!
)

echo.
if defined FINAL_PY if defined FINAL_TOR (
    echo !GREEN!  Setup complete!!RESET!
    echo !GREEN!  Launch from: Start Menu ^> Torchain, or Desktop shortcut!RESET!
) else (
    echo !YELLOW!  Setup incomplete - see errors above.!RESET!
)
echo !YELLOW!  If you ever lose internet: Start Menu ^> Torchain ^> Fix Internet!RESET!
echo.

pause
exit /b 0
