@echo off
REM TaskTrack — Register daily notification scheduler on Windows
REM Run this script once after cloning the repo.

SET REPO_DIR=%~dp0
SET PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe

IF NOT EXIST "%PYTHON%" (
    REM Try system Python
    WHERE python >nul 2>nul
    IF ERRORLEVEL 1 (
        echo ERROR: Python not found. Please install Python and try again.
        pause
        exit /b 1
    )
    SET PYTHON=python
)

SET SCRIPT=%REPO_DIR%scheduler.py
SET TASK_NAME=TaskTrackNotifier

echo Registering TaskTrack daily notification at 8:00 AM...

schtasks /Create /TN "%TASK_NAME%" /TR "\"%PYTHON%\" \"%SCRIPT%\"" /SC DAILY /ST 08:00 /F

IF ERRORLEVEL 1 (
    echo ERROR: Failed to register scheduled task. Try running as Administrator.
    pause
    exit /b 1
)

echo Success! Task '%TASK_NAME%' will run daily at 8:00 AM.
echo To remove it: schtasks /Delete /TN "%TASK_NAME%" /F
pause
