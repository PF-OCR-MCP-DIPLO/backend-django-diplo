# Backend Diplo Final

Backend Django/DRF para procesar documentos DOCX con comprobantes bancarios
embebidos, extraer texto por OCR, estructurar consignaciones, permitir
correcciones manuales, exportar resultados a Excel y asistir el diagnóstico del
pipeline.

## Descripción funcional

El sistema expone una API REST bajo `/api/` que permite:

- subir documentos `.docx` con imágenes embebidas;
- crear corridas de procesamiento trazables;
- extraer imágenes y texto auxiliar del DOCX;
- ejecutar OCR con Tesseract, Ollama Vision o stubs determinísticos;
- estructurar texto OCR con LLM de Ollama o stub;
- validar y persistir consignaciones;
- corregir resultados manualmente;
- reprocesar fuentes fallidas o imágenes puntuales;
- exportar consignaciones a Excel;
- consultar logs, diagnósticos, salud de proveedores y asistente contextual.

## Stack técnico

| Capa | Tecnología verificada |
| --- | --- |
| Runtime | Python 3.12 |
| Web/API | Django 6.0.4, Django REST Framework 3.17.1 |
| Schema | drf-spectacular |
| Base de datos | SQLite en debug sin `DATABASE_URL`; MariaDB/MySQL por `DATABASE_URL` |
| OCR | Tesseract local, Ollama Vision, stub de pruebas |
| LLM | Ollama text, stub de pruebas |
| Exportación | openpyxl |
| Tests/calidad | `manage.py test`, coverage, Black |
| Docker | `Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml` |

## Arquitectura general

El backend separa entrada HTTP, servicios de dominio y persistencia:

1. `apps/api` valida requests, aplica `X-API-Key` y serializa respuestas.
2. `apps/documents` valida DOCX y extrae imágenes en orden de aparición.
3. `apps/extraction` contiene validación de imágenes, OCR, estructuración LLM y
   validadores semánticos.
4. `apps/processing` orquesta jobs, settings, diagnósticos, correcciones,
   reprocesos y exportación.
5. `mcp_server` ofrece herramientas MCP alrededor del mismo contrato HTTP.

La trazabilidad vive en `ExtractionLog`, `SourceImage.ocr_raw_text` y
`ProcessRun.provider_config_snapshot`.

## Estructura de carpetas

| Ruta | Propósito |
| --- | --- |
| `MCP_back/` | Configuración Django, URLs raíz, WSGI/ASGI |
| `apps/api/` | Vistas REST, serializers, auth por API key y servicios del asistente |
| `apps/documents/` | Carga de DOCX y extracción de imágenes/texto |
| `apps/extraction/` | OCR, LLM, validación de imágenes y datos extraídos |
| `apps/processing/` | Modelos, settings, orquestación, jobs, diagnósticos y exportación |
| `mcp_server/` | Servidor y cliente MCP |
| `scripts/` | Utilidades de diagnóstico, MariaDB, Docker y operación |
| `tests/` | Suite de pruebas backend |
| `docs/` | Documentación técnica mantenible |

## Requisitos previos

- Python 3.12.
- `pip`.
- Base de datos local: SQLite para desarrollo rápido o MariaDB/MySQL.
- Binario de Tesseract y lenguaje `spa` si se usa OCR local real fuera de Docker.
- Ollama local o accesible por red si se usan modos `vision` o `auto` con
  proveedor `ollama`.
- Docker y Docker Compose si se usa el stack containerizado.

## Instalación local

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

La API queda disponible en `http://localhost:8000/api/`.

## Variables de entorno

Las variables se cargan desde `.env` mediante `python-dotenv`. En producción,
`DJANGO_DEBUG=0` obliga a configurar `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS` y `API_KEY`.

| Variable | Uso |
| --- | --- |
| `DJANGO_DEBUG` | Activa modo debug cuando vale `1` |
| `DJANGO_SECRET_KEY` | Clave Django |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos separados por coma |
| `DJANGO_TIME_ZONE` | Zona horaria, por defecto `America/Bogota` |
| `DATABASE_URL` | URL de BD; si falta en debug se usa SQLite |
| `API_KEY` | Valor esperado en header `X-API-Key` |
| `ALLOW_OPEN_API_FOR_DEV` | Permite API abierta solo en debug |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos para frontend |
| `PROCESS_JOBS_ASYNC` | `1` lanza jobs en hilo de fondo; `0` procesa síncrono |
| `STUB_PROVIDERS` | `1` usa proveedores determinísticos para demos/tests |
| `OCR_PROVIDER`, `LLM_PROVIDER` | Proveedor base para OCR/LLM |
| `OCR_MODE`, `OCR_MODEL` | Modo OCR y modelo/idioma por defecto |
| `OLLAMA_BASE_URL`, `OLLAMA_URL`, `OLLAMA_TAGS_URL` | Endpoints Ollama |
| `OLLAMA_MODEL`, `OLLAMA_VISION_MODEL`, `OLLAMA_TIMEOUT` | Modelos y timeout Ollama |
| `LLM_MODEL`, `ASSISTANT_MODEL` | Modelos efectivos de LLM y asistente |
| `ASSISTANT_TEMPERATURE`, `ASSISTANT_NUM_PREDICT` | Parámetros de generación del asistente |
| `OCR_TEMPERATURE`, `OCR_NUM_PREDICT` | Parámetros OCR definidos en settings |
| `LLM_MAX_RETRIES`, `LLM_RETRY_DELAY` | Reintentos para estructuración LLM |
| `MAX_OCR_CHARS_FOR_LLM` | Máximo texto OCR enviado a LLM |
| `TESSERACT_TIMEOUT_SECONDS` | Timeout máximo para Tesseract |
| `DOCX_MAX_UPLOAD_BYTES`, `DOCX_MAX_IMAGES` | Límites de carga DOCX |
| `EXTRACTED_IMAGE_MAX_BYTES` | Tamaño máximo por imagen extraída |
| `MCP_ENABLE_MUTATIONS` | Habilita mutaciones MCP si vale verdadero |

## Base de datos

- En desarrollo con `DJANGO_DEBUG=1` y sin `DATABASE_URL`, Django usa
  `db.sqlite3`.
- Para MariaDB/MySQL usa una URL como
  `mysql://mcp_user:mcp_secure_2026@localhost:3306/mcp_db`.
- `docker-compose.yml` crea un servicio `mariadb` con charset `utf8mb4` y el
  backend se conecta con `DATABASE_URL` apuntando al servicio interno.

Comandos básicos:

```bash
python manage.py migrate
python manage.py makemigrations
python manage.py createsuperuser
```

## Ejecución en desarrollo

```bash
python manage.py runserver
```

Para forzar procesamiento síncrono durante debug:

```bash
PROCESS_JOBS_ASYNC=0 python manage.py runserver
```

Para una demo determinística sin depender de OCR/LLM reales:

```bash
STUB_PROVIDERS=1 PROCESS_JOBS_ASYNC=0 python manage.py runserver
```

## Ejecución con Docker

El `docker-compose.yml` incluye `mariadb`, `backend`, `frontend` y un perfil
opcional `ollama`.

```bash
docker compose up --build
```

Con Ollama dentro del compose:

```bash
docker compose --profile ollama up --build
```

El `Dockerfile` instala Tesseract, `tesseract-ocr-spa`, dependencias Python y
ejecuta migraciones/collectstatic desde `scripts/docker-entrypoint.sh`.

## Comandos útiles

| Comando | Propósito |
| --- | --- |
| `python manage.py runserver` | Servidor local |
| `python manage.py migrate` | Aplicar migraciones |
| `python manage.py test` | Suite Django |
| `python -m coverage run manage.py test` | Tests con coverage |
| `python -m coverage report -m --fail-under=70` | Umbral observado en CI |
| `black --check .` | Formato verificado en CI |
| `python manage.py spectacular --file openapi.yaml` | Generar schema OpenAPI |
| `python scripts/debug_processing_pipeline.py --stub --sync --max-images 1` | Diagnóstico controlado del pipeline |

## Endpoints principales

La mayoría de endpoints requiere `X-API-Key` cuando `API_KEY` está configurada.

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/api/health/` | Health check |
| `POST` | `/api/documents/upload/` | Subir DOCX y crear corrida |
| `GET` | `/api/jobs/` | Listar corridas |
| `GET` | `/api/jobs/{id}/` | Detalle de corrida |
| `DELETE` | `/api/jobs/{id}/` | Eliminar corrida si no procesa |
| `POST` | `/api/jobs/{id}/process/` | Iniciar o repetir procesamiento; acepta `?force=true` |
| `POST` | `/api/jobs/{id}/reprocess-failed/` | Reprocesar fuentes fallidas |
| `POST` | `/api/jobs/{id}/source-images/{source_image_id}/reprocess/` | Reprocesar una imagen |
| `POST` | `/api/jobs/{id}/deposits/{deposit_id}/reprocess/` | Reprocesar desde un depósito |
| `PATCH` | `/api/jobs/{id}/deposits/` | Guardar correcciones manuales |
| `GET` | `/api/jobs/{id}/logs/` | Logs técnicos |
| `GET` | `/api/jobs/{id}/diagnostics/` | Diagnóstico agregado |
| `GET` | `/api/jobs/{id}/processing-state/` | Estado resumido para polling |
| `POST` | `/api/jobs/{id}/export/` | Generar Excel |
| `GET/PATCH` | `/api/processing/settings/` | Leer/actualizar settings |
| `GET` | `/api/processing/settings/options/` | Catálogos de UI |
| `GET` | `/api/processing/ollama/models/` | Modelos Ollama detectados |
| `GET` | `/api/processing/provider-health/` | Salud de proveedores |
| `POST` | `/api/assistant/chat/` | Chat de asistente |

OpenAPI:

- `GET /api/schema/`
- `GET /api/docs/`
- `GET /api/redoc/`

## Flujo de procesamiento

1. **Carga de DOCX**: `DocumentUploadView` valida extensión/tamaño y delega en
   `create_process_run_from_upload`.
2. **Extracción de imágenes**: `extract_images_in_order` recorre el paquete
   OpenXML, respeta el orden visual y aplica límites de cantidad/tamaño.
3. **Validación/preprocesamiento**: `validate_source_image` verifica firmas de
   imagen. Antes de OCR, `preprocess_image_for_ocr` aplica orientación EXIF,
   escala de grises, autocontraste, resize para imágenes pequeñas y, en visión,
   sharpen. La binarización existe como opción interna pero no se activa por
   defecto en el flujo actual.
4. **OCR**: `extract_raw_text` ejecuta `tesseract`, `vision` o `auto`. En
   `auto`, compara intentos Tesseract y visión y conserva metadatos de ambos.
5. **Estructuración**: `extract_structured_data` envía texto OCR al proveedor
   LLM, limita el tamaño con `MAX_OCR_CHARS_FOR_LLM` y usa fallback heurístico
   cuando no hay registros.
6. **Validación**: los agentes validan campos requeridos, periodo válido y
   criterios de extracción configurados.
7. **Persistencia**: se guardan `ExtractedDeposit`, `SourceImage.ocr_raw_text`,
   estado de imagen y logs de etapa.
8. **Exportación**: `export_job_to_excel` genera un `.xlsx` desde depósitos
   persistidos.
9. **Diagnóstico**: `ExtractionLog`, `/logs/`, `/diagnostics/`,
   `/processing-state/` y `/provider-health/` ayudan a explicar resultados,
   errores, timeouts y calidad OCR.

## Proveedores OCR/LLM soportados

| Área | Operativo en código | Notas |
| --- | --- | --- |
| OCR local | `tesseract` | Usa binario Tesseract y lenguaje resuelto desde `ocr_model` |
| OCR visión | `ollama` | Usa `OllamaVisionOCRProvider` y `OLLAMA_URL` |
| OCR stub | `STUB_PROVIDERS=1` | Determinístico para pruebas y demos |
| LLM texto | `ollama` | Usa `OllamaTextLLMProvider` |
| LLM stub | `STUB_PROVIDERS=1` | Determinístico |
| Catálogos no operativos MVP | `openai`, `gemini`, `deepseek`, `anthropic` | Aparecen en settings/options, pero serializers y proveedores los rechazan o marcan no implementados |

## Settings de procesamiento

`ProcessingSettings` es un singleton editable por API. Los campos principales
son:

- `ocr_mode`: `tesseract`, `vision` o `auto`.
- `ocr_provider`: proveedor OCR, normalmente `ollama` salvo modo Tesseract.
- `ocr_model`: idioma Tesseract (`spa`, `eng`, `spa+eng`) o modelo visión.
- `llm_provider` y `llm_model`: proveedor/modelo para estructuración.
- `assistant_provider` y `assistant_model`: proveedor/modelo del asistente.
- `request_timeout_seconds`: límite runtime validado entre 5 y 600 segundos.
- `valid_consignation_month` y `valid_consignation_year`: periodo válido para
  observaciones.
- `extraction_criteria`: reglas configurables de campos requeridos y validación.
- `assistant_show_debug_details`: controla detalle técnico en respuestas del
  asistente.

Las API keys de OCR/LLM/asistente se escriben por `PATCH`, pero las respuestas
solo exponen banderas `has_*_api_key`.

## Calidad OCR y binarización

La calidad OCR depende de la imagen original, el modo OCR, el modelo y el
preprocesamiento.

| Factor | Impacto |
| --- | --- |
| Resolución | Imágenes pequeñas se reescalan al doble si el lado menor es inferior a 1000 px |
| Contraste | `ImageOps.autocontrast` mejora legibilidad, pero no recupera datos perdidos |
| Orientación | `ImageOps.exif_transpose` corrige orientación EXIF antes de leer |
| Ruido | Fondos, compresión y sombras pueden fragmentar números o separadores |
| Proveedor/modelo | Tesseract y visión pueden leer distinto el mismo comprobante |
| Prompt/criterios | Ollama Vision transcribe texto visible; el LLM estructura según criterios configurados |
| Binarización | Convierte pixeles a blanco/negro por umbral. Puede ayudar en texto oscuro sobre fondo claro, pero puede destruir tonos medios, separadores y dígitos finos |

El flujo actual no binariza por defecto. La regresión reciente se cubre con
`tests/test_tesseract_ocr.py::ResolveTesseractLanguageTests::test_tesseract_runner_preserves_midtone_receipt_text`,
que verifica que textos de tono medio no se pierdan en el preprocesamiento.

Síntomas típicos de mala binarización:

- dígitos faltantes en referencias o montos;
- separadores `.` `/` `:` desaparecidos;
- texto fragmentado o fusionado;
- referencias incompletas;
- montos interpretados con escala incorrecta;
- fechas u horas dañadas.

Antes de aceptar cambios en preprocesamiento, compara `ocr_raw_text`,
`ocr_raw_text_sample`, `raw_text_chars`, `attempts`, registros estructurados y
depósitos persistidos en logs/diagnósticos.

## Troubleshooting

| Síntoma | Qué revisar |
| --- | --- |
| OCR devuelve texto vacío | Imagen válida, `ocr_mode`, modelo instalado, `TESSERACT_TIMEOUT_SECONDS`, `/provider-health/`, logs etapa `ocr` |
| Resultados peores que antes | Diff de `apps/extraction/providers/ocr/tesseract.py`, preprocesamiento, `ocr_raw_text_sample`, scores e intentos en modo `auto` |
| Proveedor no responde | `OLLAMA_URL`, `OLLAMA_TIMEOUT`, `request_timeout_seconds`, disponibilidad de Ollama, errores en `provider_error_message` |
| API key inválida | Header `X-API-Key`, `API_KEY`, `ALLOW_OPEN_API_FOR_DEV` y modo debug |
| Errores con DOCX | Extensión `.docx`, firma ZIP, `DOCX_MAX_UPLOAD_BYTES`, `DOCX_MAX_IMAGES` |
| Imágenes no extraídas | Estructura OpenXML, imágenes embebidas reales, límites de tamaño y `docx_no_images` |
| Diferencias entre proveedores | Ejecutar modo `auto`, revisar `attempts` y `auto_ocr_selected` |
| Problemas por binarización | Buscar pérdida de tonos medios, dígitos y separadores en texto OCR bruto |

Más detalle en [docs/ocr-troubleshooting.md](docs/ocr-troubleshooting.md).

## Tests

Suite completa:

```bash
python manage.py test
```

Checks de CI:

```bash
black --check .
python manage.py migrate --noinput
python -m coverage run manage.py test
python -m coverage report -m --fail-under=70
```

Tests recomendados para cambios en OCR/procesamiento:

```bash
python manage.py test tests.test_tesseract_ocr
python manage.py test tests.test_ocr_pipeline_stability
python manage.py test tests.test_processing_diagnostics
python manage.py test tests.test_extraction_providers
python manage.py test tests.test_docx_extractor
python manage.py test tests.test_api_contracts
```

## Buenas prácticas para modificar el pipeline

- Cambia una etapa a la vez y conserva logs comparables.
- No elimines `ocr_raw_text`, `raw_payload` ni muestras de diagnóstico.
- Mantén `STUB_PROVIDERS=1` para pruebas determinísticas y ejecuta pruebas reales
  aparte si cambias OCR/LLM.
- No actives binarización global sin evidencia con muestras reales.
- Si ajustas prompts o criterios, valida estructura, persistencia y exportación.
- Si cambias API o serializers, actualiza frontend y tests de contrato.

## Investigar regresiones con Git

```bash
git log --oneline -- apps/extraction apps/processing tests
git diff <commit-bueno>..<commit-malo> -- apps/extraction apps/processing tests
git blame apps/extraction/providers/ocr/tesseract.py
git bisect start
git bisect bad
git bisect good <commit-bueno>
```

Durante `git bisect`, usa un comando reproducible, por ejemplo:

```bash
python manage.py test tests.test_tesseract_ocr tests.test_ocr_pipeline_stability
```

## Convenciones de commits

Usa commits pequeños y convencionales:

- `docs: ...` para documentación.
- `test: ...` para pruebas.
- `fix: ...` para correcciones funcionales.
- `refactor: ...` para cambios sin modificación de comportamiento.

## Riesgos conocidos y limitaciones

- Proveedores externos distintos de Ollama están listados, pero no operativos en
  este MVP.
- OCR real depende de calidad de imagen y modelos instalados.
- `PROCESS_JOBS_ASYNC=1` usa hilos en proceso, no una cola distribuida.
- `STUB_PROVIDERS=1` no representa calidad real de OCR/LLM.
- La exportación Excel solo refleja depósitos persistidos.

## Documentación relacionada

- [docs/index.md](docs/index.md)
- [docs/api-contract.md](docs/api-contract.md)
- [docs/processing-pipeline.md](docs/processing-pipeline.md)
- [docs/ocr-troubleshooting.md](docs/ocr-troubleshooting.md)
- [docs/development.md](docs/development.md)
