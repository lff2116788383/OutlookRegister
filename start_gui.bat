@echo off
setlocal

echo [1/4] Checking Python environment...
python --version >nul 2>nul
if errorlevel 1 (
    echo Python was not detected. Please install Python and add it to PATH.
    pause
    exit /b 1
)

echo [2/4] Checking pip environment...
python -m pip --version >nul 2>nul
if errorlevel 1 (
    echo pip is unavailable. Please verify your Python installation.
    pause
    exit /b 1
)

echo [3/4] Installing or verifying project dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed. Please check your network or retry manually.
    pause
    exit /b 1
)

echo [4/4] Launching GUI...
python launch_gui.py
if errorlevel 1 (
    echo GUI launch failed. Please review the error output above.
    pause
    exit /b 1
)

endlocal
