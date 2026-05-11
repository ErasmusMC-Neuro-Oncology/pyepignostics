#!/usr/bin/env python

"""Workflow and classifier management."""

from typing import Dict, List, Iterator


class Workflow:
    """Represents a single workflow classifier."""

    def __init__(self, workflow_id: int, name_full: str, version: str, description: str):
        self.id = workflow_id
        self.name_full = name_full
        self.version = version
        self.description = description

    @property
    def name_short(self) -> str:
        """Short name for UI display, derived from full name."""
        return (
            self.name_full
            .replace("_classifier", "")
            .replace("_report", "")
            .replace("_research", "-R")
            .replace("_sample", "-S")
        )

    # Backwards compatibility aliases for old attribute names
    @property
    def _workflow_id(self) -> int:
        """Backwards compatibility: old name for id."""
        return self.id

    @property
    def _workflow_name_full(self) -> str:
        """Backwards compatibility: old name for name_full."""
        return self.name_full

    @property
    def _workflow_name_short(self) -> str:
        """Backwards compatibility: old name for name_short."""
        return self.name_short

    @property
    def _workflow_version(self) -> str:
        """Backwards compatibility: old name for version."""
        return self.version

    @property
    def _workflow_description(self) -> str:
        """Backwards compatibility: old name for description."""
        return self.description

    def __repr__(self) -> str:
        return f"Workflow(id={self.id}, name='{self.name_full}', version={self.version})"

    def __str__(self) -> str:
        return f"{self.name_short} (v{self.version})"


class WorkflowRegistry:
    """Registry of available workflows."""

    def __init__(self):
        self._workflows: Dict[int, Workflow] = {}

    def add(self, workflow: Workflow) -> None:
        """Add a workflow to the registry."""
        self._workflows[workflow.id] = workflow

    def get(self, workflow_id: int) -> Workflow:
        """Get a workflow by ID."""
        if workflow_id not in self._workflows:
            raise KeyError(f"Unknown workflow: {workflow_id}")
        return self._workflows[workflow_id]

    def __iter__(self) -> Iterator[Workflow]:
        """Iterate over workflows in sorted order by ID."""
        for workflow_id in sorted(self._workflows.keys()):
            yield self._workflows[workflow_id]

    def __len__(self) -> int:
        """Number of workflows in registry."""
        return len(self._workflows)

    def get_workflows(self) -> List[Workflow]:
        """Return all workflows as a list."""
        return list(self)

    def __repr__(self) -> str:
        return f"WorkflowRegistry({len(self)} workflows)"

    def __str__(self) -> str:
        return f"Registry with {len(self)} workflows"


# Legacy aliases for backwards compatibility
classifierWorkflowObj = Workflow
classifierWorkflowsObj = WorkflowRegistry

# Global registry instance
# Workflows are loaded dynamically from the API via EpignosticsPortalClient.get_workflows()
classifierWorkflows = WorkflowRegistry()
