# Initial Architecture

## Current baseline

The current Django repository contains only the default project skeleton in [MCP_back/settings.py](/home/gebert/djang-project/backend-diplo-final/MCP_back/settings.py) and [MCP_back/urls.py](/home/gebert/djang-project/backend-diplo-final/MCP_back/urls.py). There is no domain modeling or application structure yet.

The legacy project at `/home/gebert/ev_dirs/ev_OCR_ImagenATexto` already contains reusable logic in `src/`, but it is centered on a CLI pipeline for folders of images, not `.docx` uploads.

## Key architectural decisions

### 1. Use a modular monolith

One Django project with a few clear apps is the right level for this MVP. Microservices would add coordination cost without solving a current problem.

### 2. Keep views thin

DRF views should validate request shape, call orchestration services, and return persisted results. OCR, LLM parsing, document extraction, and Excel generation should live in service modules.

### 3. Separate domain workflow from provider integrations

The project needs future flexibility to switch between local and cloud models. The clean boundary is:

- domain/application services orchestrate the workflow
- provider adapters implement OCR and LLM calls

### 4. Persist traceability as first-class data

Strict order and auditability are core business rules, so they must be represented in the database rather than inferred from filenames or transient directories.

### 5. Do not copy the legacy concurrency model as-is

The legacy pipeline uses `ProcessPoolExecutor` with `as_completed` in [src/pipeline.py](/home/gebert/ev_dirs/ev_OCR_ImagenATexto/src/pipeline.py), which returns results in completion order rather than source order. That is incompatible with the MVP requirement of strict document ordering.

## Proposed project tree

```text
backend-diplo-final/
├── manage.py
├── MCP_back/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── api/
│   │   ├── urls.py
│   │   └── views.py
│   ├── processing/
│   │   ├── models.py
│   │   ├── services/
│   │   │   ├── process_docx.py
│   │   │   ├── orchestrator.py
│   │   │   ├── observations.py
│   │   │   └── excel_exporter.py
│   │   ├── selectors.py
│   │   └── admin.py
│   ├── documents/
│   │   ├── services/
│   │   │   ├── docx_image_extractor.py
│   │   │   └── storage.py
│   │   └── tests/
│   ├── extraction/
│   │   ├── services/
│   │   │   ├── ocr_service.py
│   │   │   ├── structuring_service.py
│   │   │   └── validators.py
│   │   ├── providers/
│   │   │   ├── ocr/
│   │   │   │   ├── base.py
│   │   │   │   └── ollama_vision.py
│   │   │   └── llm/
│   │   │       ├── base.py
│   │   │       └── ollama_text.py
│   │   └── schemas.py
│   └── common/
│       ├── settings.py
│       └── utils/
│           └── currency.py
└── docs/
    ├── mvp_scope.md
    ├── architecture.md
    └── migration_plan.md
```

## Proposed apps

### `apps.api`

Responsibility:

- REST endpoints
- request/response serializers
- API routing

Reason:

Keeps HTTP concerns separate from business workflow.

### `apps.documents`

Responsibility:

- receiving uploaded `.docx`
- extracting embedded images in order
- assigning stable sequence numbers
- storing source artifacts if needed

Reason:

The biggest new requirement compared with the legacy system is `.docx` handling. This deserves a dedicated boundary.

### `apps.extraction`

Responsibility:

- OCR execution
- LLM-based structuring
- validation of extracted fields
- provider abstraction for OCR and LLM engines

Reason:

This is where most reusable legacy logic lives, but it must be reorganized around services instead of CLI code.

### `apps.processing`

Responsibility:

- process run model
- extracted item model
- orchestration service for the end-to-end flow
- Excel export
- observations such as current-month validation

Reason:

This is the business workflow app that coordinates the others and stores the audit trail.

## Proposed domain models

### `ProcessRun`

- `id`
- `source_docx`
- `original_filename`
- `status` (`pending`, `processing`, `completed`, `failed`)
- `started_at`
- `finished_at`
- `total_images`
- `total_records`
- `excel_file`
- `error_message`
- `provider_config_snapshot` optional JSON

### `SourceImage`

- `id`
- `process_run`
- `sequence_index`
- `image_file`
- `source_name`
- `content_hash`
- `ocr_status`
- `ocr_raw_text`
- `ocr_provider`

### `ExtractedDeposit`

- `id`
- `process_run`
- `source_image`
- `sequence_index`
- `fecha_consignacion`
- `hora_consignacion`
- `referencia`
- `valor`
- `is_current_month`
- `observations`
- `structured_payload` optional JSON

## Suggested processing flow

1. API receives `.docx`
2. `documents.docx_image_extractor` extracts images in exact document order
3. `processing.orchestrator` creates `ProcessRun` and `SourceImage` records
4. For each ordered image:
   - `extraction.ocr_service` obtains raw text
   - `extraction.structuring_service` converts raw text to structured records
   - `extraction.validators` applies schema and business validation
   - `processing.observations` marks date-related observations
5. `processing.excel_exporter` builds the final workbook
6. `ProcessRun` is marked completed or failed

## Why not create all Django apps in this round

The repository is still at the analysis stage. Creating a lot of empty Django apps now would produce scaffolding without validated implementation boundaries. For this round, the documentation is the highest-value artifact. In Round 2, we should create only the apps that are immediately used by the first vertical slice.
