# 🚀 Guía Rápida: MariaDB Backend MCP

## ⚡ Inicio Rápido (Docker Compose)

### Paso 1: Configurar variables de entorno

```bash
# El archivo .env ya está configurado, solo verifica:
# DATABASE_URL=mysql://mcp_user:mcp_secure_2026@localhost:3306/mcp_db
```

### Paso 2: Levantar servicios

```bash
# Desde la carpeta backend-django-diplo
docker-compose up -d

# Esperar ~10 segundos a que MariaDB inicie
sleep 10

# Ver estado
docker-compose ps
```

### Paso 3: Inicializar base de datos

```bash
# Las migraciones se ejecutan automáticamente en el contenedor backend
# Verificar logs:
docker-compose logs backend

# Si necesitas reiniciar migraciones:
docker-compose exec backend python scripts/init_mariadb.py
```

### Paso 4: Verificar acceso

```bash
# Backend API
curl http://localhost:8000/api/

# MariaDB directamente
docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db -e "SHOW TABLES;"
```

## 🔧 Desarrollo Local (Sin Docker)

### Requisitos
- Python 3.12+
- MariaDB 11.4+ o MySQL 8.0+
- pip

### Instalación

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Configurar .env (ya debería estar)
# Verificar que DATABASE_URL apunta a tu instancia MariaDB

# 3. Ejecutar migraciones
python scripts/init_mariadb.py

# 4. Iniciar servidor
python manage.py runserver 0.0.0.0:8000
```

## 📊 Verificar Base de Datos

### Tablas creadas

```bash
# Conectar a MariaDB
mysql -h localhost -u mcp_user -pmcp_secure_2026 -D mcp_db

# Listar tablas
SHOW TABLES;

# Ver estructura de una tabla
DESCRIBE processing_processrun;

# Contar registros
SELECT 
    table_name,
    table_rows
FROM information_schema.tables 
WHERE table_schema = 'mcp_db' 
AND table_type = 'BASE TABLE';
```

### Charset y Collation

```sql
-- Verificar configuración
SELECT @@character_set_database, @@collation_database;

-- Resultado esperado:
-- utf8mb4 | utf8mb4_unicode_ci
```

## 📤 Flujo de Datos (OCR)

1. **Upload DOCX** → `POST /api/documents/upload/`
   - Crea registro en `processing_processrun`

2. **Extracción OCR** → Automático
   - Guarda imágenes en `processing_sourceimage`
   - Texto OCR en `ocr_raw_text`

3. **Parseo Datos** → Automático
   - Consignaciones en `processing_extracteddeposit`
   - Datos en `structured_payload`

4. **Exportar Excel** → `GET /api/documents/{id}/export/`
   - Genera archivo Excel con datos

## 🔒 Seguridad Desarrollo

Credenciales actuales son **solo para desarrollo**:
- Usuario: `mcp_user`
- Contraseña: `mcp_secure_2026`
- Root: `root_mcp_2026`

⚠️ **Para producción**: Cambiar a valores seguros

## 🛑 Detener Servicios

```bash
# Con Docker
docker-compose down

# Mantener datos:
docker-compose down -v  # ⚠️ Borra volúmenes

# Solo backend
docker-compose stop backend

# Reiniciar todo
docker-compose restart
```

## 🐛 Troubleshooting Rápido

### MariaDB no inicia
```bash
# Ver logs
docker-compose logs mariadb

# Recrear desde cero
docker-compose down -v
docker-compose up -d mariadb
sleep 15
docker-compose up -d backend
```

### Migraciones fallan
```bash
# Ejecutar manualmente
docker-compose exec backend python manage.py migrate --verbosity=2

# O ver estado
docker-compose exec backend python manage.py showmigrations
```

### Conexión rechazada
```bash
# Verificar que MariaDB está corriendo
docker-compose ps mariadb

# Verificar credenciales en .env
cat .env | grep DB_

# Probar conexión directa
docker-compose exec mariadb mysql -u root -proot_mcp_2026 -e "SELECT 1;"
```

## 📚 Documentación Completa

Ver [MARIADB_SETUP.md](MARIADB_SETUP.md) para:
- Estructura completa de tablas
- Variables de entorno
- Migraciones posteriores
- Troubleshooting avanzado

## 💡 Comandos Útiles

```bash
# Ver logs en tiempo real
docker-compose logs -f backend

# Conectar a MariaDB
docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db

# Ejecutar comando Django
docker-compose exec backend python manage.py <comando>

# Shell Django
docker-compose exec backend python manage.py shell

# Crear superusuario
docker-compose exec backend python manage.py createsuperuser
```

## ✅ Checklist Inicial

- [ ] Variables de entorno (.env) configuradas
- [ ] `docker-compose up -d` ejecutado
- [ ] MariaDB iniciado (10-15 segundos)
- [ ] Backend iniciado y migraciones completadas
- [ ] `docker-compose ps` muestra ambos servicios `Up`
- [ ] `curl http://localhost:8000/api/` retorna 200 OK
- [ ] Tablas visibles en `SHOW TABLES;`

## 🎯 Próximos Pasos

1. Subir documento DOCX de prueba
2. Verificar extracción OCR
3. Revisar datos en `processing_extracteddeposit`
4. Exportar a Excel
5. Hacer correcciones manuales
