# Servicios

| Servicio | Responsabilidad | Efectos |
| --- | --- | --- |
| `upload_service.py` | Crear corrida desde DOCX | Escribe archivos y registros |
| `job_runner.py` | Coordinar procesamiento | Cambia estados |
| `orchestrator.py` | Pipeline principal | Invoca OCR y LLM |
| `manual_corrections.py` | Correcciones y reprocesos | Reescribe depósitos |
| `excel_exporter.py` | Exportación Excel | Genera archivo |
| `diagnostics.py` | Resúmenes de estado | Solo lectura |
| `settings_service.py` | Configuración | Lee/escribe singleton |

