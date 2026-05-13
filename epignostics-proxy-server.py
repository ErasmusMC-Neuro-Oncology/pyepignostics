#!/usr/bin/env python

import logging
import os
import tempfile
import tarfile
import io
import uuid
import threading
import requests
from datetime import datetime

from pyepignostics.epignostics import *

from flask import Flask, render_template, send_file, jsonify
from tqdm import tqdm
#from run import *

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


webapp = Flask(__name__)

# Job queue management
jobs_queue = []
completed_jobs = []
jobs_lock = threading.Lock()

# Background worker thread
def job_worker():
    """Background thread that processes jobs sequentially."""
    while True:
        job = None
        with jobs_lock:
            if jobs_queue:
                job = jobs_queue[0]

        if job:
            try:
                process_queued_job(job)
            except Exception as e:
                log.error(f"[WORKER] Unexpected error in job {job.get('id')}: {str(e)}")
            finally:
                with jobs_lock:
                    if jobs_queue and jobs_queue[0] == job:
                        jobs_queue.pop(0)
        else:
            # Sleep briefly if no jobs
            threading.Event().wait(0.1)

# Start worker thread
worker_thread = threading.Thread(target=job_worker, daemon=True)
worker_thread.start()
log.info("[WORKER] Background job worker started")

app = EpignosticsPortalClient()
app.login()
app.get_workflows()  # Load workflows from API
n_samples = app.get_sample_count()


def cleanup_job(job):
    """Remove a job from completed jobs list."""
    with jobs_lock:
        if job in completed_jobs:
            completed_jobs.remove(job)


def process_queued_job(job):
    """Execute a queued job with error handling."""
    log.info(f"[EXECUTOR] Starting job {job['id']} ({job['type']})")
    try:
        job['status'] = 'processing'
        log.info(f"[EXECUTOR] Job {job['id']} set to processing")

        if job['type'] == 'refresh':
            sample_obj = app.get_sample(job['sample_id'])
            if sample_obj is None:
                raise Exception(f"Sample {job['sample_id']} not found")
            sample_obj.get_workflow_runs_new(app)
            # Mark workflows as no longer loading after refresh completes
            sample_obj._workflows_loading.clear()
            log.info(f"Refreshed sample {job['sample_id']}")

        elif job['type'] == 'cache':
            sample_obj = app.get_sample(job['sample_id'])
            if sample_obj is None:
                raise Exception(f"Sample {job['sample_id']} not found")

            workflow_run_obj = None
            for run in sample_obj._workflow_runs:
                if run._id == job['run_id']:
                    workflow_run_obj = run
                    break

            if workflow_run_obj is None:
                raise Exception(f"Workflow run {job['run_id']} not found")

            workflow_obj = classifierWorkflows.get(job['workflow_id'])
            workflow_run_obj.cache_all(app, sample_name=sample_obj._name, workflow=workflow_obj)
            log.info(f"Cached workflow run {job['run_id']}")

        job['status'] = 'completed'
        job['completed_at'] = datetime.utcnow().isoformat() + 'Z'
        log.info(f"[EXECUTOR] Job {job['id']} completed successfully")

    except requests.Timeout:
        job['status'] = 'failed'
        job['error'] = 'Connection timeout - server not responding'
        log.error(f"Job {job['id']} timeout: {job['error']}")
    except requests.ConnectionError as e:
        job['status'] = 'failed'
        job['error'] = f'Connection failed: {str(e)}'
        log.error(f"Job {job['id']} connection error: {job['error']}")
    except Exception as e:
        job['status'] = 'failed'
        job['error'] = str(e)
        log.error(f"Job {job['id']} failed: {job['error']}")
    finally:
        with jobs_lock:
            if job in jobs_queue:
                jobs_queue.remove(job)
            if job['status'] == 'completed' or job['status'] == 'failed':
                completed_jobs.append(job)
                # Auto-cleanup completed jobs after 5 minutes
                threading.Timer(300, cleanup_job, args=[job]).start()



@webapp.route('/')
def index():
    return render_template('index.html',
        nsamples=app._n_samples,
        samples=app.get_samples(),
        wfs=classifierWorkflows.get_workflows()
        )


@webapp.route('/api/queue')
def get_queue():
    """Get current job queue status."""
    with jobs_lock:
        queue_data = {
            'pending': [j for j in jobs_queue],
            'active': [j for j in jobs_queue if j['status'] == 'processing'],
            'completed': [j for j in completed_jobs[-10:]]  # Last 10 completed
        }
    return jsonify(queue_data)


@webapp.route('/api/samples')
def get_samples_api():
    """Get all samples as JSON for dynamic table updates."""
    samples_data = []
    for sample in app.get_samples():
        sample_info = {
            'id': sample._id,
            'idat': sample._idat,
            'name': sample._name,
            'created_at': sample._created_at,
            'chip_type': sample._chip_type,
            'extraction_type': sample._extraction_type,
            'workflow_runs': len(sample._workflow_runs) if sample._workflow_runs else 0,
        }
        samples_data.append(sample_info)

    return jsonify({
        'total': len(samples_data),
        'samples': samples_data
    })


@webapp.route('/api/sample/<int:sample_id>')
def get_sample_api(sample_id):
    """Get in-memory sample data WITHOUT updating from Epignostix."""
    sample = app.get_sample(sample_id)
    if sample is None:
        return jsonify({'error': 'sample not found'}), 404

    # Build workflow status info from current in-memory state
    workflows_data = {}
    for wf in classifierWorkflows:
        status = sample._workflows[wf]['status']
        runs_for_wf = []
        if sample._workflow_runs:
            for run in sample._workflow_runs:
                if run._workflow_id == wf._workflow_id:
                    runs_for_wf.append({
                        'id': run._id,
                        'status': run._status,
                        'cached': run.is_cached(workflow=wf, sample_name=sample._name),
                        'classifier_result': run.get_classifier_result(workflow=wf, sample_name=sample._name)
                    })
        workflows_data[str(wf._workflow_id)] = {
            'status': status,
            'runs': runs_for_wf
        }

    return jsonify({
        'id': sample._id,
        'idat': sample._idat,
        'name': sample._name,
        'workflows': workflows_data
    })


@webapp.route('/api/sample/<int:sample_id>/update', methods=['POST'])
def update_sample_api(sample_id):
    """Update sample data from Epignostix API."""
    sample = app.get_sample(sample_id)
    if sample is None:
        return jsonify({'error': 'sample not found'}), 404

    try:
        # Fetch current workflow runs from Epignostix
        sample.get_workflow_runs_new(app)
        sample._workflows_loading.clear()

        # Build workflow status info
        workflows_data = {}
        for wf in classifierWorkflows:
            status = sample._workflows[wf]['status']
            runs_for_wf = []
            if sample._workflow_runs:
                for run in sample._workflow_runs:
                    if run._workflow_id == wf._workflow_id:
                        runs_for_wf.append({
                            'id': run._id,
                            'status': run._status,
                            'cached': run.is_cached(workflow=wf, sample_name=sample._name),
                            'classifier_result': run.get_classifier_result(workflow=wf, sample_name=sample._name)
                        })
            workflows_data[str(wf._workflow_id)] = {
                'status': status,
                'runs': runs_for_wf
            }

        return jsonify({
            'id': sample._id,
            'idat': sample._idat,
            'name': sample._name,
            'workflows': workflows_data
        })
    except Exception as e:
        log.error(f"Failed to update sample {sample_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500


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
    try:
        # Batch fetch all samples (fast - no workflow details)
        for sample in app.update_samples(detailed=False):
            # Populate workflows dict so template doesn't error
            sample._populate_workflows_dict(set())
            # Mark all workflows as loading since we just fetched with detailed=False
            sample._workflows_loading = set(wf._workflow_id for wf in classifierWorkflows)

        # Queue refresh job for each sample
        n_queued = 0
        for sample in app.get_samples():
            job = {
                'id': str(uuid.uuid4()),
                'type': 'refresh',
                'sample_id': sample._id,
                'sample_idat': sample._idat,
                'status': 'queued',
                'created_at': datetime.utcnow().isoformat() + 'Z',
            }
            with jobs_lock:
                jobs_queue.append(job)
            n_queued += 1

        log.info(f"Queued {n_queued} refresh jobs for all samples")
        return jsonify({'status': 'success', 'queued': n_queued, 'total_samples': app._n_samples})

    except Exception as e:
        log.error(f"Scrape failed: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


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


@webapp.route("/sample/<int:sample_id>:<sample_idat>/refresh", methods=['GET', 'POST'])
def refresh(sample_id, sample_idat):
    """Queue a refresh job for the sample."""
    sample = app.get_sample(sample_id)

    if not sample:
        log.error(f"Sample {sample_id}:{sample_idat} not found")
        return "error - sample not found", 404

    job = {
        'id': str(uuid.uuid4()),
        'type': 'refresh',
        'sample_id': sample_id,
        'sample_idat': sample_idat,
        'status': 'queued',
        'created_at': datetime.utcnow().isoformat() + 'Z',
    }

    with jobs_lock:
        jobs_queue.append(job)
        queue_position = len(jobs_queue)

    log.info(f"Queued refresh for sample {sample_id}, position: {queue_position}")

    return jsonify({'job_id': job['id'], 'status': 'queued', 'position': queue_position})


@webapp.route("/sample/<int:sample_id>:<sample_idat>/remove_sample")
def remove_sample(sample_id, sample_idat):
    sample = app.get_sample(sample_id)
    if sample is None:
        log.error(f"Could not find sample in cache: {sample_id}:{sample_idat}")
        return "error - sample not found", 404

    sample.remove(app)
    return 'done removing and refreshing'


@webapp.route("/sample/<int:sample_id>:<sample_idat>/workflow_run/<int:run_id>/cache", methods=['GET', 'POST'])
def cache_workflow_result(sample_id, sample_idat, run_id):
    """Queue a cache job for the workflow run."""
    sample = app.get_sample(sample_id)
    if sample is None:
        log.error(f"Could not find sample in cache: {sample_id}:{sample_idat}")
        return jsonify({'error': 'sample not found'}), 404

    # Find the workflow run
    workflow_run = None
    if sample._workflow_runs:
        for run in sample._workflow_runs:
            if run._id == run_id:
                workflow_run = run
                break

    if not workflow_run:
        log.error(f"Could not find workflow run {run_id} for sample {sample_id}:{sample_idat}")
        return jsonify({'error': 'workflow run not found'}), 404

    job = {
        'id': str(uuid.uuid4()),
        'type': 'cache',
        'sample_id': sample_id,
        'sample_idat': sample_idat,
        'run_id': run_id,
        'workflow_id': workflow_run._workflow_id,
        'status': 'queued',
        'created_at': datetime.utcnow().isoformat() + 'Z',
    }

    with jobs_lock:
        jobs_queue.append(job)
        queue_position = len(jobs_queue)

    log.info(f"Queued cache for workflow run {run_id}, position: {queue_position}")

    return jsonify({'job_id': job['id'], 'status': 'queued', 'position': queue_position})


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




