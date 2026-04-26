# ADR 0001: Django + DRF

## Estado
Aceptado

## Contexto
Se necesita una API con validación clara, serializers y documentación de schema.

## Decisión
Usar Django y Django REST Framework como stack backend principal.

## Consecuencias
- Estructura conocida para mantenimiento.
- Serializers y views facilitan contratos explícitos.
- El pipeline debe vivir en servicios para no cargar las views.
