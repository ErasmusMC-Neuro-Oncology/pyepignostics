#!/usr/bin/env python

import logging
import os
import tempfile
import tarfile
import io

from pyepignostics.epignostics import *

from flask import Flask, render_template, send_file
from tqdm import tqdm
#from run import *

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


webapp = Flask(__name__)


app = EpignosticsPortalClient()
app.login()
app.get_workflows()  # Load workflows from API
n_samples = app.get_sample_count()



@webapp.route('/')
def index():
    return render_template('index.html',
        nsamples=app._n_samples,
        samples=app.get_samples(),
        wfs=classifierWorkflows.get_workflows()
        )


def subsample(app, k):
    sslice = {}
    
    i = 0
    for key in app._samples:
        if i < k:
            sslice[key] = []
        
        for ss in app._samples[key]:
            if i < k:
                sslice[key].append(ss)
            i += 1
    
    return sslice


@webapp.route('/scrape')
def scrape():
    for _ in app.update_samples(detailed=True):
        pass

    # save
    # https://www.digitalocean.com/community/tutorials/python-pickle-example

    return render_template('scrape.html', posts=[]) # trigger that updating has completed


@webapp.route('/scrape-list')
def scrape_list():
    app.update_samples_sparse()
    
    
    return render_template('scrape.html', posts=[]) # trigger that updating has completed




@webapp.route("/sample/<int:sample_id>:<sample_idat>/workflow/<int:workflow_id>/execute_job")
def execute_job(sample_id, sample_idat, workflow_id):
    """Execute a workflow for the given sample."""
    sample = app.get_sample(sample_id)

    # If sample not found in cache, create a temporary sample object
    if sample is None:
        log.info(f"Sample {sample_id}:{sample_idat} not in cache, creating temporary object")
        try:
            sample = sample(sample_id, sample_idat, None, None, None)
        except Exception as e:
            log.error(f"Could not create sample object: {sample_id}:{sample_idat} - {str(e)}")
            return "error - could not create sample", 500

    log.info(f"Using sample {sample_id}:{sample_idat}")

    try:
        workflow = classifierWorkflows.get(workflow_id)
        log.info(f"Found workflow {workflow_id}")
    except Exception as e:
        log.error(f"Could not find workflow {workflow_id}: {str(e)}")
        return "error - workflow not found", 404

    success = sample.execute_workflow(app, workflow)

    if success:
        log.info(f"Executed workflow {workflow_id} for sample {sample_id}")
        return "done"
    else:
        log.error(f"Failed to execute workflow {workflow_id} for sample {sample_id}")
        return "error", 500


@webapp.route("/sample/<int:sample_id>:<sample_idat>/workflow_run/<int:run_id>/restart")
def restart_workflow_run(sample_id, sample_idat, run_id):
    """Restart a workflow run."""
    sample = app.get_sample(sample_id)
    if sample is None:
        log.error(f"Could not find sample in cache: {sample_id}:{sample_idat}")
        return "error - sample not found", 404

    # Find the workflow run
    workflow_run = None
    if sample._workflow_runs:
        for run in sample._workflow_runs:
            if run._id == run_id:
                workflow_run = run
                break

    if not workflow_run:
        log.error(f"Could not find workflow run {run_id} for sample {sample_id}:{sample_idat}")
        return "error - workflow run not found", 404

    success = workflow_run.restart(app)

    if success:
        log.info(f"Restarted workflow run {run_id}")
        sample.get_workflow_runs_new(app)
        return "done"
    else:
        log.error(f"Failed to restart workflow run {run_id}")
        return "error", 500


@webapp.route("/sample/<int:sample_id>:<sample_idat>/refresh")
def refresh(sample_id, sample_idat):
    """Refresh sample data by fetching latest workflow runs from API."""
    # Try to get sample from cache first
    sample = app.get_sample(sample_id)

    # If not in cache, fetch it from API
    if not sample:
        log.info(f"Sample not in cache, fetching from API...")
        try:
            for s in app.update_samples(detailed=False):
                if s._id == int(sample_id) and s._idat == str(sample_idat):
                    sample = s
                    break
        except Exception as e:
            log.error(f"Could not fetch sample from API: {str(e)}")
            return "error - sample not found", 404

    if not sample:
        log.error(f"Sample {sample_id}:{sample_idat} not found")
        return "error - sample not found", 404

    log.info(f"Refreshing sample {sample_id}:{sample_idat}")

    # Refresh workflow runs for this sample
    sample.get_workflow_runs_new(app)

    log.info(f"Refreshed {len(sample._workflow_runs)} workflow runs for sample {sample_id}")
    return 'done'


@webapp.route("/sample/<int:sample_id>:<sample_idat>/remove_sample")
def remove_sample(sample_id, sample_idat):
    sample = app.get_sample(sample_id)
    if sample is None:
        log.error(f"Could not find sample in cache: {sample_id}:{sample_idat}")
        return "error - sample not found", 404

    sample.remove(app)
    return 'done removing and refreshing'


@webapp.route("/sample/<int:sample_id>:<sample_idat>/workflow_run/<int:run_id>/cache")
def cache_workflow_result(sample_id, sample_idat, run_id):
    """Cache all workflow run outputs to ./cache directory on server."""
    sample = app.get_sample(sample_id)
    if sample is None:
        log.error(f"Could not find sample in cache: {sample_id}:{sample_idat}")
        return "error - sample not found", 404

    # Find the workflow run
    workflow_run = None
    if sample._workflow_runs:
        for run in sample._workflow_runs:
            if run._id == run_id:
                workflow_run = run
                break

    if not workflow_run:
        log.error(f"Could not find workflow run {run_id} for sample {sample_id}:{sample_idat}")
        return "error - workflow run not found", 404

    # Get workflow object
    try:
        workflow = classifierWorkflows.get(workflow_run._workflow_id)
    except Exception as e:
        log.error(f"Could not find workflow {workflow_run._workflow_id}: {str(e)}")
        workflow = None

    # Cache all outputs for all tasks
    cached_files = workflow_run.cache_all(
        app,
        sample_name=sample._name,
        workflow=workflow
    )

    if not cached_files:
        log.error(f"Failed to cache workflow run {run_id} - no files cached")
        return "error - caching failed", 500

    log.info(f"Cached {len(cached_files)} files for workflow run {run_id}")
    return "done"


@webapp.route("/sample/<int:sample_id>:<sample_idat>/workflow_run/<int:run_id>/download")
def download_workflow_result(sample_id, sample_idat, run_id):
    """Download cached workflow run results as TAR archive."""
    sample = app.get_sample(sample_id)
    if sample is None:
        log.error(f"Could not find sample in cache: {sample_id}:{sample_idat}")
        return "error - sample not found", 404

    # Find the workflow run
    workflow_run = None
    if sample._workflow_runs:
        for run in sample._workflow_runs:
            if run._id == run_id:
                workflow_run = run
                break

    if not workflow_run:
        log.error(f"Could not find workflow run {run_id} for sample {sample_id}:{sample_idat}")
        return "error - workflow run not found", 404

    # Get workflow object
    try:
        workflow = classifierWorkflows.get(workflow_run._workflow_id)
    except Exception as e:
        log.error(f"Could not find workflow {workflow_run._workflow_id}: {str(e)}")
        workflow = None

    # Check if cache directory exists
    if not workflow_run.is_cached(workflow=workflow, sample_name=sample._name):
        log.error(f"Workflow run {run_id} not cached")
        return "error - results not cached yet", 400

    # Determine cache directory
    if workflow:
        workflow_name = workflow._workflow_name_full.replace(" ", "_")
        base_cache_dir = f"cache/{workflow_name}__v{workflow._workflow_version}__{workflow._workflow_id}"
    else:
        base_cache_dir = "cache"

    if sample._name:
        run_dir = os.path.join(base_cache_dir, f"{sample._name}_{run_id}")
    else:
        run_dir = os.path.join(base_cache_dir, str(run_id))

    if not os.path.isdir(run_dir):
        log.error(f"Cache directory not found: {run_dir}")
        return "error - cache directory not found", 404

    try:
        # Create TAR archive on-the-fly and stream to browser
        tar_filename = f"{sample._name}_{run_id}.tar" if sample._name else f"workflow_run_{run_id}.tar"

        # Create in-memory TAR archive
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
            # Add all files from the run directory
            for root, dirs, files in os.walk(run_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Calculate archive name (relative path from cache dir)
                    arcname = os.path.relpath(file_path, base_cache_dir)
                    tar.add(file_path, arcname=arcname)

        tar_buffer.seek(0)
        log.info(f"Created TAR archive with {len(tar_buffer.getvalue())} bytes for workflow run {run_id}")

        from flask import Response
        response = Response(tar_buffer.getvalue(), mimetype='application/x-tar')
        response.headers['Content-Disposition'] = f'attachment; filename="{tar_filename}"'
        return response
    except Exception as e:
        log.error(f"Failed to create TAR archive for workflow run {run_id}: {str(e)}")
        return "error - could not create archive", 500




