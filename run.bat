@echo off
REM Windows run script for Firejams (uv installs Python and the dependencies on first run)
cd /d "%~dp0"
uv run main.py
