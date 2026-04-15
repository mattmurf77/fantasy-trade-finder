#!/usr/bin/env bash
# Render build script — runs on every deploy
set -o errexit

pip install -r requirements.txt

# Ensure the data directory exists (SQLite DB lives here)
mkdir -p data
