# Autenticación y autorización

## Propósito

Describir el mecanismo de control de acceso real implementado en el backend.

## Mecanismo actual

- Implementación: `apps/api/auth.py`.
- Permiso principal: `ApiKeyPermission`.
- Header esperado: `X-API-Key` (servidor: `HTTP_X_API_KEY`).

## Reglas de acceso

- Si `API_KEY` está configurada, se exige API key.
- Si `API_KEY` no está configurada y `ALLOW_OPEN_API_FOR_DEV=1`, se permite acceso abierto.
- En producción (`DJANGO_DEBUG=0`), `API_KEY` debe estar configurada.

## Endpoints sin restricción de API key

- `HealthView` (`GET /api/health/`).
- Root view del proyecto (`/`) como verificación liviana.

## Consideraciones de seguridad

- La comparación de claves usa `secrets.compare_digest`.
- El backend no implementa autenticación por usuario/sesión/JWT para estos endpoints.
- Control CORS/CSRF depende de settings y variables de entorno.

## Pendiente de validar

- Requisitos de autenticación/autoría por rol para escenarios multiusuario reales.

## Enlaces relacionados

- [Configuración](configuration.md)
- [API](api.md)
