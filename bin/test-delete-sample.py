#!/usr/bin/env python3

"""
Test script to verify DELETE sample behavior.

Fetches initial sample list, deletes a sample, and compares results.
"""

import sys
import logging

from pyepignostics.epignostics import EpignosticsPortalClient

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
log = logging.getLogger(__name__)

app = EpignosticsPortalClient()
app.login()
app.get_workflows()

# Fetch initial samples
log.info("=== Fetching initial samples ===")
initial_samples = []
for sample in app.update_samples(detailed=False):
    initial_samples.append((sample._id, sample._name, sample._idat))
    log.info(f"Sample: {sample._id} - {sample._name}")

log.info(f"Total initial samples: {len(initial_samples)}")

if len(initial_samples) == 0:
    log.error("No samples found!")
    sys.exit(1)

# Select sample to delete (by ID from args or first sample)
if len(sys.argv) > 1:
    target_id = int(sys.argv[1])
    sample_to_delete = next((s for s in initial_samples if s[0] == target_id), None)
    if not sample_to_delete:
        log.error(f"Sample {target_id} not found!")
        sys.exit(1)
else:
    sample_to_delete = initial_samples[0]

sample_id, sample_name, sample_idat = sample_to_delete
log.info(f"\n=== Attempting to delete sample: {sample_id} ({sample_name}) ===")

# Get sample object and delete
sample = app.get_sample(sample_id)
if sample:
    result = sample.remove(app)
    log.info(f"Delete result: {result}")
else:
    log.error(f"Could not find sample {sample_id} in cache")
    sys.exit(1)

# Fetch samples again after delete
log.info(f"\n=== Fetching samples after delete ===")
app._samples = {}
app._n_samples = 0
final_samples = []
for sample in app.update_samples(detailed=False):
    final_samples.append((sample._id, sample._name, sample._idat))
    log.info(f"Sample: {sample._id} - {sample._name}")

log.info(f"Total final samples: {len(final_samples)}")

# Compare
log.info(f"\n=== Comparison ===")
log.info(f"Initial count: {len(initial_samples)}")
log.info(f"Final count: {len(final_samples)}")
log.info(f"Difference: {len(initial_samples) - len(final_samples)}")

# Find deleted samples
initial_ids = {s[0] for s in initial_samples}
final_ids = {s[0] for s in final_samples}
removed_ids = initial_ids - final_ids

log.info(f"\nSamples that were removed:")
for sample_id in removed_ids:
    initial = next((s for s in initial_samples if s[0] == sample_id), None)
    log.info(f"  - ID {sample_id}: {initial[1] if initial else 'UNKNOWN'}")

log.info(f"\n=== Results ===")

# Check if target was deleted
if sample_id in removed_ids:
    log.info(f"✓ Target sample {sample_id} was deleted")
else:
    log.error(f"✗ ERROR: Target sample {sample_id} was NOT deleted!")

# Check if other samples were unexpectedly removed
other_removed = removed_ids - {sample_id}
if other_removed:
    log.error(f"✗ ERROR: Other samples were also removed: {other_removed}")
    for sid in other_removed:
        initial = next((s for s in initial_samples if s[0] == sid), None)
        log.error(f"    - ID {sid}: {initial[1] if initial else 'UNKNOWN'}")
elif len(removed_ids) == 1 and sample_id in removed_ids:
    log.info(f"✓ Only the target sample was removed")

# Check for unexpected new samples
added_ids = final_ids - initial_ids
if added_ids:
    log.warning(f"⚠ Unexpected: New samples appeared: {added_ids}")
else:
    log.info(f"✓ No new samples appeared")

# Summary of count change
if len(final_samples) == len(initial_samples) - 1:
    log.info(f"✓ Sample count decreased by 1 (expected): {len(initial_samples)} → {len(final_samples)}")
elif len(final_samples) == len(initial_samples):
    log.error(f"✗ Sample count stayed the same (unexpected): {len(initial_samples)} → {len(final_samples)}")
elif len(final_samples) > len(initial_samples) - 1:
    log.warning(f"⚠ Sample count decreased by {len(initial_samples) - len(final_samples)} (less than expected)")
else:
    log.error(f"✗ Sample count decreased by more than expected: {len(initial_samples)} → {len(final_samples)}")
