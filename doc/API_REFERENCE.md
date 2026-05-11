# Epignostix external WEB-API Reference

Base URL: "https://app.epignostix.com/api/v1"

## Overview

The Epignostix API provides access to Illumina methylation analysis samples, workflows, and execution results.

### Data Hierarchy

```
Sample
├─ Workflow 1 (available status)
│  └─ Workflow Run 1
│     ├─ Task Run 1
│     ├─ Task Run 2
│     └─ ...
├─ Workflow 2 (done status)
│  └─ Workflow Run 2
│     ├─ Task Run 1
│     └─ ...
└─ Workflow N (unavailable status)
```

**Key concepts:**
- **Sample**: An Illumina methylation IDAT file with metadata
- **Workflow**: A classifier/analysis pipeline that can be executed on samples
- **Workflow Run**: A single execution of a workflow on a sample
- **Task Run**: Individual tasks within a workflow run (preprocessing, classification, QC, etc.)

---

## 1. Authentication

### POST /api/v1/auth/token

OAuth2-style token endpoint. Returns a Bearer token for subsequent authenticated requests.

**Request:**
```
POST https://app.epignostix.com/api/v1/auth/token
Content-Type: application/x-www-form-urlencoded
```

**Body (form-encoded):**
```
grant_type=&username=user@example.com&password=secret&scope=&client_id=&client_secret=
```

*Note: Most fields are empty placeholders; only `username` and `password` are used.*

**Response (200):**
```json
{
  "access_token": "[a-zA-Z0-9]+...",
  "token_type": "bearer",
  "expires_in": 3600, # 1 hour
  "scope": ""
}
```

**Response (401/422):**
```json
{
  "detail": "Incorrect email or password"
}
```

### Using the token

All subsequent requests must include HTTP header:
```
Authorization: Bearer <access_token>
```

---

## 2. Samples

### GET /api/v1/illumina_methylation_sample

List samples with pagination and optional filtering.

**Query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | integer | 0 | Offset for pagination |
| `limit` | integer | 100 | Max number of records returned |
| `search_term` | string | `""` | Free-text filter; empty returns all |

**Response:**
```json
[
  {
    "id": "{sample_id}",
    "created_at": "2026-05-07T09:25:17.624165",
    "updated_at": "2026-05-07T09:25:17.624167",
    "sample_identifier": "TCGA-S9-A6WI-01A",
    "localisation": null,
    "diagnosis": null,
    "age": null,
    "given_chip_type": "ND",
    "given_extraction_type": "ND",
    "idat_id": "{idat_id}",
    "subject_id": "{subject_id}",
    "filename": "",
    "idat": {
      "uuid": "ebb4c2e0-c32b-517c-9933-6f9c3150e98b", # hash of sentrix id, algorithm or peper/salting still unknown
      "chip_type": "CHIP_450K_V1"
    }
  }
]
```

**Field reference:**
| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `id` | integer | no | Internal sample ID |
| `created_at` | ISO 8601 | no | Timestamp of upload |
| `updated_at` | ISO 8601 | no | Timestamp of last metadata modification |
| `sample_identifier` | string | no | User-visible sample name |
| `idat.uuid` | string (UUID) | no | Unique identifier of IDAT file |
| `idat.chip_type` | string | no | Detected chip type (e.g., `CHIP_450K_V1`) |
| `localisation` | string | yes | Anatomical localisation |
| `diagnosis` | string | yes | Clinical diagnosis |
| `age` | number | yes | Patient age |
| `given_chip_type` | string | no | Chip type as submitted (`ND` if not specified) |
| `given_extraction_type` | string | no | Extraction type as submitted |
| `idat_id` | integer | no | Foreign key to idat record |
| `subject_id` | integer | no | Foreign key to subject/patient record |
| `filename` | string | yes | Original filename |

⚠️ **Important:** `sample.updated_at` is NOT updated when workflow runs are executed. It only tracks changes to sample metadata. For workflow result caching, use `workflow_run.updated_at` instead (see Workflow Runs section).

### GET /api/v1/illumina_methylation_sample/count

Returns the total number of samples (plain text integer). Cheap operation — use for polling to detect changes.

**Response:**
```
Sample count: [0-9]+
```

---

## 3. Workflows

Workflows are loaded dynamically from the API and are global (not per-sample).

### Available workflow information

Each workflow has:
- `_workflow_id`: Integer ID (used in execute endpoint)
- `_workflow_name_full`: Full name (e.g., `epxCNS_v1_0_0_classifier`)
- `_workflow_name_short`: Short name for UI display
- `_workflow_version`: Version number (e.g., `1.0`)
- `_workflow_description`: Human-readable description

### Workflow status per sample

When fetching samples with workflow runs, each sample's workflow status is one of:
- `available`: Can be executed
- `done`: Has been executed at least once
- `unavailable`: Not available for this sample

---

## 4. Workflow Runs

⚠️ **IMPORTANT:** The following two endpoints must ALWAYS be fetched together for data consistency. See "Coupled endpoints" section below.

### GET /api/v1/workflow_runs/by_entity/{entity_id}?entity_type=IlluminaMethylationSample

Returns array of workflow run summaries for a sample with basic status.

**Response:**
```json
[
  {
    "run_identifier": "Workflow_id_{workflow_id}_entity_id_{sample_id}_user_id_{creator_id}",
    "status": "initialized",
    "workflow_id": "{workflow_id}",
    "entity_id": "{sample_id}",
    "creator_id": "{creator_id}",
    "id": "{run_id}"
  }
]
```

### GET /api/v1/workflow_runs/{run_id}

Returns full workflow run with nested `task_runs` array. Each task has its own status and timestamps.

**Response:**
```json
{
  "id": "{id}",
  "created_at": "2026-05-06T07:04:15.419479",
  "updated_at": "2026-05-06T07:04:15.419481",
  "run_identifier": "Workflow_id_15_entity_id_..._user_id_...",
  "status": "initialized",
  "workflow_id": "{workflow_id}",
  "entity_id": "{entity_id}",
  "creator_id": "{creator_id}",
  "task_runs": [
    {
      "id": "{task_run_id}",782,
      "created_at": "2026-05-06T07:04:15.967690",
      "updated_at": "2026-05-06T07:04:15.967693",
      "entity_id": "{entity_id}",
      "status": "complete",
      "task_id": "{task_id}",
      "task_result_id": "{task_result_id}",
      "task": {
        "task_name": "epxCNS_v1_0_0_sex",
        "task_version": "v1.0",
        "result_type": "AnalysisIdatSex"
      }
    },
    {
      "id": "{task_run_id}",785,
      "created_at": "2026-05-06T07:04:16.540576",
      "updated_at": "2026-05-06T07:04:16.540580",
      "entity_id": "{entity_id}",
      "status": "complete",
      "task_id": "{task_id}",
      "task_result_id": "{task_result_id}",
      "task": {
        "task_name": "epxCNS_v1_0_0_classifier",
        "task_version": "v1.0",
        "result_type": "AnalysisIdatClassifier"
      }
    },
    {
      "id": "{task_run_id}",780,
      "created_at": "2026-05-06T07:04:15.581289",
      "updated_at": "2026-05-06T07:04:15.581292",
      "entity_id": "{entity_id}",
      "status": "complete",
      "task_id": "{task_id}",
      "task_result_id": "{task_result_id}",
      "task": {
        "task_name": "epxCNS_v1_0_0_preprocess",
        "task_version": "v1.0",
        "result_type": "AnalysisIdatPreprocess"
      }
    },
    {
      "id": "{task_run_id}",783,
      "created_at": "2026-05-06T07:04:16.158617",
      "updated_at": "2026-05-06T07:04:16.158621",
      "entity_id": "{entity_id}",
      "status": "complete",
      "task_id": "{task_id}",
      "task_result_id": "{task_result_id}",
      "task": {
        "task_name": "epxCNS_v1_0_0_mgmt",
        "task_version": "v1.0",
        "result_type": "AnalysisIdatMGMT"
      }
    },
    {
      "id": "{task_run_id}",786,
      "created_at": "2026-05-06T07:04:16.746714",
      "updated_at": "2026-05-06T07:04:16.746717",
      "entity_id": "{entity_id}",
      "status": "complete",
      "task_id": "{task_id}",
      "task_result_id": "{task_result_id}",
      "task": {
        "task_name": "epxCNS_v1_0_0_report",
        "task_version": "v1.0",
        "result_type": "AnalysisReport"
      }
    },
    {
      "id": "{task_run_id}",781,
      "created_at": "2026-05-06T07:04:15.776639",
      "updated_at": "2026-05-06T07:04:15.776643",
      "entity_id": "{entity_id}",
      "status": "complete",
      "task_id": "{task_id}",
      "task_result_id": "{task_result_id}",
      "task": {
        "task_name": "epxCNS_v1_0_0_cnv_mnp",
        "task_version": "v1.0",
        "result_type": "AnalysisIdatCNVP"
      }
    },
    {
      "id": "{task_run_id}",784,
      "created_at": "2026-05-06T07:04:16.349307",
      "updated_at": "2026-05-06T07:04:16.349310",
      "entity_id": "{entity_id}",
      "status": "complete",
      "task_id": "{task_id}",
      "task_result_id": "{task_result_id}",
      "task": {
        "task_name": "epxCNS_v1_0_0_qc",
        "task_version": "v1.0",
        "result_type": "AnalysisIdatEPXqc"
      }
    }
  ]
}
```

### Workflow run fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | integer | Run ID (use in `/workflow_runs/{id}`) |
| `created_at` | ISO 8601 | When run was created |
| `updated_at` | ISO 8601 | When run was last updated |
| `run_identifier` | string | Human-readable: `Workflow_id_{wf_id}_entity_id_{entity_id}_user_id_{creator_id}` |
| `status` | string | One of: `initialized`, `running`, `complete`, `failed`, `error` |
| `workflow_id` | integer | Which classifier/workflow was run |
| `entity_id` | integer | Sample ID |
| `creator_id` | integer | User ID who submitted |
| `task_runs` | array | Only in detail response |

### Task run fields

Each object in `task_runs`:

| Field | Type | Notes |
|-------|------|-------|
| `id` | integer | Task run ID |
| `created_at` | ISO 8601 | When task started |
| `updated_at` | ISO 8601 | When task completed (for `complete` status) |
| `entity_id` | integer | Entity ID (may differ from run's entity_id) |
| `status` | string | One of: `initialized`, `running`, `complete`, `failed`, `error` |
| `task_id` | integer | Task definition ID |
| `task_result_id` | integer | Result ID (use in download endpoint) |
| `task.task_name` | string | Task name (e.g., `epxCNS_v1_0_0_classifier`) |
| `task.task_version` | string | Version (e.g., `v1.0`) |
| `task.result_type` | string | Result type for downloads (see table below) |

### Coupled endpoints requirement

⚠️ **IMPORTANT:** Always fetch both endpoints together:

1. **First:** `/workflow_runs/by_entity/{sample_id}` — get the list of runs with basic status
2. **Then:** `/workflow_runs/{run_id}` for each run — get detailed task status

**Status consistency check:** After fetching details, validate that `workflow_run.status` matches the derived status from `task_runs`:
- If ANY task is `running` → run status should be `running`
- If ANY task is `failed` or `error` → run status should be `failed`/`error`
- If ALL tasks are `complete` → run status should be `complete`
- If ANY task is `initialized` → run status should be `initialized`

### Caching strategy

⚠️ **IMPORTANT:** Neither `sample.updated_at` nor `workflow_run.updated_at` nor `task.updated_at` are updated when workflow runs are restarted or tasks are re-executed.

**What doesn't work:**
- ❌ Timestamp-based cache invalidation
- ❌ `sample.updated_at` — only tracks metadata changes
- ❌ `workflow_run.updated_at` — not updated on restart/re-execution
- ❌ `task.updated_at` — frozen at original execution time

**Recommended strategy:**
1. Poll `/workflow_runs/by_entity/{sample_id}` periodically
2. Track seen run IDs
3. If a new run ID appears → fetch details and cache
4. If a run ID's status changes → re-fetch and invalidate

---

## 5. Workflow Execution

### POST /api/v1/illumina_methylation_sample/{sample_id}/execute_workflow?workflow_id={workflow_id}

Execute a workflow for a sample.

**Request:**
```
POST https://app.epignostix.com/api/v1/illumina_methylation_sample/{sample_id}/execute_workflow?workflow_id=15
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Response:**
Returns HTTP 200 on success. Response body may be empty or contain status information (API behavior not fully documented).

**Expected behavior:**
- Workflow execution is queued asynchronously
- Use `/workflow_runs/by_entity/{sample_id}` to poll for the new run ID
- Refresh workflow runs after execution to show new run in UI

---

## 6. Workflow Run Management

### POST /api/v1/workflow_runs/restart/{run_id}

Restart a workflow run.

**Request:**
```
POST https://app.epignostix.com/api/v1/workflow_runs/restart/{workflow_run_id}
Authorization: Bearer <access_token>
```

**Response:**
Returns HTTP 200 on success.

**Expected behavior:**
- Same run ID is reused
- `status` is reset (typically to `initialized`)
- `updated_at` is NOT updated (see caching strategy above)
- Tasks may be re-executed or reset

---

## 7. Results Download

### GET /api/v1/analysis_idat/{endpoint}/{run_id}/{task_result_id}

Download result files for a task.

**Result types and endpoints:**

| result_type | task_name | endpoint | format | notes |
|---|---|---|---|---|
| AnalysisIdatPreprocess | epxCNS_v1_0_0_preprocess | (not documented) | ? | Preprocessing outputs |
| AnalysisIdatSex | epxCNS_v1_0_0_sex | `sex` | JSON | Sex classification |
| AnalysisIdatMGMT | epxCNS_v1_0_0_mgmt | `mgmt`, `mgmt_plot` | JSON, JPG | MGMT methylation status + plot |
| AnalysisIdatEPXqc | epxCNS_v1_0_0_qc | `epxqc`, `epxqc_plot` | JSON, JPG | QC metrics + plot |
| AnalysisIdatCNVP | epxCNS_v1_0_0_cnv_mnp | `cnvp_gene_image`, `cnvp_bundle` | JPG, ZIP | CNV plot + bundled data |
| AnalysisIdatClassifier | epxCNS_v1_0_0_classifier | `classifier`, `classifier_summary` | JSON | Classification + summary JSON |
| AnalysisReport | epxCNS_v1_0_0_report | `report_pdf` | PDF | Final analysis report |

**Example request (get classifier summary):**
```
GET https://app.epignostix.com/api/v1/analysis_idat/classifier_summary/{workflow_run_id}/{task_run_id}
Authorization: Bearer <access_token>
```

---

## Implementation Notes

### Python class mapping

| API Concept | Python Class | Location |
|---|---|---|
| Sample | `sample` | `pyepignostics/pyepignostics.py` |
| Workflow | `Workflow` | `pyepignostics/workflow.py` |
| Workflow Run | `workflow_run` | `pyepignostics/pyepignostics.py` |
| API Client | `EpignosticsPortalClient` | `pyepignostics/pyepignostics.py` |

