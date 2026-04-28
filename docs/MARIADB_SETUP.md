# Migración de SQLite3 a MariaDB

## 📋 Descripción General

Este documento describe la migración del backend Django del proyecto MCP de SQLite3 a MariaDB. MariaDB es una base de datos relacional robusta que soporta:

- **Mejor rendimiento** en operaciones concurrentes
- **Escalabilidad** para procesamiento de múltiples documentos OCR
- **Transacciones ACID** para garantizar integridad de datos
- **Character set UTF-8MB4** para soporte completo de Unicode
- **Replicación y backup** nativo

## 🗂️ Estructura de Datos

Se crearán automáticamente las siguientes tablas según los modelos Django:

### Tabla: `processing_processrun`
Unidad principal de trazabilidad del flujo de procesamiento.

```
- id (PK)
- source_docx (FileField)
- original_filename (CharField)
- extracted_text (TextField)
- status (CharField) - Valores: uploaded, processing, completed, completed_with_errors, failed
- total_images (PositiveIntegerField)
- total_records (PositiveIntegerField)
- excel_file (FileField, nullable)
- error_message (TextField)
- provider_config_snapshot (JSONField)
- started_at (DateTimeField, nullable)
- finished_at (DateTimeField, nullable)
- created_at (DateTimeField)
- updated_at (DateTimeField)
```

### Tabla: `processing_sourceimage`
Imágenes extraídas del DOCX con estado OCR.

```
- id (PK)
- process_run_id (FK → processing_processrun)
- sequence_index (PositiveIntegerField)
- image_file (FileField)
- source_name (CharField)
- content_hash (CharField)
- ocr_status (CharField) - Valores: pending, processed, failed
- ocr_raw_text (TextField)
- ocr_provider (CharField)
- error_message (TextField)
- created_at (DateTimeField)
- updated_at (DateTimeField)

UNIQUE_CONSTRAINT: (process_run_id, sequence_index)
INDEX: sequence_index, process_run_id
```

### Tabla: `processing_extracteddeposit`
Consignaciones estructuradas derivadas de imágenes.

```
- id (PK)
- process_run_id (FK → processing_processrun)
- source_image_id (FK → processing_sourceimage)
- sequence_index (PositiveIntegerField)
- fecha_consignacion (CharField)
- hora_consignacion (CharField)
- referencia (CharField)
- valor (DecimalField, max_digits=14, decimal_places=2)
- is_current_month (BooleanField, nullable)
- observations (JSONField)
- structured_payload (JSONField)
- created_at (DateTimeField)

INDEX: sequence_index, process_run_id, source_image_id
```

### Tabla: `processing_processingSettings`
Configuración de OCR, LLM y asistente.

```
- id (PK)
- singleton_key (CharField, UNIQUE) - Default: "default"
- ocr_mode (CharField) - Valores: tesseract, vision, auto
- ocr_provider (CharField) - Valores: ollama, openai, gemini, deepseek, anthropic
- ocr_model (CharField)
- llm_provider (CharField)
- llm_model (CharField)
- assistant_provider (CharField)
- assistant_model (CharField)
- ocr_api_key (CharField)
- llm_api_key (CharField)
- assistant_api_key (CharField)
- assistant_temperature (FloatField, default=0.2)
- assistant_num_predict (PositiveIntegerField, default=256)
- assistant_show_debug_details (BooleanField)
- request_timeout_seconds (PositiveIntegerField, default=320)
- extraction_criteria (JSONField)
- created_at (DateTimeField)
- updated_at (DateTimeField)
```

### Tabla: `processing_extractionlog`
Eventos técnicos de extracción, validación o reproceso.

```
- id (PK)
- process_run_id (FK → processing_processrun)
- source_image_id (FK → processing_sourceimage, nullable)
- sequence_index (PositiveIntegerField)
- stage (CharField)
- provider (CharField)
- model (CharField)
- ocr_mode (CharField)
- raw_payload (JSONField)
- raw_text (TextField)
- notes (TextField)
- is_error (BooleanField)
- created_at (DateTimeField)

INDEX: sequence_index, process_run_id
```

## 🚀 Instalación y Configuración

### 1. Dependencias Python

Se agregó `mysqlclient==2.2.5` a requirements.txt:

```bash
pip install mysqlclient
```

### 2. Variables de Entorno (.env)

Actualizar el archivo `.env` con la configuración de MariaDB:

```env
# Base de Datos
DATABASE_URL=mysql://mcp_user:mcp_secure_2026@localhost:3306/mcp_db
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mcp_db
DB_USER=mcp_user
DB_PASSWORD=mcp_secure_2026
DB_ROOT_PASSWORD=root_mcp_2026
```

### 3. Docker Compose

Se actualizó `docker-compose.yml` para incluir servicio MariaDB:

```yaml
services:
  mariadb:
    image: mariadb:11.4
    environment:
      MARIADB_ROOT_PASSWORD: root_mcp_2026
      MARIADB_DATABASE: mcp_db
      MARIADB_USER: mcp_user
      MARIADB_PASSWORD: mcp_secure_2026
      MARIADB_COLLATE: utf8mb4_unicode_ci
      MARIADB_CHARSET: utf8mb4
    ports:
      - "3306:3306"
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 10s
      timeout: 5s
      retries: 5
```

## 🔧 Inicialización de Base de Datos

### Opción 1: Docker Compose (Recomendado)

```bash
# Construir y levantar contenedores
docker-compose up -d

# Verificar que todo esté corriendo
docker-compose ps

# Ver logs del backend
docker-compose logs -f backend
```

### Opción 2: Script Python

```bash
# Ejecutar desde el backend (requiere MariaDB corriendo)
python scripts/init_mariadb.py
```

### Opción 3: Script Bash (Linux/Mac)

```bash
# Ejecutar desde el backend (requiere MariaDB corriendo)
bash scripts/init_mariadb.sh
```

### Opción 4: Script Batch (Windows)

```cmd
# Ejecutar desde el backend (requiere MariaDB corriendo)
init_mariadb.bat
```

## 📊 Verificación

### Conectar a MariaDB

```bash
# Desde terminal
mysql -h localhost -u mcp_user -p -D mcp_db

# Comando: SHOW TABLES;
# Debería mostrar:
#  - processing_processrun
#  - processing_sourceimage
#  - processing_extracteddeposit
#  - processing_processingsettings
#  - processing_extractionlog
#  - (y otras tablas de Django como auth_user, etc.)
```

### Verificar Charset y Collation

```sql
SELECT @@character_set_database, @@collation_database;
-- Resultado esperado: utf8mb4, utf8mb4_unicode_ci
```

### Ver Tamaño de Tablas

```sql
SELECT 
    table_name,
    table_rows,
    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb,
    table_collation
FROM information_schema.tables
WHERE table_schema = 'mcp_db'
ORDER BY table_name;
```

## 🔄 Flujo de Datos OCR

1. **Upload** → Archivo DOCX sube al servidor
   - Se crea registro en `processing_processrun`
   - Estado: `uploaded`

2. **Extracción de Imágenes** → Se extraen imágenes del DOCX
   - Se crean registros en `processing_sourceimage`
   - Estado: `pending`

3. **OCR** → Se procesa cada imagen
   - Se actualiza `processing_sourceimage.ocr_raw_text`
   - Se crean registros en `processing_extractionlog`
   - Estado: `processed` o `failed`

4. **Extracción de Datos** → Se parsea OCR a consignaciones
   - Se crean registros en `processing_extracteddeposit`
   - `structured_payload` contiene datos parseados

5. **Corrección Manual** (opcional) → Usuario corrige errores
   - Se actualiza `processing_extracteddeposit`

6. **Exportación** → Se genera archivo Excel
   - Se actualiza `processing_processrun.excel_file`
   - Estado: `completed`

## 🔒 Seguridad

### Cambios de Producción

En `MCP_back/settings.py` se configuró:

```python
"OPTIONS": {
    "charset": "utf8mb4",
    "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
    "use_unicode": True,
    "autocommit": True,
},
"ATOMIC_REQUESTS": True,
"CONN_MAX_AGE": 600,
```

### Credenciales en Producción

⚠️ **IMPORTANTE**: Las credenciales en `.env` son solo para desarrollo.

Para producción:
- Cambiar todas las contraseñas por valores seguros
- Usar variables de entorno desde el sistema
- Usar secretos de Docker/Kubernetes
- Habilitar SSL/TLS en la conexión

```env
# Producción (ejemplo)
DATABASE_URL=mysql://prod_user:${SECURE_PASSWORD}@mariadb-prod.example.com:3306/mcp_db_prod
DJANGO_SECRET_KEY=${DJANGO_SECRET_PROD}
DJANGO_DEBUG=0
```

## 📝 Migraciones Posteriores

Si modificas modelos, ejecuta:

```bash
# Crear nuevas migraciones
python manage.py makemigrations

# Aplicar migraciones
python manage.py migrate

# Ver estado de migraciones
python manage.py showmigrations
```

## 🐛 Troubleshooting

### Error: "No module named 'MySQLdb'"

```bash
# Solución: instalar mysqlclient
pip install mysqlclient
```

### Error: "Can't connect to MySQL server"

- Verificar que MariaDB está corriendo: `docker-compose ps`
- Verificar variables de entorno en `.env`
- Verificar firewall y puertos
- Ver logs: `docker-compose logs mariadb`

### Error: "Unknown character set 'utf8mb4'"

Probablemente MariaDB versión antigua. Actualizar:

```bash
docker pull mariadb:11.4
docker-compose down
docker-compose up -d
```

### Error: "Table 'mcp_db.auth_user' doesn't exist"

Las migraciones no se ejecutaron. Ejecutar manualmente:

```bash
python manage.py migrate
```

## 📚 Referencias

- [MariaDB Official Documentation](https://mariadb.com/kb/en/documentation/)
- [Django ORM - Database Setup](https://docs.djangoproject.com/en/6.0/ref/settings/#databases)
- [Django Migrations](https://docs.djangoproject.com/en/6.0/topics/migrations/)
- [MySQLdb Documentation](https://github.com/PyMySQL/mysqlclient)

## 📞 Soporte

Para issues o preguntas:
1. Revisar logs: `docker-compose logs -f`
2. Conectar directamente a MariaDB y verificar datos
3. Revisar status de migraciones: `python manage.py showmigrations`
