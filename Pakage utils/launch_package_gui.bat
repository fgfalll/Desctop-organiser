@echo off
REM NGIT Package GUI Launcher
REM This script launches the NGIT Package GUI application

echo Starting NGIT Package GUI...
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python and try again
    pause
    exit /b 1
)

REM Check if required files exist
if not exist "ngit_package_packer.py" (
    echo Error: ngit_package_packer.py not found
    echo Please ensure both files are in the same directory
    pause
    exit /b 1
)

if not exist "ngit_package_gui.py" (
    echo Error: ngit_package_gui.py not found
    echo Please ensure both files are in the same directory
    pause
    exit /b 1
)

REM Launch the GUI
python ngit_package_gui.py

REM If the GUI exits with an error, pause to see the message
if %errorlevel% neq 0 (
    echo.
    echo GUI exited with error code %errorlevel%
    pause
)