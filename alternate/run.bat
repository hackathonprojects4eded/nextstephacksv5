@echo off
REM Windows run script for Alternate Fire Radio System (no terminal window)

REM Activate virtual environment if it exists
if exist ..\.venv\Scripts\activate.bat (
    call ..\.venv\Scripts\activate.bat
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    set PYTHON_CMD=pythonw
) else (
    set PYTHON_CMD=pythonw.exe
)

%PYTHON_CMD% main.py 