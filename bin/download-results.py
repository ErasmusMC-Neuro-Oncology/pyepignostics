#!/usr/bin/env python3

"""
Batch download all completed workflow results from Epignostix.

Downloads all samples' completed workflow runs to ./cache/ in organized subdirectories.
Supports optional filtering by sample name.

Usage:
    ./scripts/download-results.sh                # Download all
    ./scripts/download-results.sh TCGA-S9        # Download samples matching 'TCGA-S9'
    python3 bin/download-results.py TCGA-S9      # Direct Python call
"""

import sys
import logging
from tqdm import tqdm

from pyepignostics.epignostics import EpignosticsPortalClient
from pyepignostics.workflows import classifierWorkflows

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
log = logging.getLogger(__name__)

# Optional sample name filter from command line
sample_filter = sys.argv[1] if len(sys.argv) > 1 else None

# Initialize API client
app = EpignosticsPortalClient()
app.login()
app.get_workflows()

# Get total sample count for progress bar
n = app.get_sample_count()
log.info(f"Found {n} samples" + (f" (filter: '{sample_filter}')" if sample_filter else ""))

# Download each sample's completed workflow results
downloaded_count = 0
skipped_filtered_count = 0
skipped_cached_count = 0

for sample in tqdm(app.update_samples(detailed=False), total=n, desc="Samples"):
    # Filter on sample name FIRST (before expensive deep read)
    if sample_filter and sample_filter not in sample._name:
        skipped_filtered_count += 1
        continue

    # Fetch workflow runs for this sample (deep read - only for matching samples)
    sample.get_workflow_runs_new(app)

    # Process each workflow run
    for run in sample._workflow_runs:
        try:
            workflow = classifierWorkflows.get(run._workflow_id)
        except KeyError:
            log.warning(f"Workflow {run._workflow_id} not found in registry")
            continue

        # Skip if already cached
        if run.is_cached(workflow=workflow, sample_name=sample._name):
            log.debug(f"Already cached: {sample._name} / {workflow.name_short}")
            skipped_cached_count += 1
            continue

        # Download and cache all results for this workflow run
        log.info(f"Downloading: {sample._name} / {workflow.name_short} (run {run._id})")
        try:
            run.cache_all(app, sample_name=sample._name, workflow=workflow)
            downloaded_count += 1
        except Exception as e:
            log.error(f"Failed to download {sample._name} / {workflow.name_short}: {e}")

summary = f"Downloaded: {downloaded_count}"
if skipped_cached_count > 0:
    summary += f" | Already cached: {skipped_cached_count}"
if skipped_filtered_count > 0:
    summary += f" | Filtered out: {skipped_filtered_count}"
log.info(summary)
