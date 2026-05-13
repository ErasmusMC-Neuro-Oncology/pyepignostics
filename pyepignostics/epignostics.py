#!/usr/bin/env python

import requests
import math
from tqdm import tqdm
import subprocess
import shutil
import os
import logging
import copy
import json
import zipfile
import warnings
from datetime import datetime

from pyepignostics.workflows import classifierWorkflowObj, classifierWorkflowsObj, classifierWorkflows

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)



class workflow_run:
    _id = None
    _run_identifier = None
    _status = None
    _task_runs = None
    _workflow_id = None
    _entity_id = None
    _creator_id = None
    _created_at = None
    _updated_at = None

    def __init__(self, run_id, run_identifier, status, workflow_id, entity_id, creator_id, created_at=None, updated_at=None):
        self._id = run_id
        self._run_identifier = run_identifier
        self._status = status
        self._workflow_id = workflow_id
        self._entity_id = entity_id
        self._creator_id = creator_id
        self._created_at = created_at
        self._updated_at = updated_at
        self._task_runs = None

    def get_detailed_info(self, app):
        """
        Fetch detailed task run information for this workflow run from the API.

        Args:
            app: EpignosticsPortalClient instance with authentication token
        """
        try:
            response = app.get(
                f"{app._SERVER_URL}/workflow_runs/{self._id}",
                verify=True,
            )
            data = response.json()
            self._task_runs = data.get('task_runs', [])
            self._task_runs.sort(key=lambda t: t.get('task', {}).get('task_name', ''))
            log.info(f"Retrieved {len(self._task_runs)} tasks for workflow run {self._id}")
        except requests.exceptions.RequestException as e:
            log.error(f"Could not get detailed info for workflow run {self._id}: {str(e)}")
            self._task_runs = []

    def _get_downloadable_tasks(self):
        """
        Identify tasks with downloadable results (result_type-based).

        Returns list of (task_run, download_info) tuples where download_info contains:
        - result_type: the API result type (e.g., "AnalysisReport")
        - task_result_id: the ID for API calls
        - endpoint: the API endpoint pattern (derived from result_type)
        """
        downloadable = []
        if not self._task_runs:
            return downloadable

        result_type_endpoints = {
            "AnalysisReport": "analysis_idat/report_pdf",
        }

        for task_run in self._task_runs:
            if task_run.get('status') != 'complete':
                continue

            task = task_run.get('task', {})
            result_type = task.get('result_type')

            if result_type and result_type in result_type_endpoints:
                downloadable.append({
                    'task_run': task_run,
                    'result_type': result_type,
                    'task_result_id': task_run.get('task_result_id'),
                    'endpoint': result_type_endpoints[result_type],
                    'task_name': task.get('task_name'),
                })

        return downloadable

    def _get_all_cacheable_outputs(self):
        """
        Get all outputs that should be cached for all completed tasks.

        Maps result_type → list of (endpoint, file_extension) tuples.
        """
        task_output_endpoints = {
            "AnalysisReport": [
                ("report_pdf", "pdf"),
            ],
            "AnalysisIdatCNVP": [
                ("cnvp_gene_image", "jpg"),
                ("cnvp_bundle", "zip"),
            ],
            "AnalysisIdatPreprocess": [
                # TODO: unknown outputs
            ],
            "AnalysisIdatSex": [
                ("sex", "json"),
            ],
            "AnalysisIdatMGMT": [
                ("mgmt", "json"),
                ("mgmt_plot", "jpg"),
            ],
            "AnalysisIdatEPXqc": [
                ("epxqc", "json"),
                ("epxqc_plot", "jpg"),
            ],
            "AnalysisIdatClassifier": [
                ("classifier", "json"),
                ("classifier_summary", "json"),
            ],
        }

        cacheable = []
        if not self._task_runs:
            return cacheable

        for task_run in self._task_runs:
            if task_run.get('status') != 'complete':
                continue

            task = task_run.get('task', {})
            result_type = task.get('result_type')
            task_name = task.get('task_name', 'unknown')

            if result_type in task_output_endpoints:
                outputs = task_output_endpoints[result_type]
                if outputs:  # Only add if there are outputs to cache
                    cacheable.append({
                        'task_run': task_run,
                        'task_name': task_name,
                        'result_type': result_type,
                        'task_result_id': task_run.get('task_result_id'),
                        'outputs': outputs,  # List of (endpoint, extension)
                    })

        return cacheable

    def get_download_info(self):
        """
        Get list of all downloadable files with their metadata.

        Returns list of dicts with: result_type, task_name, task_result_id, endpoint
        """
        return self._get_downloadable_tasks()

    def get_file_name(self, download_info=None, sample_name=None):
        """
        Generate a file name for download based on workflow/sample info.
        If download_info provided, include task/result type in name.
        If sample_name provided, include it at the beginning.
        """
        parts = []

        if sample_name:
            parts.append(sample_name)

        parts.append(str(self._id))

        if download_info:
            parts.append(download_info.get('result_type', 'result'))
            if download_info.get('task_name'):
                parts.append(download_info['task_name'])

        return "_".join(parts) + ".pdf"

    def is_downloadable(self):
        """
        Check if this workflow run has any downloadable results (status complete + result_type in map).
        """
        return len(self._get_downloadable_tasks()) > 0

    def is_cached(self, workflow=None, sample_name=None):
        """
        Check if the workflow run results have been cached locally in ./cache directory.
        Checks if the run directory exists: cache/{workflow_name}_v{version}_{id}/{sample_name}_{run_id}/

        Args:
            workflow: workflow object to determine cache directory, or None
            sample_name: sample identifier for directory naming, or None

        Returns:
            True if cache directory exists and contains files, False otherwise
        """
        # Determine base cache directory
        if workflow:
            workflow_name = workflow._workflow_name_full.replace(" ", "_")
            cache_dir = f"cache/{workflow_name}__v{workflow._workflow_version}__{workflow._workflow_id}"
        else:
            cache_dir = "cache"

        # Build the run-specific directory path
        if sample_name:
            run_dir = os.path.join(cache_dir, f"{sample_name}_{self._id}")
        else:
            run_dir = os.path.join(cache_dir, str(self._id))

        # Check if directory exists and contains files
        if not os.path.isdir(run_dir):
            log.debug(f"[is_cached] Directory not found: {run_dir}")
            return False

        # Check if directory has any cached files
        try:
            has_files = len(os.listdir(run_dir)) > 0
            log.debug(f"[is_cached] {run_dir} - cached: {has_files}")
            return has_files
        except OSError as e:
            log.debug(f"[is_cached] Error checking {run_dir}: {str(e)}")
            return False

    def is_downloaded(self):
        """
        Check if the workflow run results have already been downloaded and cached locally.
        Deprecated: use is_cached() instead.
        """
        return self.is_cached()

    def get_classifier_result(self, workflow=None, sample_name=None):
        """
        Get the classifier result (second group level class and score) from the cached summary JSON.

        Args:
            workflow: workflow object to determine cache directory, or None
            sample_name: sample identifier for directory naming, or None

        Returns:
            dict with 'group' and 'score' keys, or None if not found/error
        """
        # Determine base cache directory
        if workflow:
            workflow_name = workflow._workflow_name_full.replace(" ", "_")
            cache_dir = f"cache/{workflow_name}__v{workflow._workflow_version}__{workflow._workflow_id}"
        else:
            cache_dir = "cache"

        # Build the run-specific directory path
        if sample_name:
            run_dir = os.path.join(cache_dir, f"{sample_name}_{self._id}")
        else:
            run_dir = os.path.join(cache_dir, str(self._id))

        # Try to find the summary JSON file
        try:
            for root, dirs, files in os.walk(run_dir):
                for file in files:
                    if file.endswith('_classifier_summary.json'):
                        summary_path = os.path.join(root, file)
                        with open(summary_path, 'r') as f:
                            data = json.load(f)

                        # Extract second group level (first member of first group)
                        if data.get('summary_hierarchical') and len(data['summary_hierarchical']) > 0:
                            first_group = data['summary_hierarchical'][0]
                            if first_group.get('members') and len(first_group['members']) > 0:
                                second_level = first_group['members'][0]
                                score = second_level.get('score', 'N/A')
                                # Round score to 2 decimals if it's a number
                                if isinstance(score, (int, float)):
                                    score = round(score, 2)
                                return {
                                    'group': second_level.get('group', 'N/A'),
                                    'score': score
                                }
                        return None
        except Exception as e:
            log.error(f"Error reading classifier result for run {self._id}: {str(e)}")
            return None

    def restart(self, app):
        """
        Restart a workflow run using the new Epignostix API.

        Args:
            app: EpignosticsPortalClient instance with authentication token

        Returns:
            True on success, False on failure
        """
        try:
            url = f"{app._SERVER_URL}/workflow_runs/restart/{self._id}"
            response = app.post(
                url,
                verify=True,
                timeout=30,
            )
            log.info(f"Restarted workflow run {self._id}")
            return True
        except requests.exceptions.RequestException as e:
            log.error(f"Could not restart workflow run {self._id}: {str(e)}")
            return False

    def download(self, app, download_info=None, output_dir=None, sample_name=None, workflow=None):
        """
        Download a result file from the API.

        Args:
            app: EpignosticsPortalClient instance with authentication token
            download_info: specific download_info dict from get_download_info(), or None for first downloadable
            output_dir: directory to save file, or None to use cache directory with workflow info
            sample_name: sample identifier to include in filename, or None
            workflow: workflow object (classifierWorkflowObj) to organize cache directory, or None

        Returns:
            Path to downloaded file, or None on failure
        """
        if not self._task_runs:
            log.warning(f"No task runs available for workflow run {self._id}")
            return None

        downloadables = self._get_downloadable_tasks()
        if not downloadables:
            log.warning(f"No downloadable results for workflow run {self._id}")
            return None

        if download_info is None:
            download_info = downloadables[0]

        endpoint = download_info.get('endpoint')
        task_result_id = download_info.get('task_result_id')

        url = f"{app._SERVER_URL}/{endpoint}/{self._id}/{task_result_id}"

        try:
            response = app.get(
                url,
                verify=True,
                timeout=30,
            )

            file_name = self.get_file_name(download_info, sample_name=sample_name)

            # Determine output directory
            if output_dir is None:
                if workflow:
                    # Use cache directory with workflow info (replace spaces with underscores)
                    workflow_name = workflow._workflow_name_full.replace(" ", "_")
                    cache_subdir = f"cache/{workflow_name}__v{workflow._workflow_version}__{workflow._workflow_id}"
                    output_dir = cache_subdir
                else:
                    # Fallback to current directory
                    output_dir = "."

            # Create directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)

            file_path = os.path.join(output_dir, file_name)

            with open(file_path, 'wb') as f:
                f.write(response.content)

            log.info(f"Downloaded {download_info['result_type']} to {file_path}")
            return file_path

        except requests.exceptions.RequestException as e:
            log.error(f"Failed to download {download_info['result_type']} from {url}: {str(e)}")
            return None
        except IOError as e:
            log.error(f"Failed to write file: {str(e)}")
            return None

    def cache_all(self, app, sample_name=None, workflow=None):
        """
        Download all outputs for all completed tasks and cache them in organized directories.

        Directory structure: ./cache/{workflow_name}_v{version}_{id}/{sample_name}_{run_id}/{task_name}/

        Args:
            app: EpignosticsPortalClient instance with authentication token
            sample_name: sample identifier for directory naming, or None
            workflow: workflow object to organize cache directory, or None

        Returns:
            List of successfully cached file paths, or empty list if nothing cached
        """
        if not self._task_runs:
            log.warning(f"No task runs available for workflow run {self._id}")
            return []

        cacheable = self._get_all_cacheable_outputs()
        if not cacheable:
            log.info(f"No cacheable outputs for workflow run {self._id}")
            return []

        cached_files = []

        # Determine base cache directory
        if workflow:
            workflow_name = workflow._workflow_name_full.replace(" ", "_")
            base_cache_dir = f"cache/{workflow_name}__v{workflow._workflow_version}__{workflow._workflow_id}"
        else:
            base_cache_dir = "cache"

        # Add sample and run info to directory
        if sample_name:
            run_subdir = f"{sample_name}_{self._id}"
        else:
            run_subdir = str(self._id)

        # Download all outputs
        for cache_entry in cacheable:
            task_name = cache_entry['task_name']
            task_result_id = cache_entry['task_result_id']
            result_type = cache_entry['result_type']
            outputs = cache_entry['outputs']
            task_run = cache_entry['task_run']

            # Extract timestamp from task_run (use updated_at if available, fallback to created_at)
            timestamp_str = task_run.get('updated_at') or task_run.get('created_at')
            file_mtime = None
            if timestamp_str:
                try:
                    # Parse ISO 8601 datetime and convert to Unix timestamp
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    file_mtime = dt.timestamp()
                except (ValueError, AttributeError):
                    log.warning(f"Could not parse timestamp {timestamp_str} for task {task_name}")

            # Create task-specific directory
            task_dir = os.path.join(base_cache_dir, run_subdir, task_name)
            os.makedirs(task_dir, exist_ok=True)

            # Download each output file for this task
            for endpoint, file_ext in outputs:
                try:
                    # Construct full endpoint path: analysis_idat/{endpoint_name}
                    full_endpoint = f"analysis_idat/{endpoint}"
                    url = f"{app._SERVER_URL}/{full_endpoint}/{self._id}/{task_result_id}"
                    response = app.get(
                        url,
                        verify=True,
                        timeout=30,
                    )

                    # Generate filename with task name and endpoint type
                    file_name = f"{task_name}_{endpoint}.{file_ext}"
                    file_path = os.path.join(task_dir, file_name)

                    # Format JSON prettily if it's a JSON file
                    if file_ext == 'json':
                        try:
                            json_data = response.json()
                            content = json.dumps(json_data, indent=2)
                            with open(file_path, 'w') as f:
                                f.write(content)
                        except (json.JSONDecodeError, ValueError):
                            with open(file_path, 'wb') as f:
                                f.write(response.content)
                    else:
                        with open(file_path, 'wb') as f:
                            f.write(response.content)

                    # Set file modification time to task's updated_at timestamp
                    if file_mtime:
                        os.utime(file_path, (file_mtime, file_mtime))
                        log.info(f"Cached {endpoint} ({result_type}) to {file_path} [timestamp: {timestamp_str}]")
                    else:
                        log.info(f"Cached {endpoint} ({result_type}) to {file_path}")

                    cached_files.append(file_path)

                    # Auto-extract ZIP bundles with timestamp preservation
                    if file_ext == 'zip':
                        try:
                            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                                zip_ref.extractall(task_dir)

                                # Preserve ZIP member timestamps on extracted files
                                for info in zip_ref.infolist():
                                    extracted_path = os.path.join(task_dir, info.filename)
                                    if os.path.exists(extracted_path):
                                        # Convert ZIP date_time tuple to timestamp
                                        date_time = info.date_time
                                        timestamp = datetime(*date_time).timestamp()
                                        os.utime(extracted_path, (timestamp, timestamp))

                            log.info(f"Extracted ZIP bundle {file_name} to {task_dir} (timestamps preserved)")
                            # Remove ZIP after successful extraction
                            os.remove(file_path)
                            log.info(f"Removed ZIP file {file_path}")
                        except zipfile.BadZipFile as e:
                            log.error(f"Invalid ZIP file {file_path}: {str(e)}")
                        except Exception as e:
                            log.error(f"Failed to extract ZIP {file_path}: {str(e)}")

                except requests.exceptions.RequestException as e:
                    log.error(f"Failed to cache {endpoint} from {url}: {str(e)}")
                except IOError as e:
                    log.error(f"Failed to write file {file_name}: {str(e)}")

        if cached_files:
            log.info(f"Successfully cached {len(cached_files)} files for workflow run {self._id}")
        return cached_files


class sample:
    _idat = None
    _id = None
    _name = None
    _created_at = None
    _updated_at = None# worthless, doesn't update as workflows are exectud or re-run
    _chip_type = None
    _extraction_type = None

    _ext = None
    _workflows = None
    _workflow_runs = None

    def __init__(self, s_idat, s_id, s_name, s_created_at, s_chip_type, s_extraction_type, s_updated_at=None):
        self._idat = s_idat
        self._id = s_id
        self._name = s_name
        self._created_at = s_created_at
        self._updated_at = s_updated_at
        self._chip_type = s_chip_type
        self._extraction_type = s_extraction_type
        self._workflows = {}
        self._workflow_runs = []
        self._workflows_loading = set()


    def get_workflow_runs_new(self, app):
        """
        Fetch workflow runs for this sample using the new Epignostix API.
        Creates workflow_run objects and stores them in _workflow_runs attribute.
        Also populates _workflows dict for template compatibility.
        Note: created_at and updated_at are only available after calling get_detailed_info().

        Args:
            app: EpignosticsPortalClient instance with authentication token
        """
        try:
            response = requests.get(
                f"{app._SERVER_URL}/workflow_runs/by_entity/{self._id}",
                headers={"Authorization": f"Bearer {app._response_token}"},
                params={"entity_type": "IlluminaMethylationSample"},
                verify=True,
            )
            response.raise_for_status()
            raw_runs = response.json()

            self._workflow_runs = []
            executed_workflow_ids = set()

            for run_data in raw_runs:
                run = workflow_run(
                    run_data['id'],
                    run_data['run_identifier'],
                    run_data['status'],
                    run_data['workflow_id'],
                    run_data['entity_id'],
                    run_data['creator_id'],
                    run_data.get('created_at'),
                    run_data.get('updated_at')
                )
                # Fetch detailed info (tasks) for this workflow run
                run.get_detailed_info(app)
                self._workflow_runs.append(run)
                executed_workflow_ids.add(run_data['workflow_id'])

            # Populate _workflows dict for template compatibility
            self._populate_workflows_dict(executed_workflow_ids)

            log.info(f"Retrieved {len(self._workflow_runs)} workflow runs for sample {self._id}")
        except requests.exceptions.RequestException as e:
            log.error(f"Could not get workflow runs for sample {self._id}: {str(e)}")
            self._workflow_runs = []
            self._populate_workflows_dict(set())

    def _populate_workflows_dict(self, executed_workflow_ids):
        """
        Populate _workflows dict for template compatibility with the old API format.
        Structure: {workflow_obj: {'status': 'available|done|unavailable', 'jobs': {}}}
        """
        self._workflows = {}

        # Mark workflows as available or done
        for workflow in classifierWorkflows:
            if workflow._workflow_id in executed_workflow_ids:
                self._workflows[workflow] = {'status': 'done', 'jobs': {}}
            else:
                self._workflows[workflow] = {'status': 'available', 'jobs': {}}

    def execute_workflow(self, app, workflow):
        """
        Execute a workflow for this sample using the new Epignostix API.

        Args:
            app: EpignosticsPortalClient instance with authentication token
            workflow: classifierWorkflowObj instance
        """
        try:
            url = f"{app._SERVER_URL}/illumina_methylation_sample/{self._id}/execute_workflow?workflow_id={workflow._workflow_id}"
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {app._response_token}",
                    "Content-Type": "application/json",
                },
                verify=True,
            )
            response.raise_for_status()
            log.info(f"Executed workflow {workflow._workflow_id} for sample {self._id}")
            self.get_workflow_runs_new(app)
            return True
        except requests.exceptions.RequestException as e:
            log.error(f"Could not execute workflow {workflow._workflow_id} for sample {self._id}: {str(e)}")
            return False

    def remove(self, app):
        """Delete sample from Epignostix server."""
        try:
            response = app._request(
                "DELETE",
                f"{app._SERVER_URL}/illumina_methylation_sample/{self._id}",
                verify=True,
            )
            log.info(f"Deleted sample {self._id}")
            return True
        except requests.exceptions.RequestException as e:
            log.error(f"Could not delete sample {self._id}: {str(e)}")
            return False




# most elegant way would be to have this class in four states:
# - uninitialized
# - credentials loaded (blocks everything except login)
# - logged in (blocks loading credentials)
# - error
class EpignosticsPortalClient:
    _user = None
    _pwd = None

    _response_token = None
    _samples = {}
    _n_samples = 0

    _SERVER_URL = "https://app.epignostix.com/api/v1"

    def __init__(self):
        self._samples = {}
        self._n_samples = 0

    def get_config(self):
        logging.info("Reading credentials")

        with open('config.txt', 'r') as fh:
            for line in fh:
                line = line.strip().split("=", 1)

                if len(line) == 2 and line[0] == "user":
                    self._user = line[1]

                elif len(line) == 2 and line[0] == "pwd":
                    self._pwd = line[1]

        if self._user is None or self._pwd is None:
            raise Exception("config error")

        return True

    def login(self):
        self.get_config()

        logging.info("Authenticating to the portal")

        try:
            response = requests.post(
                self._SERVER_URL + '/auth/token',
                headers={
                    "accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "",
                    "username": self._user,
                    "password": self._pwd,
                    "scope": "",
                    "client_id": "",
                    "client_secret": "",
                }
            )
            response.raise_for_status()
            self._response_token = response.json()['access_token']
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)

        # remove from memory, credentials have been used, response is enough
        self._user = None
        self._pwd = None

        logging.info("Authenticating to the portal: done")

        return True

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with automatic 401 re-login handling."""
        if "headers" not in kwargs:
            kwargs["headers"] = {}
        if "Authorization" not in kwargs["headers"]:
            kwargs["headers"]["Authorization"] = f"Bearer {self._response_token}"

        response = requests.request(method, url, **kwargs)

        # Handle token expiration
        if response.status_code == 401:
            log.warning("Token expired (401), re-logging in...")
            self.login()
            # Retry with new token
            kwargs["headers"]["Authorization"] = f"Bearer {self._response_token}"
            response = requests.request(method, url, **kwargs)

        response.raise_for_status()
        log.info(f"[API] {method} {url} → {response.status_code}")
        return response

    def get(self, url: str, **kwargs) -> requests.Response:
        """GET request with 401 handling."""
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        """POST request with 401 handling."""
        return self._request("POST", url, **kwargs)

    def get_workflows(self):
        """Fetch available workflows from the API and populate classifierWorkflows."""
        logging.info("Getting available workflows")

        try:
            response = self.get(
                self._SERVER_URL + '/workflows',
                params={"entity_type": "IlluminaMethylationSample"},
                verify=True,
            )
            response.raise_for_status()
            raw_workflows = response.json()

            # Clear and repopulate classifierWorkflows with data from the API
            classifierWorkflows._workflows.clear()

            for wf_data in raw_workflows:
                wf = classifierWorkflowObj(
                    wf_data['id'],
                    wf_data['name'],
                    wf_data['version'],
                    wf_data['description']
                )
                classifierWorkflows.add(wf)

            logging.info(f"Loaded {len(raw_workflows)} workflows from API")
            return classifierWorkflows.get_workflows()

        except requests.exceptions.RequestException as e:
            log.error(f"Could not get workflows: {str(e)}")
            return []

    def get_sample_count(self):
        logging.info("Getting number of samples listed")

        response = self.get(
            self._SERVER_URL + '/illumina_methylation_sample/count',
            params={"search_term": ""},
            verify=True,
        )
        response.raise_for_status()

        n = int(response.text.strip())
        logging.info("Getting number of samples listed: " + str(n))
        return n

    def update_samples(self, detailed=False):
        """
        Fetch all samples from the portal and store them locally.

        Field mapping (new API → old sample class):
          idat.uuid → s_idat
          id → s_id
          sample_identifier → s_name
          created_at → s_created_at
          idat.chip_type → s_chip_type
          given_extraction_type → s_extraction_type

        Args:
            detailed (bool): If True, fetch workflow runs for each sample.
                           If False (default), only fetch basic sample info.
        """
        n = self.get_sample_count()

        self._samples = {}
        self._n_samples = 0

        logging.info("Getting sample overview -- n=" + str(n))

        response = self.get(
            self._SERVER_URL + '/illumina_methylation_sample',
            params={"skip": 0, "limit": n, "search_term": ""},
            verify=True,
        )
        response.raise_for_status()

        raw_out = response.json()
        log.info("update_samples: n=" + str(len(raw_out)))

        i = 0
        for item in tqdm(raw_out):
            s = sample(
                item['idat']['uuid'],
                item['id'],
                item['sample_identifier'],
                item['created_at'],
                item['idat']['chip_type'],
                item['given_extraction_type'],
                item.get('updated_at')
            )

            if detailed:
                s.get_workflow_runs_new(self)

            self.add_sample(s)
            i += 1

            yield s

        if i != n:
            raise Exception(str(n) + " samples expected, only " + str(i) + " provided by the query")

    def update_samples_sparse(self):
        """
        Update sample list without refreshing samples that are already cached.
        Only fetches new samples that haven't been seen before.
        """
        n = self.get_sample_count()

        logging.info("Getting sample overview (sparse)")

        response = self.get(
            self._SERVER_URL + '/illumina_methylation_sample',
            params={"skip": 0, "limit": n, "search_term": ""},
            verify=True,
        )
        response.raise_for_status()

        raw_out = response.json()

        existing_samples = []
        new_samples = []

        for item in tqdm(raw_out):
            s = self.get_sample(item['id'], item['idat']['uuid'])
            if s is not None:
                s._updated_at = item.get('updated_at')
                existing_samples.append(s)
            else:
                s = sample(
                    item['idat']['uuid'],
                    item['id'],
                    item['sample_identifier'],
                    item['created_at'],
                    item['idat']['chip_type'],
                    item['given_extraction_type'],
                    item.get('updated_at')
                )
                new_samples.append(s)

        self._samples = {}
        self._n_samples = 0
        for s in existing_samples + new_samples:
            self.add_sample(s)

        if len(existing_samples) + len(new_samples) != n:
            raise Exception(str(n) + " samples expected, only " + str(len(existing_samples) + len(new_samples)) + " provided by the query")

        return n

    def add_sample(self, sample_s):
        """Add a sample to the local cache, keyed by sample ID."""
        sample_id = sample_s._id
        if sample_id in self._samples:
            log.warning(f"Duplicate sample ID: {sample_id}")

        self._samples[sample_id] = sample_s
        self._n_samples += 1

    def get_sample(self, sample_id, sample_idat=None):
        """Retrieve a specific sample by ID (idat parameter kept for backwards compatibility)."""
        return self._samples.get(sample_id)

    def get_samples(self):
        """Return all samples as a sorted list."""
        return list(self)

    def __iter__(self):
        """Iterate through all samples in reverse sorted order by ID."""
        for sample_id in sorted(self._samples.keys(), reverse=True):
            yield self._samples[sample_id]

    def upload_sample(
        self,
        idat_grn_path: str,
        idat_red_path: str,
        sample_identifier: str,
        workflow_id: int,
        given_chip_type: str = "ND",
        given_extraction_type: str = "ND",
        sex: str = "ND",
        keep_filename: bool = False,
        localisation: str = "",
        diagnosis: str = "",
        age: str = "",
        verbose: bool = False,
    ):
        """
        Upload a pair of IDAT files and start a workflow run.

        Returns dict with sample_id, uuid, workflow_run_id on success, None on failure.
        """
        url = f"{self._SERVER_URL}/illumina_methylation_sample"
        params = {
            "sample_identifier": sample_identifier,
            "given_chip_type": given_chip_type,
            "given_extraction_type": given_extraction_type,
            "sex": sex,
            "workflow_id": workflow_id,
            "keep_filename": str(keep_filename).lower(),
        }
        try:
            with open(idat_grn_path, "rb") as grn, open(idat_red_path, "rb") as red:
                files = {
                    "idat1": (os.path.basename(idat_grn_path), grn, "application/octet-stream"),
                    "idat2": (os.path.basename(idat_red_path), red, "application/octet-stream"),
                }
                data = {"localisation": localisation, "diagnosis": diagnosis, "age": age}
                response = self._request("PUT", url, params=params, files=files, data=data, verify=True)
            if verbose:
                print(f"HTTP {response.status_code}")
                print(response.text)
            result = response.json()
            log.info(f"Uploaded {sample_identifier}: sample_id={result['sample_id']}, workflow_run_id={result['workflow_run_id']}")
            return result
        except requests.exceptions.RequestException as e:
            log.error(f"Failed to upload {sample_identifier}: {e}")
            return None

    def __len__(self):
        """Return the total number of samples."""
        return self._n_samples


def is_valid_zipfile(zipfile):
    result = subprocess.run(['unzip', '-t', zipfile], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        
    return (result.returncode == 0)



