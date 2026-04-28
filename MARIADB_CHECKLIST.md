# ✅ Checklist de Instalación - MariaDB Backend

## 📋 Pre-Requisitos

- [ ] Docker y Docker Compose instalados
- [ ] Python 3.12+ instalado (para desarrollo local)
- [ ] Git clone del repositorio completado
- [ ] Variables de entorno (.env) configuradas

## 🔧 Configuración

- [ ] Archivo `.env` creado con variables de MariaDB
  - [ ] `DATABASE_URL` apunta a MariaDB
  - [ ] `DB_HOST`, `DB_PORT`, `DB_NAME` configurados
  - [ ] `DB_USER` y `DB_PASSWORD` configurados
  - [ ] `DB_ROOT_PASSWORD` configurado

- [ ] requirements.txt actualizado con `mysqlclient==2.2.5`

- [ ] docker-compose.yml actualizado
  - [ ] Servicio `mariadb` configurado
  - [ ] Volumen `mariadb_data` creado
  - [ ] Backend depende de MariaDB
  - [ ] Variables de entorno pasadas a backend

- [ ] Dockerfile actualizado
  - [ ] Dependencias de sistema agregadas (libmysqlclient-dev)
  - [ ] Script de inicialización en CMD

- [ ] MCP_back/settings.py actualizado
  - [ ] Configuración MySQL/MariaDB con opciones
  - [ ] charset: utf8mb4
  - [ ] ATOMIC_REQUESTS: True
  - [ ] CONN_MAX_AGE: 600

## 🚀 Inicio con Docker

- [ ] Navegar a `backend-django-diplo`
  ```bash
  cd backend-django-diplo
  ```

- [ ] Construir y iniciar contenedores
  ```bash
  docker-compose up -d
  ```

- [ ] Verificar que MariaDB está corriendo (esperar ~15 segundos)
  ```bash
  docker-compose ps
  # Estados esperados: mariadb (Up), backend (Up)
  ```

- [ ] Verificar logs del backend
  ```bash
  docker-compose logs -f backend
  # Esperar a ver "Starting development server..."
  ```

- [ ] Presionar Ctrl+C para salir de logs

## 📊 Verificación de Base de Datos

- [ ] Conectar a MariaDB
  ```bash
  docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db
  ```

- [ ] Ver tablas creadas
  ```sql
  SHOW TABLES;
  ```

- [ ] Verificar que existen las tablas:
  - [ ] `processing_processrun`
  - [ ] `processing_sourceimage`
  - [ ] `processing_extracteddeposit`
  - [ ] `processing_processingSettings`
  - [ ] `processing_extractionlog`

- [ ] Ver charset de la base de datos
  ```sql
  SELECT @@character_set_database, @@collation_database;
  -- Esperado: utf8mb4 | utf8mb4_unicode_ci
  ```

- [ ] Salir de MySQL
  ```sql
  EXIT;
  ```

## 🔍 Verificación Completa

- [ ] Ejecutar script de verificación
  ```bash
  python scripts/verify_mariadb.py
  ```

- [ ] Todos los chequeos deben ser ✓ (verdes)

- [ ] Estado final: "✓ INSTALACIÓN COMPLETADA Y VERIFICADA"

## 🌐 Verificar Backend

- [ ] Acceder al endpoint API
  ```bash
  curl http://localhost:8000/api/
  # Debe retornar JSON con información de API
  ```

- [ ] Acceder a documentación OpenAPI
  ```
  http://localhost:8000/api/schema/swagger-ui/
  ```

- [ ] Ver que endpoints están disponibles
  - [ ] `/api/documents/`
  - [ ] `/api/processing/`
  - [ ] `/api/settings/`

## 💾 Prueba de Flujo

- [ ] Crear un documento de prueba (DOCX)

- [ ] Subir documento al backend
  ```bash
  curl -X POST -F "file=@test.docx" http://localhost:8000/api/documents/upload/
  ```

- [ ] Verificar que se creó registro en base de datos
  ```bash
  docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db \
    -e "SELECT id, original_filename, status FROM processing_processrun LIMIT 1;"
  ```

- [ ] Ver proceso en tiempo real
  ```bash
  docker-compose logs -f backend
  ```

## 🛑 Detener Servicios

- [ ] Detener todo (sin perder datos)
  ```bash
  docker-compose stop
  ```

- [ ] Detener y eliminar volúmenes (destruir datos)
  ```bash
  docker-compose down -v
  ```

- [ ] Reiniciar todo
  ```bash
  docker-compose restart
  ```

## 🔐 Seguridad

- [ ] Verificar que credenciales son seguras (.env nunca en Git)
  ```bash
  git status | grep .env
  # No debe mostrar .env (debería estar en .gitignore)
  ```

- [ ] Para producción:
  - [ ] Cambiar todas las contraseñas
  - [ ] Habilitar SSL/TLS
  - [ ] Limitar acceso por IP
  - [ ] Usar secretos de Docker/Kubernetes

## 📝 Documentación

- [ ] Leer `MARIADB_MIGRATION.md` - Resumen de cambios
- [ ] Leer `MARIADB_SETUP.md` - Documentación completa
- [ ] Leer `MARIADB_QUICKSTART.md` - Guía rápida
- [ ] Leer `DATABASE_STRUCTURE.md` - Estructura de datos

## 🐛 Troubleshooting

### MariaDB no inicia

- [ ] Ver logs de MariaDB
  ```bash
  docker-compose logs mariadb
  ```

- [ ] Verificar puerto 3306 no está en uso
  ```bash
  # Windows
  netstat -ano | findstr :3306
  
  # Linux/Mac
  lsof -i :3306
  ```

- [ ] Recrear desde cero
  ```bash
  docker-compose down -v
  docker-compose up -d mariadb
  sleep 15
  docker-compose up -d backend
  ```

### Backend no conecta a MariaDB

- [ ] Verificar variables de entorno
  ```bash
  docker-compose config | grep DATABASE_URL
  ```

- [ ] Ver logs de backend
  ```bash
  docker-compose logs backend | head -50
  ```

- [ ] Verificar conectividad
  ```bash
  docker-compose exec backend python -c "import MySQLdb; print('MySQLdb OK')"
  ```

### Migraciones fallan

- [ ] Ejecutar manualmente
  ```bash
  docker-compose exec backend python manage.py migrate --verbosity=2
  ```

- [ ] Ver estado de migraciones
  ```bash
  docker-compose exec backend python manage.py showmigrations
  ```

- [ ] Recrear todo
  ```bash
  docker-compose down -v
  docker-compose up -d
  ```

## ✨ Siguiente Pasos

- [ ] Configurar frontend (si aún no está hecho)
- [ ] Probar flujo completo OCR
- [ ] Hacer correcciones manuales
- [ ] Exportar a Excel
- [ ] Configurar backups en producción
- [ ] Agregar monitoreo

## 📞 Soporte

Si hay problemas:

1. Revisar documentación:
   - `MARIADB_SETUP.md` - Problemas comunes
   - `MARIADB_QUICKSTART.md` - Soluciones rápidas

2. Ejecutar verificación:
   ```bash
   python scripts/verify_mariadb.py
   ```

3. Ver logs:
   ```bash
   docker-compose logs -f
   ```

4. Contactar al equipo de desarrollo con:
   - Mensaje de error exacto
   - Output de `docker-compose ps`
   - Output de `docker-compose logs`

---

**Estado:** ✅ Checklist completado
**Proyecto:** MCP Backend - Migración MariaDB
**Fecha:** Abril 2026
