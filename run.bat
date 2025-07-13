@echo off
REM Windows run script for Firejams

REM Activate virtual environment if it exists
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

where python >nul 2>nul
if %errorlevel%==0 (
    set PYTHON_CMD=python
) else (
    where python3 >nul 2>nul
    if %errorlevel%==0 (
        set PYTHON_CMD=python3
    ) else (
        echo Python is not installed.
        exit /b 1
    )
)

%PYTHON_CMD% main.py 