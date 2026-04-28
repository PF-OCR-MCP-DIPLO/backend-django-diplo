# 🚀 Guía de Inicio Rápido - MariaDB (Windows PowerShell)

## ⚡ Inicio en 3 Pasos (Windows)

### Paso 1: Abrir PowerShell
```powershell
# Navegar a la carpeta del backend
cd "d:\Universidad\Diplomado\Proyecto final\backend-django-diplo"
```

### Paso 2: Iniciar Docker Compose
```powershell
# Construir y levantar contenedores
docker-compose up -d

# Esperar 15 segundos a que MariaDB inicie
Start-Sleep -Seconds 15

# Verificar estado
docker-compose ps
```

**Salida esperada:**
```
NAME              COMMAND                  SERVICE      STATUS          PORTS
backend           "sh -c 'python scri…"    backend      Up (healthy)    0.0.0.0:8000->8000/tcp
mariadb           "mariadb"                mariadb      Up (healthy)    0.0.0.0:3306->3306/tcp
```

### Paso 3: Verificar Base de Datos
```powershell
# Ejecutar verificación completa
python scripts/verify_mariadb.py
```

**Si todo está bien, verás:**
```
✓ Conexión a Base de Datos
✓ Charset y Collation
✓ Tablas Django
✓ Modelos Django
✓ Migraciones Django
✓ Configuración Django
✓ Estadísticas de Tablas

Resultado: 7/7 verificaciones pasadas
✓ INSTALACIÓN COMPLETADA Y VERIFICADA
```

## 🔧 Comandos Útiles (PowerShell)

### Ver logs en tiempo real
```powershell
# Backend
docker-compose logs -f backend

# MariaDB
docker-compose logs -f mariadb

# Ambos
docker-compose logs -f
```

### Conectar directamente a MariaDB
```powershell
# Abrir cliente MySQL
docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db

# Dentro de MySQL, ver tablas:
# SHOW TABLES;
# SELECT COUNT(*) FROM processing_processrun;
# EXIT;
```

### Ejecutar comando Django
```powershell
# Shell interactivo Django
docker-compose exec backend python manage.py shell

# Ver estado de migraciones
docker-compose exec backend python manage.py showmigrations

# Crear superusuario
docker-compose exec backend python manage.py createsuperuser
```

### Reiniciar servicios
```powershell
# Reiniciar todo
docker-compose restart

# Reiniciar solo backend
docker-compose restart backend

# Reiniciar solo MariaDB
docker-compose restart mariadb
```

### Detener servicios
```powershell
# Detener (sin perder datos)
docker-compose stop

# Detener y eliminar todo (CUIDADO: pierde datos)
docker-compose down -v

# Detener solo backend
docker-compose stop backend
```

## 📊 Verificar Datos

### Ver ProcessRuns (documentos subidos)
```powershell
docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db -e `
  "SELECT id, original_filename, status, created_at FROM processing_processrun ORDER BY created_at DESC LIMIT 5;"
```

### Ver imágenes extraídas
```powershell
docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db -e `
  "SELECT id, source_name, ocr_status FROM processing_sourceimage LIMIT 5;"
```

### Ver consignaciones
```powershell
docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db -e `
  "SELECT id, referencia, valor FROM processing_extracteddeposit LIMIT 5;"
```

### Ver tamaño de tablas
```powershell
docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db -e `
  "SELECT table_name, table_rows, ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb FROM information_schema.tables WHERE table_schema = 'mcp_db' ORDER BY table_rows DESC;"
```

## 🌐 Acceder a la API

### Desde PowerShell
```powershell
# Endpoint base
Invoke-RestMethod -Uri "http://localhost:8000/api/"

# Ver documentación Swagger
# Abrir en navegador: http://localhost:8000/api/schema/swagger-ui/
```

### Desde Navegador
- **API Base**: http://localhost:8000/api/
- **Swagger UI**: http://localhost:8000/api/schema/swagger-ui/
- **ReDoc**: http://localhost:8000/api/schema/redoc/
- **OpenAPI Schema**: http://localhost:8000/api/schema/

## 📤 Probar Flujo OCR

### 1. Preparar documento de prueba
```powershell
# Crear o descargar un DOCX de prueba
# Debe contener una tabla con consignaciones
```

### 2. Subir documento
```powershell
$file = "C:\ruta\al\test.docx"

# Subir y obtener ID
$response = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/documents/upload/" `
  -Method Post `
  -InFile $file `
  -ContentType "multipart/form-data" `
  -Headers @{"X-API-Key" = "dev"}

Write-Host "ID del ProcessRun: $($response.id)"

# Guardar el ID para después
$processRunId = $response.id
```

### 3. Monitorear procesamiento
```powershell
# Ver en tiempo real
docker-compose logs -f backend

# O consultar estado en base de datos
docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db -e `
  "SELECT id, status, total_images, total_records FROM processing_processrun WHERE id = $processRunId;"
```

### 4. Exportar a Excel
```powershell
# Una vez completado (status = "completed")
$response = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/documents/$processRunId/export/" `
  -Method Get `
  -Headers @{"X-API-Key" = "dev"}

# Descargar archivo Excel
[System.IO.File]::WriteAllBytes("C:\output\resultado.xlsx", $response)
```

## 🔐 Credenciales (Desarrollo)

```
MariaDB:
  Host: localhost
  Port: 3306
  Usuario: mcp_user
  Contraseña: mcp_secure_2026
  DB: mcp_db

API:
  API Key: dev
```

⚠️ **IMPORTANTE:** Cambiar todas las credenciales en producción

## 🐛 Troubleshooting (PowerShell)

### Error: "Port 3306 is already in use"

```powershell
# Encontrar qué está usando el puerto
netstat -ano | findstr :3306

# Matar el proceso (si es MariaDB antiguo)
taskkill /PID <PID> /F

# O cambiar puerto en .env y docker-compose.yml
# DB_PORT=3307
```

### Error: "Cannot connect to Docker daemon"

```powershell
# Asegurarse que Docker Desktop está corriendo
# Verificar estado
docker ps

# Si no funciona, reiniciar Docker Desktop manualmente
```

### Error: "MySQLdb module not found"

```powershell
# Las dependencias están en el Dockerfile
# Solo necesita reconstruir:
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### Backend no conecta a MariaDB

```powershell
# Verificar que MariaDB está corriendo
docker-compose ps mariadb

# Ver logs de error
docker-compose logs mariadb

# Reiniciar ambos
docker-compose stop
docker-compose start
```

### Migraciones no se ejecutaron

```powershell
# Ejecutar manualmente
docker-compose exec backend python manage.py migrate

# Ver estado
docker-compose exec backend python manage.py showmigrations

# Verificar integridad
python scripts/verify_mariadb.py
```

## 🎯 Próximas Acciones

1. **Completar frontend** (si no está hecho)
   ```powershell
   cd ..\Frontend-diplo
   docker-compose up -d
   ```

2. **Acceder a la UI**
   ```
   http://localhost:5173
   ```

3. **Subir documentos OCR**
   - Usar la interfaz web
   - O usar cURL/PowerShell

4. **Verificar datos en BD**
   ```powershell
   python scripts/verify_mariadb.py
   ```

5. **Configurar backups** (producción)
   ```powershell
   # Crear backup
   docker-compose exec mariadb mysqldump -u mcp_user -pmcp_secure_2026 mcp_db > backup.sql
   
   # Restaurar backup
   docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 mcp_db < backup.sql
   ```

## 📚 Documentación Completa

- **MARIADB_MIGRATION.md** - Resumen de cambios realizados
- **MARIADB_SETUP.md** - Documentación técnica completa
- **MARIADB_QUICKSTART.md** - Guía rápida para Linux/Mac
- **DATABASE_STRUCTURE.md** - Estructura de datos y relaciones
- **MARIADB_CHECKLIST.md** - Checklist de verificación

## 💡 Alias Útiles (Agregar a Perfil PowerShell)

```powershell
# En $PROFILE (Abre: notepad $PROFILE)
Set-Alias -Name docker-up -Value {docker-compose up -d}
Set-Alias -Name docker-down -Value {docker-compose down -v}
Set-Alias -Name docker-logs -Value {docker-compose logs -f}
Set-Alias -Name db-connect -Value {docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db}
Set-Alias -Name verify-db -Value {python scripts/verify_mariadb.py}
```

Luego usar:
```powershell
docker-up
docker-logs
db-connect
verify-db
docker-down
```

## 🔗 Enlaces Rápidos

- [MariaDB Docs](https://mariadb.com/kb/en/)
- [Docker Compose Docs](https://docs.docker.com/compose/)
- [Django ORM Docs](https://docs.djangoproject.com/en/6.0/topics/db/)
- [MySQLdb GitHub](https://github.com/PyMySQL/mysqlclient)

---

**Última actualización:** Abril 2026
**Plataforma:** Windows PowerShell + Docker
**Estado:** ✅ Listo para usar
