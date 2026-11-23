@echo off
REM FolderKit++ launcher.
REM This runs FolderKit.py using the Python interpreter that has
REM PySide6 installed (C:\Python312), instead of whatever "python"
REM happens to point to on this PC. This avoids:
REM   ModuleNotFoundError: No module named 'PySide6'
REM which happens when multiple Python installs exist and the PATH
REM points to a different one than the one pip installed packages into.
REM
REM If your Python is installed somewhere else, edit the PYEXE line
REM below to match (open this file with Notepad to edit).

setlocal
set PYEXE=C:\Python312\python.exe

if not exist "%PYEXE%" (
    echo Could not find %PYEXE%
    echo Please edit run.bat and set PYEXE to your actual python.exe path.
    pause
    exit /b 1
)

cd /d "%~dp0"
"%PYEXE%" FolderKitPP.py

if errorlevel 1 (
    echo.
    echo FolderKit++ exited with an error. See the message above for details.
    pause
)
