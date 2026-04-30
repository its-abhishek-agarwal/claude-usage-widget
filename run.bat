@echo off
title Claude Tracker Installer

if "%1"=="GO" goto main
start "" cmd /c ""%~f0" GO"
exit

:main
echo.
echo Claude Tracker Installer
echo ========================
echo.

set LOG=%~dp0install.log
echo Install started %date% %time% > "%LOG%"

rem Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found.
    echo Install from https://www.python.org/downloads/
    echo Check "Add Python to PATH" during install, then run this again.
    echo ERROR: Python not found >> "%LOG%"
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  Found: %%v
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo Found: %%v >> "%LOG%"

rem Install dependencies (one-time)
if not exist "%~dp0.deps_installed" (
    echo.
    echo Installing dependencies, please wait...
    pip install -r "%~dp0requirements.txt" -q --disable-pip-version-check >> "%LOG%" 2>&1
    if %errorlevel% neq 0 (
        echo ERROR: pip install failed. See install.log for details.
        echo pip FAILED >> "%LOG%"
        pause
        exit /b 1
    )
    echo done > "%~dp0.deps_installed"
    echo Dependencies installed OK.
    echo deps OK >> "%LOG%"
)

rem Register native messaging host
echo.
echo Registering native host...
python "%~dp0setup_host.py" >> "%LOG%" 2>&1
if %errorlevel% neq 0 (
    echo ERROR: setup_host.py failed. See install.log for details.
    pause
    exit /b 1
)
echo Done.

rem Launch widget
echo.
echo Starting widget...
python "%~dp0launcher.py" >> "%LOG%" 2>&1
if %errorlevel% neq 0 (
    echo ERROR: launcher.py failed. See install.log for details.
    pause
    exit /b 1
)

echo.
echo Claude Tracker is running in your tray.
echo.
echo Success %date% %time% >> "%LOG%"
