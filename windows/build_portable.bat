@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM  torchain - Build Windows distributions (standalone onefile & portable folder)
REM
REM  This script uses PyInstaller to bundle the entire tcwin package for Windows:
REM    - Standalone single-file executable: dist\torchain.exe  (--onefile)
REM    - Portable folder distribution:      dist\torchain\    (folder)
REM    - Compressed portable archive:       dist\torchain-portable.zip
REM
REM  Usage:
REM    windows\build_portable.bat             (builds both onefile & folder)
REM    windows\build_portable.bat /onefile    (builds only standalone torchain.exe)
REM    windows\build_portable.bat /folder     (builds only portable folder & zip)
REM
REM  Requirements:
REM    - Python 3.9+ on PATH (or installed via windows\setup.bat)
REM    - The bundled windows\Tor.zip (already in the repo)
REM ============================================================================

set "SCRIPTDIR=%~dp0"
if "%SCRIPTDIR:~-1%"=="\" set "SCRIPTDIR=%SCRIPTDIR:~0,-1%"
set "REPOROOT=%SCRIPTDIR%\.."
set "FOLDER_SPEC=%SCRIPTDIR%\torchain_portable.spec"
set "ONEFILE_SPEC=%SCRIPTDIR%\torchain_onefile.spec"
set "OUTDIR=%REPOROOT%\dist\torchain"
set "STANDALONE_EXE=%REPOROOT%\dist\torchain.exe"

set "BUILD_MODE=all"
if /i "%~1"=="/onefile" set "BUILD_MODE=onefile"
if /i "%~1"=="-onefile" set "BUILD_MODE=onefile"
if /i "%~1"=="--onefile" set "BUILD_MODE=onefile"
if /i "%~1"=="onefile" set "BUILD_MODE=onefile"
if /i "%~1"=="/folder" set "BUILD_MODE=folder"
if /i "%~1"=="-folder" set "BUILD_MODE=folder"
if /i "%~1"=="--folder" set "BUILD_MODE=folder"
if /i "%~1"=="folder" set "BUILD_MODE=folder"

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
echo  torchain Windows Builder (Mode: !BUILD_MODE!)
echo  ================================================
echo.

REM --- Check Tor.zip exists ---
if not exist "%SCRIPTDIR%\Tor.zip" (
    echo [ERROR] Tor.zip not found at %SCRIPTDIR%\Tor.zip
    echo         The bundled Tor.zip is required to include tor.exe in the build.
    exit /b 1
)

REM --- Install/upgrade PyInstaller ---
echo [1/4] Installing/verifying PyInstaller...
%PY% -m pip install --upgrade pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install PyInstaller.
    echo         Try: %PY% -m pip install pyinstaller
    exit /b 1
)
echo        PyInstaller ready.

REM --- Clean previous build artifacts ---
echo [2/4] Cleaning previous build...
if exist "%REPOROOT%\build" rmdir /s /q "%REPOROOT%\build" >nul 2>&1
if "!BUILD_MODE!"=="folder" (
    if exist "%OUTDIR%" rmdir /s /q "%OUTDIR%" >nul 2>&1
    if exist "%REPOROOT%\dist\torchain-portable.zip" del "%REPOROOT%\dist\torchain-portable.zip" >nul 2>&1
) else if "!BUILD_MODE!"=="onefile" (
    if exist "%STANDALONE_EXE%" del "%STANDALONE_EXE%" >nul 2>&1
) else (
    if exist "%OUTDIR%" rmdir /s /q "%OUTDIR%" >nul 2>&1
    if exist "%STANDALONE_EXE%" del "%STANDALONE_EXE%" >nul 2>&1
    if exist "%REPOROOT%\dist\torchain-portable.zip" del "%REPOROOT%\dist\torchain-portable.zip" >nul 2>&1
)

REM --- Build Standalone Onefile ---
if "!BUILD_MODE!"=="onefile" goto build_onefile
if "!BUILD_MODE!"=="all" goto build_onefile
goto check_folder

:build_onefile
echo [3/4] Building standalone single-file executable (torchain.exe)...
%PY% -m PyInstaller --noconfirm "%ONEFILE_SPEC%"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Standalone PyInstaller build failed.
    exit /b 1
)
if not exist "%STANDALONE_EXE%" (
    echo [ERROR] Standalone torchain.exe not found in dist\
    exit /b 1
)
echo        Standalone executable created: dist\torchain.exe
if "!BUILD_MODE!"=="onefile" goto finish

:check_folder
if "!BUILD_MODE!"=="folder" goto build_folder
if "!BUILD_MODE!"=="all" goto build_folder
goto finish

:build_folder
echo [4/4] Building portable folder distribution...
%PY% -m PyInstaller --noconfirm "%FOLDER_SPEC%"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Portable folder PyInstaller build failed.
    exit /b 1
)

if not exist "%OUTDIR%\torchain.exe" (
    echo.
    echo [ERROR] torchain.exe not found in dist\torchain\ after build.
    exit /b 1
)

set "TCL_OK=0"
if exist "%OUTDIR%\tcl8.6" set "TCL_OK=1"
if exist "%OUTDIR%\_tcl_data" set "TCL_OK=1"
if "%TCL_OK%"=="0" (
    echo [WARNING] Tcl/Tk data directories not found in folder output.
)

pushd "%REPOROOT%\dist"
powershell -NoProfile -Command "Compress-Archive -Path 'torchain' -DestinationPath 'torchain-portable.zip' -Force"
popd
echo        Portable archive created: dist\torchain-portable.zip

:finish
echo.
echo  ================================================
echo  Build successful!
echo.
if exist "%STANDALONE_EXE%" (
    for %%A in ("%STANDALONE_EXE%") do (
        set "SIZE=%%~zA"
        set /a "MB=!SIZE! / 1048576"
        echo  Standalone Exe: dist\torchain.exe (~!MB! MB)
    )
)
if exist "%OUTDIR%\torchain.exe" (
    echo  Folder:         dist\torchain\
)
if exist "%REPOROOT%\dist\torchain-portable.zip" (
    for %%A in ("%REPOROOT%\dist\torchain-portable.zip") do (
        set "ZSIZE=%%~zA"
        set /a "ZMB=!ZSIZE! / 1048576"
        echo  Portable Zip:   dist\torchain-portable.zip (~!ZMB! MB)
    )
)
echo.
echo  ================================================
pause
exit /b 0
