# Current Architecture

## System overview

The project is a modular monolith built with Django + Django REST Framework, plus a separate React/Vite frontend.

End-to-end flow:

1. Frontend uploads one `.docx`
2. Backend extracts embedded images in document order
3. A `ProcessRun` and ordered `SourceImage` records are created
4. Processing starts in sync or in-process async mode depending on `PROCESS_JOBS_ASYNC`
5. Each image goes through OCR, LLM structuring, validation, and persistence
6. Results are reviewed in the frontend
7. Manual corrections can be persisted back to the backend
8. Excel export is generated from persisted deposits, including saved corrections

## Backend modules

- `apps.api`: REST endpoints, serializers, error envelope
- `apps.documents`: `.docx` upload and image extraction
- `apps.extraction`: OCR, LLM, schema validation, image validation
- `apps.processing`: run models, orchestration, manual corrections, Excel export
- `apps.common`: request id middleware and shared utilities

## Main data model

### `ProcessRun`

- Stores the uploaded source document
- Tracks status: `uploaded`, `processing`, `completed`, `completed_with_errors`, `failed`
- Stores totals, timestamps, export file and provider snapshot

### `SourceImage`

- One row per image extracted from the `.docx`
- Preserves `sequence_index`
- Stores OCR status, raw text, provider and per-image errors

### `ExtractedDeposit`

- Structured result linked to both `ProcessRun` and `SourceImage`
- Stores editable business fields:
  - `fecha_consignacion`
  - `hora_consignacion`
  - `referencia`
  - `valor`
- Stores derived observations and current-month flag

### `ExtractionLog`

- Technical traceability per run and per image
- Includes OCR/LLM stages, raw text and error notes

## Processing model

`POST /api/jobs/{id}/process/` behaves in one of two modes:

- `PROCESS_JOBS_ASYNC=1`: prepares the job, marks it as `processing`, and starts an in-process background thread
- `PROCESS_JOBS_ASYNC=0`: runs the job inline inside the request, useful for deterministic tests

The async mode is intentionally lightweight and demo-friendly. It is not a distributed queue and should be presented as an MVP background execution mechanism, not as production job infrastructure.

## Manual corrections

The frontend results table now edits persisted `ExtractedDeposit` fields instead of local-only placeholders.

Endpoint:

- `PATCH /api/jobs/{id}/deposits/`

Payload:

```json
{
  "items": [
    {
      "id": 12,
      "fecha_consignacion": "22/04/2026",
      "hora_consignacion": "15:45",
      "referencia": "REF999",
      "valor": "175000"
    }
  ]
}
```

Effects:

- validates the corrected values
- persists them on `ExtractedDeposit`
- recomputes observations
- updates `structured_payload`
- makes the changes visible after refresh
- ensures Excel export uses the corrected values

## Security baseline

This project keeps a presentation-oriented security baseline:

- `API_KEY` protects sensitive write actions when configured
- `DJANGO_SECRET_KEY` is required when `DJANGO_DEBUG=0`
- `API_KEY` is required when `DJANGO_DEBUG=0`
- allowed hosts and CORS defaults are limited to local development hosts
- unhandled API exceptions return a generic JSON 500 envelope

This is still not enterprise security and should be presented honestly as an MVP hardening pass.

## Known limitations

- Async processing is in-process, not queue-based
- SQLite is used for local/demo persistence
- API key auth is minimal and there are no user accounts or roles
- The “assistant” panel in the frontend is guidance UX, not a real backend AI integration
