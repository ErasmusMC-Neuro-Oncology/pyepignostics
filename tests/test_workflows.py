#!/usr/bin/env python

"""
Tests for workflow management and classifierWorkflow objects.

Requires config.txt in the project root with:
    user=email@example.com
    pwd=yourpassword

Run:
    pytest tests/test_workflows.py
"""

import pathlib
import pytest
import logging

from pymnp.pymnp import mnpscrapNew
from pymnp.workflows import classifierWorkflowObj, classifierWorkflowsObj, classifierWorkflows

log = logging.getLogger(__name__)

CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.txt"

requires_config = pytest.mark.skipif(
    not CONFIG_PATH.exists(),
    reason="config.txt not found in project root"
)


class TestWorkflows:
    @requires_config
    def test_workflows_can_be_loaded(self):
        """Load workflows from API and verify they populate classifierWorkflows."""
        app = mnpscrapNew()
        app.login()
        app.get_workflows()

        # Verify classifierWorkflows is populated
        assert len(classifierWorkflows) > 0, "No workflows loaded"

        # Log loaded workflows
        for workflow in classifierWorkflows:
            print(f"  - ID {workflow._workflow_id}: {workflow._workflow_name_full} (v{workflow._workflow_version})")

    @requires_config
    def test_classifier_workflow_obj_type(self):
        """Verify loaded workflows are classifierWorkflowObj instances."""
        app = mnpscrapNew()
        app.login()
        app.get_workflows()

        for workflow in classifierWorkflows:
            assert isinstance(workflow, classifierWorkflowObj), \
                f"Expected classifierWorkflowObj, got {type(workflow)}"
            assert hasattr(workflow, '_workflow_id'), "Missing _workflow_id"
            assert hasattr(workflow, '_workflow_name_full'), "Missing _workflow_name_full"
            assert hasattr(workflow, '_workflow_version'), "Missing _workflow_version"

    @requires_config
    def test_classifier_workflows_obj_container(self):
        """Verify classifierWorkflows is a classifierWorkflowsObj instance."""
        app = mnpscrapNew()
        app.login()
        app.get_workflows()

        assert isinstance(classifierWorkflows, classifierWorkflowsObj), \
            f"Expected classifierWorkflowsObj, got {type(classifierWorkflows)}"

    @requires_config
    def test_workflows_greater_than_four(self):
        """Total number of workflows should be greater than 4."""
        app = mnpscrapNew()
        app.login()
        app.get_workflows()

        workflow_count = len(classifierWorkflows)
        log.info(f"Total workflows loaded: {workflow_count}")
        for workflow in classifierWorkflows:
            log.info(f"  - [{workflow._workflow_id}] {workflow._workflow_name_full} v{workflow._workflow_version}")

        assert workflow_count > 4, \
            f"Expected > 4 workflows, got {workflow_count}"

    @requires_config
    def test_workflow_retrieval_by_id(self):
        """Test that workflows can be retrieved by ID."""
        app = mnpscrapNew()
        app.login()
        app.get_workflows()

        # Get the first workflow
        first_workflow = next(iter(classifierWorkflows), None)
        assert first_workflow is not None, "No workflows available"

        # Retrieve it by ID
        retrieved = classifierWorkflows.get(first_workflow._workflow_id)
        assert retrieved is not None
        assert retrieved._workflow_id == first_workflow._workflow_id
        assert retrieved._workflow_name_full == first_workflow._workflow_name_full

    @requires_config
    def test_workflow_iteration(self):
        """Test that workflows can be iterated in sorted order by ID."""
        app = mnpscrapNew()
        app.login()
        app.get_workflows()

        workflow_ids = [w._workflow_id for w in classifierWorkflows]
        assert len(workflow_ids) > 0, "No workflows to iterate"
        assert workflow_ids == sorted(workflow_ids), "Workflows not sorted by ID"
