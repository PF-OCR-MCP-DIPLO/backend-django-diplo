# Demo Runbook

## Local environment

### Backend

Required environment variables for local demo:

```bash
cp .env.example .env
```

Important values:

- `DJANGO_DEBUG=1`
- `DJANGO_SECRET_KEY=change-me-for-your-local-env`
- `API_KEY=dev`
- `PROCESS_JOBS_ASYNC=1`
- `STUB_PROVIDERS=1` for stable demo without external OCR/LLM dependencies

### Frontend

```bash
cp .env.example .env
```

Important values:

- `VITE_API_BASE_URL=http://localhost:8000/api`
- `VITE_API_KEY=dev`

## Run locally

### Backend

```bash
source venv/bin/activate
python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
npm install
npm run dev
```

## Main endpoints

- `GET /api/health/`
- `POST /api/documents/upload/`
- `GET /api/jobs/`
- `GET /api/jobs/{id}/`
- `POST /api/jobs/{id}/process/`
- `PATCH /api/jobs/{id}/deposits/`
- `GET /api/jobs/{id}/logs/`
- `POST /api/jobs/{id}/export/`
- `GET /api/processing/settings/`
- `PATCH /api/processing/settings/`

## Recommended demo flow

1. Open Dashboard
2. Upload a `.docx`
3. Start processing
4. Wait for automatic refresh or click `Actualizar estado`
5. Review results
6. Edit one or two rows and click `Guardar correcciones`
7. Export Excel
8. Show that refresh keeps the corrected values

## Validation commands

### Backend

```bash
python manage.py test tests.test_api tests.test_docx_extractor tests.test_excel_exporter tests.test_validators tests.test_tesseract_ocr -v 1
```

### Frontend

```bash
npm run build
npm run typecheck
npm test
```

## Known presentation caveats

- Background processing is thread-based for demo simplicity
- Use `STUB_PROVIDERS=1` if you want deterministic processing during the presentation
- The assistant panel is guidance UI, not a live AI backend capability
