#!/usr/bin/env python3

"""
Upload an Illumina methylation IDAT sample pair to Epignostix.

Usage:
    ./scripts/upload-sample.sh <grn_idat> <red_idat>
    ./scripts/upload-sample.sh <grn_idat> <red_idat> <sample_identifier>
    python3 bin/upload-sample.py path/to/sample_Grn.idat path/to/sample_Red.idat
    python3 bin/upload-sample.py path/to/sample_Grn.idat path/to/sample_Red.idat MY_SAMPLE_ID

The sample_identifier defaults to the filename with _Grn.idat / _Red.idat stripped.
"""

import sys
import re
import os
import logging

from pyepignostics.epignostics import EpignosticsPortalClient

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
log = logging.getLogger(__name__)

verbose = False
args = []
for arg in sys.argv[1:]:
    if arg in ('-v', '--verbose'):
        verbose = True
    else:
        args.append(arg)

if len(args) < 2:
    print(f"Usage: {sys.argv[0]} [-v] <grn_idat> <red_idat> [sample_identifier]", file=sys.stderr)
    sys.exit(1)

idat_grn = args[0]
idat_red = args[1]

if len(args) >= 3:
    sample_identifier = args[2]
else:
    sample_identifier = re.sub(r'_(Grn|Red)\.idat$', '', os.path.basename(idat_grn))

app = EpignosticsPortalClient()
app.login()
app.get_workflows()

workflow_id = 15

log.info(f"Uploading {sample_identifier} (workflow_id={workflow_id})")
result = app.upload_sample(idat_grn, 
                           idat_red,
                           sample_identifier,
                           workflow_id,
                           verbose=verbose)

if result:
    print(f"sample_id:       {result['sample_id']}")
    print(f"uuid:            {result['uuid']}")
    print(f"workflow_run_id: {result['workflow_run_id']}")
else:
    sys.exit(1)
