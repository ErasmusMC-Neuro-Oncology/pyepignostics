#!/bin/bash

# Setup script for pymnp development environment
# Creates virtualenv and installs dependencies from pyproject.toml

set -e

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip and install build tools
pip install --upgrade pip setuptools wheel

# Install package in editable mode with all dependencies
pip install -e .

echo "✓ Installation complete. Activate with: source .venv/bin/activate"
