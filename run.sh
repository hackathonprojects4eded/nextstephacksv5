#!/bin/sh
# Cross-platform run script for Firejams

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
  if [ -f ".venv/bin/activate" ]; then
    . .venv/bin/activate
  elif [ -f ".venv/Scripts/activate" ]; then
    . .venv/Scripts/activate
  fi
fi

# Try to use python3, fallback to python
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD >/dev/null 2>&1; then
  PYTHON_CMD="python"
fi

$PYTHON_CMD main.py 