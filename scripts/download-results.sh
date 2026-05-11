#!/bin/bash

# Batch download all completed workflow results from Epignostix to ./cache/
#
# Usage:
#   ./scripts/download-results.sh              # Download all samples
#   ./scripts/download-results.sh TCGA-S9      # Download samples matching filter

set -e

source .venv/bin/activate

python3 bin/download-results.py "$@"
