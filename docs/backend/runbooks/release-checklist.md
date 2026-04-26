# Runbook: checklist de release

- Tests relevantes ejecutados
- Migraciones revisadas
- Variables de entorno documentadas
- Compatibilidad frontend-backend validada
- Schema OpenAPI regenerado o revisado
- Documentación actualizada
- Rollback básico confirmado

## Rollback básico

Si una release rompe la API, volver a la versión previa del backend y del
frontend al mismo tiempo para evitar desalineación de contratos.
