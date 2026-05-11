#!/usr/bin/env python

"""
Tests for authentication via EpignosticsPortalClient against the Epignostix portal.

Requires config.txt in the project root with:
    user=email@example.com
    pwd=yourpassword

Run:
    pytest tests/test_login.py
"""

import pathlib
import pytest
import requests
import os
import tempfile

from pyepignostics.epignostics import EpignosticsPortalClient

CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.txt"

requires_config = pytest.mark.skipif(
    not CONFIG_PATH.exists(),
    reason="config.txt not found in project root"
)


class _EpignosticsPortalClientWithCreds(EpignosticsPortalClient):
    """Test-only subclass that injects credentials instead of reading config.txt."""
    def __init__(self, username, password):
        self._user = username
        self._pwd = password

    def get_config(self):
        pass


class TestLogin:
    def test_login_endpoint_reachable(self, server_url):
        """Auth endpoint should respond (not a connection error)."""
        url = f"{server_url}/auth/token"
        try:
            response = requests.post(url, data={}, verify=True, timeout=10)
        except requests.exceptions.ConnectionError:
            pytest.fail("Could not reach the portal auth endpoint.")
        assert response.status_code is not None

    @requires_config
    def test_login_succeeds(self):
        """login() must return True and store a non-empty token."""
        app = EpignosticsPortalClient()
        result = app.login()
        assert result is True
        assert app._response_token, "Expected a non-empty access_token after login"

    @requires_config
    def test_credentials_cleared_after_login(self):
        """Credentials must be wiped from memory once login completes."""
        app = EpignosticsPortalClient()
        app.login()
        assert app._user is None
        assert app._pwd is None

    def test_login_with_wrong_password(self):
        """Wrong password must raise SystemExit (non-200 response)."""
        app = _EpignosticsPortalClientWithCreds("user@example.com", "wrong-password-12345")
        with pytest.raises((SystemExit, Exception)):
            app.login()

    def test_login_with_wrong_username(self):
        """Non-existent user must raise SystemExit (non-200 response)."""
        app = _EpignosticsPortalClientWithCreds("nonexistent_xyz_404@example.invalid", "irrelevant")
        with pytest.raises((SystemExit, Exception)):
            app.login()

    @requires_config
    def test_get_sample_count(self):
        """get_sample_count() must return a non-negative integer and print it."""
        app = EpignosticsPortalClient()
        app.login()
        n = app.get_sample_count()
        assert isinstance(n, int)
        assert n >= 0
        print(f"\nSample count: {n}")

    @requires_config
    def test_update_samples_without_details(self):
        """update_samples(detailed=False) must fetch only basic sample info."""
        app = EpignosticsPortalClient()
        app.login()

        samples_fetched = []
        for s in app.update_samples(detailed=False):
            samples_fetched.append(s)

        assert len(samples_fetched) > 0, "Expected at least one sample"
        assert app._n_samples == len(samples_fetched)

        print(f"\nFetched {app._n_samples} samples (without workflow runs):")
        for s in samples_fetched[:5]:  # Print first 5
            print(f"  - {s._idat[:8]}... (ID: {s._id}) — {s._name}")
        if len(samples_fetched) > 5:
            print(f"  ... and {len(samples_fetched) - 5} more")

    @requires_config
    def test_update_samples_with_details(self):
        """update_samples(detailed=True) must fetch samples with workflow runs."""
        app = EpignosticsPortalClient()
        app.login()

        samples_fetched = []
        for s in app.update_samples(detailed=True):
            samples_fetched.append(s)

        assert len(samples_fetched) > 0, "Expected at least one sample"
        assert app._n_samples == len(samples_fetched)

        print(f"\nFetched {app._n_samples} samples (with workflow runs):")
        for s in samples_fetched[:5]:  # Print first 5
            print(f"\n  - {s._idat[:8]}... (ID: {s._id}) — {s._name}")
            if s._workflow_runs:
                for run in s._workflow_runs:
                    print(f"      • {run._run_identifier} (status: {run._status})")
            else:
                print(f"      (no workflow runs)")
        if len(samples_fetched) > 5:
            print(f"\n  ... and {len(samples_fetched) - 5} more samples")

    @requires_config
    def test_get_workflows(self):
        """get_workflows() must fetch and populate classifierWorkflows from API."""
        from pyepignostics.epignostics import classifierWorkflows

        app = EpignosticsPortalClient()
        app.login()

        # Clear workflows first to ensure we're testing the fetch
        initial_count = len(classifierWorkflows)

        # Fetch workflows from API
        workflows = app.get_workflows()

        assert len(workflows) > 0, "Expected at least one workflow from API"
        assert len(classifierWorkflows) > 0, "Expected classifierWorkflows to be populated"

        print(f"\nFetched {len(workflows)} workflows from API:")
        for wf in workflows:
            print(f"  • ID {wf._workflow_id}: {wf._workflow_name_full}")
            print(f"    Version: {wf._workflow_version}")
            print(f"    Description: {wf._workflow_description}")
            print(f"    Short name: {wf._workflow_name_short}")

    @requires_config
    def test_workflow_run_details(self):
        """workflow_run.get_detailed_info() must fetch task runs for a workflow run."""
        app = EpignosticsPortalClient()
        app.login()

        # Fetch one sample with workflow runs
        samples_fetched = []
        for s in app.update_samples(detailed=True):
            samples_fetched.append(s)
            if len(samples_fetched) >= 1:
                break

        assert len(samples_fetched) > 0, "Expected at least one sample"
        sample = samples_fetched[0]

        if not sample._workflow_runs:
            pytest.skip("Sample has no workflow runs to test")

        # Get detailed info for first workflow run
        run = sample._workflow_runs[0]
        run.get_detailed_info(app)

        assert run._task_runs is not None, "Expected task_runs to be populated"
        print(f"\nWorkflow run {run._run_identifier} has {len(run._task_runs)} tasks:")
        for task in run._task_runs:
            print(f"  • {task['task']['task_name']} v{task['task']['task_version']} — {task['status']}")

    @requires_config
    def test_token_can_reach_samples_endpoint(self, server_url):
        """Token obtained via EpignosticsPortalClient must allow an authenticated request."""
        app = EpignosticsPortalClient()
        app.login()

        headers = {"Authorization": f"Bearer {app._response_token}"}
        r = requests.get(
            f"{server_url}/illumina_methylation_sample",
            headers=headers,
            params={"skip": 0, "limit": 1},
            verify=True,
            timeout=15,
        )
        assert r.status_code == 200, (
            f"Authenticated request failed: {r.status_code} {r.text}"
        )

    @requires_config
    def test_download_report_from_completed_task(self):
        """Download report PDF from a sample with a completed workflow run task."""
        app = EpignosticsPortalClient()
        app.login()

        # Fetch samples with workflow runs
        sample_with_downloadable = None
        for s in app.update_samples(detailed=True):
            if s._workflow_runs:
                for run in s._workflow_runs:
                    # Check if run has downloadable results
                    if run.is_downloadable():
                        sample_with_downloadable = s
                        break
            if sample_with_downloadable:
                break

        if not sample_with_downloadable:
            pytest.skip("No sample with downloadable workflow run found")

        # Get the first downloadable run
        downloadable_run = None
        for run in sample_with_downloadable._workflow_runs:
            if run.is_downloadable():
                downloadable_run = run
                break

        assert downloadable_run is not None, "Should have found a downloadable run"

        # Get download info
        download_infos = downloadable_run.get_download_info()
        assert len(download_infos) > 0, "Should have at least one downloadable file"
        download_info = download_infos[0]

        # Construct the URL that will be downloaded
        endpoint = download_info.get('endpoint')
        task_result_id = download_info.get('task_result_id')
        download_url = f"{app._SERVER_URL}/{endpoint}/{downloadable_run._id}/{task_result_id}"

        # Get the filename that will be saved
        filename = downloadable_run.get_file_name(download_info, sample_name=sample_with_downloadable._name)

        # Get workflow object for cache directory organization
        from pyepignostics.epignostics import classifierWorkflows
        try:
            workflow = classifierWorkflows.get(downloadable_run._workflow_id)
        except:
            workflow = None

        # Download to cache directory with workflow info
        file_path = downloadable_run.download(
            app,
            output_dir=None,  # Use default cache directory with workflow info
            sample_name=sample_with_downloadable._name,
            workflow=workflow
        )

        assert file_path is not None, "download() should return a file path"
        assert os.path.exists(file_path), f"Downloaded file should exist at {file_path}"

        # Verify file size is reasonable (PDF files should have content)
        file_size = os.path.getsize(file_path)
        assert file_size > 100, f"Downloaded file too small ({file_size} bytes), likely not a real PDF"

        # Get absolute path for display
        abs_file_path = os.path.abspath(file_path)

        print(f"\nSuccessfully downloaded report:")
        print(f"  Sample: {sample_with_downloadable._idat[:8]}... (ID: {sample_with_downloadable._id})")
        print(f"  Workflow run: {downloadable_run._run_identifier}")
        print(f"  Download URL: {download_url}")
        print(f"  Filename: {filename}")
        print(f"  Full path: {abs_file_path}")
        print(f"  File size: {file_size} bytes")
