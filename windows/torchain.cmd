@echo off
setlocal EnableDelayedExpansion
REM torchain launcher for Windows - locates Python, self-elevates, runs tcwin.
set "APPDIR=%~dp0"

REM 1) Prefer the self-contained Python shipped beside torchain.
set "PYEXE="
if exist "%APPDIR%python\python.exe" set "PYEXE=%APPDIR%python\python.exe"
if not defined PYEXE if exist "%APPDIR%python\bin\python.exe" set "PYEXE=%APPDIR%python\bin\python.exe"
if not defined PYEXE if defined TORCHAIN_PYTHON if exist "%TORCHAIN_PYTHON%" set "PYEXE=%TORCHAIN_PYTHON%"
if not defined PYEXE (
  where py >nul 2>&1 && set "PYEXE=py"
)
if not defined PYEXE (
  where python >nul 2>&1 && set "PYEXE=python"
)
if not defined PYEXE (
  echo Python not found. Run windows\setup.bat first.
  exit /b 69
)

REM 2) Require elevation (net session succeeds only when elevated).
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Administrator rights required - relaunching elevated...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%APPDIR%torchain.ps1" %*
  exit /b 0
)

REM 3) Run the package with the app dir as the working dir so 'tcwin' imports.
pushd "%APPDIR%"
"%PYEXE%" -m tcwin %*
set "RC=%errorlevel%"
popd
exit /b %RC%
