#!/bin/sh
# Run script for Firejams (uv installs Python and the dependencies on first run)
cd "$(dirname "$0")" && uv run main.py
