# Legacy to Django Migration Plan

## Legacy technical summary

The legacy project is not a generic OCR sandbox; it is a working CLI pipeline with four real layers:

- entrypoint CLI in [main.py](/home/gebert/ev_dirs/ev_OCR_ImagenATexto/main.py)
- batch orchestration in [src/pipeline.py](/home/gebert/ev_dirs/ev_OCR_ImagenATexto/src/pipeline.py)
- AI extraction in [src/extractor/llm_client.py](/home/gebert/ev_dirs/ev_OCR_ImagenATexto/src/extractor/llm_client.py) and [src/extractor/models.py](/home/gebert/ev_dirs/ev_OCR_ImagenATexto/src/extractor/models.py)
- support utilities in [src/config/config.py](/home/gebert/ev_dirs/ev_OCR_ImagenATexto/src/config/config.py), [src/utils/currency.py](/home/gebert/ev_dirs/ev_OCR_ImagenATexto/src/utils/currency.py), and [src/utils/state_manager.py](/home/gebert/ev_dirs/ev_OCR_ImagenATexto/src/utils/state_manager.py)

Important real findings from the code:

- The README describes a Tesseract/OpenCV pipeline, but the actual OCR implementation in [src/ocr/processor.py](/home/gebert/ev_dirs/ev_OCR_ImagenATexto/src/ocr/processor.py) uses Ollama vision over HTTP, not `pytesseract`.
- The legacy input is a directory of images, not a `.docx`.
- The batch pipeline processes images concurrently and yields them using `as_completed`, which breaks deterministic source order.
- Structured extraction already has useful prompt hardening and schema validation.
- Caching is implemented in SQLite by file path plus hash, outside Django models.
- Excel generation exists, but it is embedded inside the CLI entrypoint rather than isolated as a reusable service.

## Diagnosis

### A. Reusable almost directly

- `src/utils/currency.py`
  - Value: useful isolated utility with a narrow responsibility
  - Migration: move into `apps/common/utils/currency.py`

- `src/extractor/models.py`
  - Value: good starting point for extraction schema and validation rules
  - Migration: adapt into `apps/extraction/schemas.py` and business validators

### B. Reusable with refactor

- `src/extractor/llm_client.py`
  - Keep: prompt intent, retry loop, JSON cleanup, schema validation flow
  - Change: convert into provider adapter plus service layer, separate transport from prompt policy, stop instantiating directly inside worker code

- `src/pipeline.py`
  - Keep: high-level pipeline stages
  - Change: replace CLI concurrency-centric orchestration with ordered application service driven by persisted entities

- `main.py`
  - Keep: export intent and summary concepts
  - Change: remove CLI concerns, move Excel generation into a dedicated service, drop Rich/Typer UI behavior

- `src/config/config.py`
  - Keep: environment-based provider configuration idea
  - Change: merge into Django settings and provider-specific settings modules

### C. Should not be migrated as-is

- `src/ocr/processor.py`
  - Reason: name and docs are misleading; it claims OCR processor/Tesseract but actually performs HTTP calls to Ollama vision
  - Action: replace with explicit OCR provider adapters and a service interface

- `src/utils/state_manager.py`
  - Reason: external SQLite cache duplicates responsibilities that Django models should own for traceability and history
  - Action: replace with persistence in Django models; optionally reintroduce hash-based deduplication later

- `test_vision.py`
  - Reason: exploratory script, not production code
  - Action: keep only as behavioral reference for prompts if needed

- output and logs folders
  - Reason: run artifacts should move under Django-managed media storage and DB records

### D. Missing pieces required for Django MVP

- `.docx` parser that preserves exact image order
- DRF endpoints for upload and result retrieval
- Django models for processing history and traceability
- Storage policy for uploaded files and generated exports
- Business rule service for date observations
- Tests for strict ordering and `.docx -> Excel` flow

## Legacy -> Django mapping

| Legacy module | Current purpose | Django destination | Recommended action | Justification |
| --- | --- | --- | --- | --- |
| `main.py` | CLI entrypoint, batch summary, export calls | `apps/api/views.py` and `apps/processing/services/excel_exporter.py` | Refactorizar | Keep export logic intent, remove CLI/UI concerns |
| `src/pipeline.py` | End-to-end orchestration for image folders | `apps/processing/services/orchestrator.py` | Refactorizar | Workflow is useful, but current concurrency breaks strict order |
| `src/extractor/llm_client.py` | LLM call, retries, prompt, schema validation | `apps/extraction/providers/llm/ollama_text.py` and `apps/extraction/services/structuring_service.py` | Refactorizar | Valuable extraction strategy, but it needs provider boundaries and cleaner injection |
| `src/extractor/models.py` | Pydantic schema and validators | `apps/extraction/schemas.py` and `apps/extraction/services/validators.py` | Reutilizar con ajustes | Strong base for structured output validation |
| `src/utils/currency.py` | Monetary normalization | `apps/common/utils/currency.py` | Reutilizar | Small, isolated, and directly valuable |
| `src/config/config.py` | `.env` settings for legacy runtime | Django settings plus provider config helpers | Refactorizar | Useful settings inventory, but Django should own configuration |
| `src/ocr/processor.py` | OCR via Ollama vision HTTP | `apps/extraction/providers/ocr/ollama_vision.py` | Reemplazar | Keep provider concept, but not the ambiguous current shape |
| `src/utils/state_manager.py` | SQLite cache by file hash | Django models and optional future dedupe service | Reemplazar | Traceability and history belong in the main DB |
| `test_vision.py` | Manual prompt experiments | `tests` reference only, not product code | Posponer | Useful as a note, not as migration target |
| `output/*` | Batch artifacts | Django media storage + DB metadata | Reemplazar | Output should be tied to a `ProcessRun` |
| `logs/*` | File logging | Django logging config | Refactorizar | Keep observability, change integration point |

## Technical risks

### 1. Strict order is currently unsolved in the legacy approach

The biggest migration risk is assuming the existing batch pipeline preserves order. It does not. The Django design must attach a `sequence_index` from document extraction time and use it everywhere.

### 2. The legacy OCR story is inconsistent

Documentation says Tesseract/OpenCV, but the code uses Ollama vision. This matters because local setup, latency, error handling, and future cloud switching depend on the real provider model, not the README.

### 3. Legacy cache cannot become the source of truth

The SQLite cache stores results by file path and hash, which is fine for a CLI but weak for auditability across uploaded `.docx` files. Migrating it directly would create a second persistence model with overlapping responsibilities.

### 4. The current extraction schema is useful but not complete for business observations

There is no persisted concept of record-level observation, current-month validation, or end-to-end process status. Django models must introduce these explicitly.

### 5. The input model changes from image folder to `.docx`

This is not a cosmetic change. The migration must add a new extraction stage before OCR and validate that duplicate image names or embedded media ordering do not corrupt traceability.

## Recommended implementation order for Round 2

1. Create the first Django apps actually needed: `api`, `documents`, `processing`, `extraction`.
2. Implement `.docx` image extraction with deterministic ordering and tests.
3. Create `ProcessRun`, `SourceImage`, and `ExtractedDeposit` models.
4. Move schema validation and currency parsing from legacy into Django modules.
5. Implement OCR and LLM provider interfaces with Ollama adapters.
6. Build the first end-to-end service for `.docx -> persisted records`.
7. Add Excel generation and a minimal upload/result API.

## Round 2 priority list

- Priority 1: ordered `.docx` extraction and persistence
- Priority 2: extraction schemas, validators, and domain models
- Priority 3: OCR and LLM adapters behind provider interfaces
- Priority 4: orchestration service for the full processing flow
- Priority 5: Excel export and result retrieval endpoint
