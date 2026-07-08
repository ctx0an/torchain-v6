@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM  torchain - Build portable folder distribution
REM
REM  This script uses PyInstaller to bundle the entire tcwin package into a
REM  portable torchain\ folder that works on any Windows 10/11 machine
REM  without Python installed.
REM
REM  A FOLDER distribution is used (not --onefile) because tkinter's Tcl/Tk
REM  runtime needs its data directories on disk for the GUI to work.
REM
REM  Requirements:
REM    - Python 3.9+ on PATH (or installed via windows\setup.bat)
REM    - The bundled windows\Tor.zip (already in the repo)
REM
REM  Output:
REM    dist\torchain\       — portable folder (run torchain.exe from here)
REM    dist\torchain-portable.zip — zipped folder for easy transport
REM ============================================================================

set "SCRIPTDIR=%~dp0"
if "%SCRIPTDIR:~-1%"=="\" set "SCRIPTDIR=%SCRIPTDIR:~0,-1%"
set "REPOROOT=%SCRIPTDIR%\.."
set "SPECFILE=%SCRIPTDIR%\torchain_portable.spec"
set "OUTDIR=%REPOROOT%\dist\torchain"

REM --- Check Python ---
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found on PATH.
        echo         Run windows\setup.bat first, or install Python 3.9+.
        exit /b 1
    )
    set "PY=py"
) else (
    set "PY=python"
)

echo.
echo  torchain portable builder (folder distribution)
echo  ================================================
echo.

REM --- Check Tor.zip exists ---
if not exist "%SCRIPTDIR%\Tor.zip" (
    echo [ERROR] Tor.zip not found at %SCRIPTDIR%\Tor.zip
    echo         The bundled Tor.zip is required to include tor.exe in the build.
    exit /b 1
)

REM --- Install/upgrade PyInstaller ---
echo [1/4] Installing PyInstaller...
%PY% -m pip install --upgrade pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install PyInstaller.
    echo         Try: %PY% -m pip install pyinstaller
    exit /b 1
)
echo        PyInstaller ready.

REM --- Clean previous build ---
echo [2/4] Cleaning previous build...
if exist "%REPOROOT%\build" rmdir /s /q "%REPOROOT%\build" >nul 2>&1
if exist "%OUTDIR%" rmdir /s /q "%OUTDIR%" >nul 2>&1
if exist "%REPOROOT%\dist\torchain-portable.zip" del "%REPOROOT%\dist\torchain-portable.zip" >nul 2>&1

REM --- Build ---
echo [3/4] Building portable folder (this may take a minute)...
echo.
%PY% -m PyInstaller --noconfirm "%SPECFILE%"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] PyInstaller build failed. Check the output above.
    exit /b 1
)

REM --- Verify folder ---
if not exist "%OUTDIR%\torchain.exe" (
    echo.
    echo [ERROR] torchain.exe not found in dist\torchain\ after build.
    exit /b 1
)

REM --- Check tkinter works by looking for Tcl/Tk data ---
set "TCL_OK=0"
if exist "%OUTDIR%\tcl8.6" set "TCL_OK=1"
if exist "%OUTDIR%\_tcl_data" set "TCL_OK=1"
if "%TCL_OK%"=="0" (
    echo.
    echo [WARNING] Tcl/Tk data directories not found in output.
    echo           The CLI will work but the GUI may fail.
    echo           Make sure Python was installed with Tcl/Tk support.
)

REM --- Zip for easy transport ---
echo [4/4] Creating portable zip...
pushd "%REPOROOT%\dist"
powershell -NoProfile -Command "Compress-Archive -Path 'torchain' -DestinationPath 'torchain-portable.zip' -Force"
popd

REM --- Done ---
echo.
echo  ================================================
echo  Build successful!
echo.
echo  Folder: dist\torchain\
echo  Zip:    dist\torchain-portable.zip
echo.
for %%A in ("%OUTDIR%\torchain.exe") do (
    set "SIZE=%%~zA"
    set /a "MB=!SIZE! / 1048576"
    echo  torchain.exe: ~!MB! MB
)
echo.
if exist "%REPOROOT%\dist\torchain-portable.zip" (
    for %%A in ("%REPOROOT%\dist\torchain-portable.zip") do (
        set "ZSIZE=%%~zA"
        set /a "ZMB=!ZSIZE! / 1048576"
        echo  Zip size: ~!ZMB! MB
    )
)
echo.
echo  To use:
echo    1. Extract torchain-portable.zip on any Windows 10/11 machine
echo    2. Right-click torchain.exe -^> Run as administrator
echo    3. First run extracts tor.exe to %%ProgramData%%\torchain\
echo    4. Use: torchain.exe gui          (dashboard with tkinter GUI)
echo           torchain.exe start         (CLI)
echo           torchain.exe doctor        (check dependencies)
echo.
echo  No Python, no VC++ Redistributable, no installer needed.
echo  Everything is inside the folder.
echo  ================================================

pause
exit /b 0
