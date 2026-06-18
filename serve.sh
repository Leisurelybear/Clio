#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/python" ]; then
    echo "Virtual environment not found. Run bash setup.sh first." >&2
    exit 1
fi

echo "Starting web UI..."
exec .venv/bin/python main.py serve "$@"
