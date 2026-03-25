#!/bin/bash
# ForgeChannels — one command to run everything
set -e

cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Setting up Python environment..."
    python3 -m venv .venv
fi

# Install deps
source .venv/bin/activate
python3 -m pip install -q -r requirements.txt

# Run the CLI, passing through any args (e.g. --dry-run)
python3 -m cli.main "$@"
