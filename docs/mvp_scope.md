# MVP Scope

## Objective

Build a Django REST Framework backend MVP that transforms a `.docx` containing bank deposit images into a final Excel file while preserving strict traceability and document order.

Primary flow:

1. Upload `.docx`
2. Extract embedded images in document order
3. Run OCR on each image
4. Convert OCR raw text into structured deposit data with LLM
5. Generate Excel output
6. Store basic process history

## What the MVP must include

- Endpoint to upload one `.docx`
- Extraction of internal images preserving the exact order in which they appear in the document
- Per-image traceability with sequence number, source file, OCR raw text, structured extraction, and observations
- OCR execution through a pluggable provider interface
- Structured extraction through a pluggable LLM provider interface
- Excel generation from structured records
- Basic persistence of processing runs and extracted deposits
- Validation/observation indicating whether the extracted deposit date belongs to the current month
- Download or retrieval of the generated Excel and processing summary

## What the MVP intentionally excludes

- Frontend
- Advanced authentication/authorization
- Background task queues such as Celery
- Cloud infrastructure and deployment architecture
- Multi-tenant design
- Complex human review workflows
- Selenium/browser automation
- Full replacement of every legacy utility before proving the end-to-end flow

## Functional rules to preserve

- `.docx` is the main input artifact
- Document order is strict and must survive extraction, OCR, parsing, persistence, and export
- Each deposit must keep traceability back to its source image and processing run
- Excel is the primary business output
- Human intervention should be minimized
- If the date is not in the current month, the record should not be discarded automatically; it should carry an observation
- The first success criterion is reliable `.docx -> Excel`

## Recommended MVP slices

### Slice 1

Upload `.docx`, extract ordered images, persist the run and extracted images metadata.

### Slice 2

Run OCR for each extracted image and persist raw text.

### Slice 3

Run LLM structuring, validate extracted fields, and persist observations.

### Slice 4

Generate Excel and expose result retrieval endpoints.

## Non-functional priorities

- Fast development over premature optimization
- Thin DRF views and orchestration in services
- Testability of parsing and extraction logic without HTTP
- Provider abstraction only where the project already has proven variability: OCR and LLM
- Documentation that matches the real migration path from the legacy codebase
