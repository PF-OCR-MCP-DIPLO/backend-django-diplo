# Apps Django

| App | Responsabilidad |
| --- | --- |
| `apps.api` | Endpoints REST, serializers, auth y errores |
| `apps.documents` | Carga de DOCX y extracción de imágenes |
| `apps.extraction` | OCR, LLM, schemas y validación |
| `apps.processing` | Modelos, orquestación, exportación y ajustes |
| `apps.common` | Middleware, logging y utilidades compartidas |

## Relación

`apps.api` orquesta llamadas a `apps.documents`, `apps.extraction` y `apps.processing`.

