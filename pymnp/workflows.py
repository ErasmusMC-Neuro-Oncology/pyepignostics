#!/usr/bin/env python

"""Workflow and classifier management."""


class classifierWorkflowObj:
    """Represents a single workflow classifier."""
    _workflow_id = None
    _workflow_name_full = None
    _workflow_name_short = None
    _workflow_version = None
    _workflow_description = None

    def __init__(self, cw_id, cw_name, cw_version, cw_description):
        self._workflow_id = cw_id
        self._workflow_name_full = cw_name
        self._workflow_name_short = cw_name.replace("_classifier","").replace("_report","").replace("_research","-R").replace("_sample","-S")
        self._workflow_version = cw_version
        self._workflow_description = cw_description


class classifierWorkflowsObj:
    """Registry of available workflows."""
    _map = {}

    def add(self, c):
        self._map[c._workflow_id] = c

    def get(self, w_id):
        if not w_id in self._map:
            raise Exception("unknown workflow: " + str(w_id))
        else:
            return self._map[w_id]

    def __iter__(self):
        for key in sorted(self._map.keys()):
            yield self._map[key]

    def __len__(self):
        return len(self._map)

    def get_workflows(self):
        out = []

        for _ in self:
            out.append(_)

        return out


classifierWorkflows = classifierWorkflowsObj()
# Workflows are now loaded dynamically from the API via mnpscrapNew.get_workflows()
