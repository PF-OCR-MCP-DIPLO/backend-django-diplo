# Jobs y workers

## Propósito

Explicar cómo se ejecutan corridas de procesamiento y reprocesos en el backend.

## Flujo de ejecución

- Entrada principal: `POST /api/jobs/{id}/process/`.
- Preparación: `prepare_job_for_processing` / `prepare_job_for_full_processing`.
- Ejecución: `process_prepared_job` en `orchestrator.py`.
- Persistencia de estado: actualización de `ProcessRun`, `SourceImage` y `ExtractionLog`.

## Modo asíncrono y síncrono

- Controlado por `PROCESS_JOBS_ASYNC`.
- Si está activo, `start_job_processing` lanza un hilo (`threading.Thread`) para ejecutar el job.
- Si no está activo, la ejecución ocurre en la misma request.

## Reproceso parcial

- `POST /api/jobs/{id}/reprocess-failed/`: reprocesa fuentes con error.
- `POST /api/jobs/{id}/source-images/{source_image_id}/reprocess/`: reproceso por fuente.
- `POST /api/jobs/{id}/deposits/{deposit_id}/reprocess/`: reproceso de consignación puntual.

## Estados de corrida

- `uploaded`
- `processing`
- `completed`
- `completed_with_errors`
- `failed`

## Jobs externos (colas dedicadas)

No se encontraron workers de Celery/RQ/Bull para ejecución distribuida en el backend actual.

## Pendiente de validar

- Estrategia oficial de escalamiento para producción cuando crezca el volumen de jobs.

## Enlaces relacionados

- [Arquitectura](architecture.md)
- [API](api.md)
- [Integraciones](integrations.md)
