# Desarrollo

## Propósito

Concentrar comandos y prácticas verificadas para desarrollo, mantenimiento y
debugging del backend.

## Entorno local

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Si `DATABASE_URL` no está definido y `DJANGO_DEBUG=1`, el backend usa SQLite.
Para MariaDB/MySQL configura `DATABASE_URL`.

## Comandos base

| Comando | Uso |
| --- | --- |
| `python manage.py runserver` | Servidor local |
| `python manage.py migrate` | Aplicar migraciones |
| `python manage.py makemigrations` | Crear migraciones |
| `python manage.py test` | Ejecutar tests |
| `black --check .` | Verificar formato |
| `python manage.py spectacular --file openapi.yaml` | Generar OpenAPI |

## Calidad observada en CI

El workflow `.github/workflows/ci.yml` ejecuta:

```bash
black --check .
python manage.py migrate --noinput
python -m coverage run manage.py test
python -m coverage report -m --fail-under=70
```

## Documentación

El workflow de docs ejecuta:

```bash
python -m pip install -r requirements-docs.txt
mkdocs build --strict --site-dir site
```

Si agregas un archivo en `docs/`, enlázalo desde `docs/index.md` y
`mkdocs.yml` para evitar warnings en modo strict.

## Scripts del repositorio

| Script | Uso |
| --- | --- |
| `scripts/debug_processing_pipeline.py` | Crear o reutilizar jobs y diagnosticar OCR/LLM |
| `scripts/init_mariadb.py` | Inicialización auxiliar de MariaDB |
| `scripts/verify_mariadb.py` | Verificación de MariaDB |
| `scripts/direct_mcp_probe.py` | Prueba directa de MCP |
| `scripts/prod_*.sh` | Operación de despliegue productivo |

Ejemplo de diagnóstico controlado:

```bash
python scripts/debug_processing_pipeline.py --stub --sync --max-images 1
```

## Cambios en OCR/procesamiento

Antes de tocar `apps/extraction` o `apps/processing`:

1. Identifica el contrato afectado: upload, OCR, estructuración, validación,
   persistencia, exportación o diagnóstico.
2. Conserva logs de etapa y muestras de OCR.
3. Ejecuta tests unitarios y de regresión específicos.
4. Compara salida con una muestra representativa si el cambio afecta OCR real.
5. Actualiza docs y frontend si cambia el contrato API.

Tests recomendados:

```bash
python manage.py test tests.test_tesseract_ocr
python manage.py test tests.test_ocr_pipeline_stability
python manage.py test tests.test_processing_diagnostics
python manage.py test tests.test_extraction_providers
python manage.py test tests.test_docx_extractor
python manage.py test tests.test_api_contracts
```

## Binarización y preprocesamiento

No actives binarización global sin evidencia. El preprocesamiento actual ya
aplica orientación EXIF, escala de grises, autocontraste y resize para imágenes
pequeñas. El modo visión añade sharpen y mantiene `binarize=False`.

Para validar cambios:

- revisa `ocr_raw_text` y `ocr_raw_text_sample`;
- compara `raw_text_chars` y `score`;
- confirma que referencias, montos, fechas y horas no pierdan separadores;
- ejecuta `tests.test_tesseract_ocr`;
- revisa `persistence_mismatch` y `record_skipped`.

## Investigación de regresiones

Comandos útiles:

```bash
git log --oneline -- apps/extraction apps/processing tests
git diff <commit-bueno>..<commit-malo> -- apps/extraction apps/processing tests
git blame apps/extraction/providers/ocr/tesseract.py
```

Cuando la causa no sea obvia:

```bash
git bisect start
git bisect bad
git bisect good <commit-bueno>
python manage.py test tests.test_tesseract_ocr tests.test_ocr_pipeline_stability
```

Usa un comando reproducible para clasificar cada commit del bisect.

## Convenciones de commits

- `docs: ...` documentación.
- `test: ...` pruebas.
- `fix: ...` corrección funcional.
- `refactor: ...` cambio interno sin alterar comportamiento esperado.

Mantén commits pequeños y separados por repositorio cuando backend y frontend
viven como repos independientes.

## Enlaces relacionados

- [Configuración](configuration.md)
- [Contrato API](api-contract.md)
- [Pipeline de procesamiento](processing-pipeline.md)
- [Troubleshooting OCR](ocr-troubleshooting.md)
- [Testing](testing.md)
- [Troubleshooting](troubleshooting.md)
