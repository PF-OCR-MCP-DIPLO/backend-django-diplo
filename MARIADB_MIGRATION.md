# 📝 Resumen de Cambios: Migración de SQLite3 a MariaDB

## 🎯 Objetivo
Migrar el backend Django del proyecto MCP de SQLite3 a MariaDB para:
- Mejor rendimiento en operaciones concurrentes
- Escalabilidad para procesamiento OCR
- Transacciones ACID robustas
- Soporte completo UTF-8MB4 para Unicode

## 📂 Archivos Modificados

### 1. **requirements.txt**
**Cambio:** Agregar dependencia para MySQL/MariaDB
```diff
+ mysqlclient==2.2.5
```
**Razón:** Django necesita `mysqlclient` para conectarse a MariaDB

---

### 2. **docker-compose.yml**
**Cambios principales:**
- ✅ Agregar servicio `mariadb` con MariaDB 11.4
- ✅ Configurar healthcheck para esperar a que MariaDB inicie
- ✅ Agregar variables de entorno de base de datos
- ✅ Agregar dependencia backend → mariadb
- ✅ Agregar volumen persistente `mariadb_data`

**Configuración MariaDB:**
```yaml
- CHARACTER SET: utf8mb4
- COLLATION: utf8mb4_unicode_ci
- Storage: InnoDB
- Max connections: 1000
```

**Enviroment variables:**
```env
DATABASE_URL=mysql://mcp_user:mcp_secure_2026@mariadb:3306/mcp_db
DB_HOST=mariadb
DB_PORT=3306
DB_NAME=mcp_db
DB_USER=mcp_user
DB_PASSWORD=mcp_secure_2026
```

---

### 3. **MCP_back/settings.py**
**Cambio:** Actualizar configuración de base de datos

```python
# Agregar opciones específicas de MySQL/MariaDB
"OPTIONS": {
    "charset": "utf8mb4",
    "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
    "use_unicode": True,
    "autocommit": True,
},
"ATOMIC_REQUESTS": True,
"CONN_MAX_AGE": 600,
```

**Beneficios:**
- `charset: utf8mb4` - Soporte completo Unicode (emojis, caracteres especiales)
- `STRICT_TRANS_TABLES` - Modo estricto para integridad de datos
- `ATOMIC_REQUESTS: True` - Todas las operaciones en transacción
- `CONN_MAX_AGE: 600` - Pool de conexiones reutilizables

---

### 4. **Dockerfile**
**Cambios:**
- ✅ Agregar `libmysqlclient-dev` para compilar mysqlclient
- ✅ Agregar cliente MariaDB para debugging
- ✅ Actualizar CMD para ejecutar script de inicialización

```dockerfile
# Nuevas dependencias
RUN apt-get install -y \
    mariadb-client \
    build-essential \
    libmysqlclient-dev

# CMD actualizado
CMD ["sh", "-c", "python scripts/init_mariadb.py && python manage.py runserver 0.0.0.0:8000"]
```

---

### 5. **.env**
**Cambios:** Agregar configuración de MariaDB

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

**Nota:** Estos valores son solo para desarrollo. Para producción, cambiar a credenciales seguras.

---

### 6. **.env.example**
**Cambio:** Agregar ejemplo de configuración de MariaDB

Sirve como referencia para nuevos desarrolladores.

---

## 🆕 Archivos Creados

### 1. **scripts/init_mariadb.py**
Script Python para inicialización automática:
- Espera a que MariaDB esté disponible (máx 30 intentos)
- Ejecuta migraciones Django
- Verifica integridad de tablas
- Carga datos iniciales (si existen)

**Uso:**
```bash
python scripts/init_mariadb.py
```

---

### 2. **scripts/init_mariadb.sh**
Script Bash para Linux/Mac:
- Configura base de datos y usuario
- Ejecuta migraciones
- Verifica tablas

**Uso:**
```bash
bash scripts/init_mariadb.sh
```

---

### 3. **scripts/verify_mariadb.py**
Script de verificación con salida colorida:
- Verifica conexión a MariaDB
- Verifica charset y collation
- Verifica tablas creadas
- Verifica modelos Django
- Verifica estado de migraciones
- Muestra estadísticas de almacenamiento

**Uso:**
```bash
python scripts/verify_mariadb.py
```

---

### 4. **init_mariadb.bat**
Script Batch para Windows:
- Ejecuta script Python de inicialización

**Uso:**
```cmd
init_mariadb.bat
```

---

### 5. **docs/MARIADB_SETUP.md**
Documentación completa sobre:
- Estructura de tablas y campos
- Variables de entorno
- Instalación paso a paso
- Verificación
- Flujo de datos OCR
- Seguridad
- Migraciones posteriores
- Troubleshooting

---

### 6. **docs/MARIADB_QUICKSTART.md**
Guía rápida de inicio:
- Inicio con Docker Compose (recomendado)
- Desarrollo local sin Docker
- Verificación de base de datos
- Flujo de datos
- Troubleshooting básico
- Comandos útiles

---

### 7. **docs/DATABASE_STRUCTURE.md**
Documentación técnica completa:
- Diagrama Entidad-Relación (ER)
- Descripción detallada de todas las tablas
- Estructura de relaciones
- Flujo de datos típico
- Consultas útiles
- Índices recomendados
- Constraints
- Estructura de campos JSON

---

## 🗂️ Estructura de Tablas Generadas

Se crearán automáticamente las siguientes tablas:

```
processing_processrun              - Unidad de trazabilidad
processing_sourceimage             - Imágenes extraídas
processing_extracteddeposit        - Consignaciones parseadas
processing_processingSettings      - Configuración global
processing_extractionlog           - Bitácora de eventos
+ Tablas estándar Django (auth_user, django_migrations, etc.)
```

## 🚀 Pasos para Activar MariaDB

### Opción 1: Docker Compose (Recomendado)
```bash
cd backend-django-diplo
docker-compose up -d
# Esperar ~10 segundos
docker-compose logs backend
```

### Opción 2: Python (Desarrollo Local)
```bash
# Asegurar que MariaDB esté corriendo localmente
python scripts/init_mariadb.py
python manage.py runserver
```

### Opción 3: Windows Batch
```cmd
cd backend-django-diplo
init_mariadb.bat
```

## ✅ Verificación

### Tablas Creadas
```bash
docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db -e "SHOW TABLES;"
```

### Charset Correcto
```bash
docker-compose exec mariadb mysql -u mcp_user -pmcp_secure_2026 -D mcp_db -e "SELECT @@character_set_database, @@collation_database;"
# Esperado: utf8mb4 | utf8mb4_unicode_ci
```

### Verificación Completa
```bash
python scripts/verify_mariadb.py
```

## 🔄 Flujo de Migración

```
SQLite3 (anterior)
├─ Datos locales en db.sqlite3
├─ No escalable
└─ Limitado para concurrencia

                    ↓
              Migración ↓

MariaDB (nuevo)
├─ Base de datos relacional robusta
├─ Escalable
├─ Soporte ACID
├─ Transacciones confiables
├─ Mejor rendimiento
└─ Ideal para producción
```

## 📊 Comparación: SQLite3 vs MariaDB

| Característica | SQLite3 | MariaDB |
|---|---|---|
| **Tipo** | Embebido | Servidor |
| **Concurrencia** | Limitada | Excelente |
| **Transacciones** | Básicas | ACID robusto |
| **Escalabilidad** | Baja | Alta |
| **Backups** | Archivo único | Backup nativo |
| **Replicación** | No | Sí |
| **Charset** | UTF-8 | UTF-8MB4 |
| **Producción** | No recomendado | Recomendado |
| **Desarrollo** | Bueno | Mejor |

## 🔒 Seguridad

### Desarrollo (Actual)
- Usuario: `mcp_user`
- Contraseña: `mcp_secure_2026` (cambiar en producción)
- Root: `root_mcp_2026` (cambiar en producción)

### Producción (Recomendado)
- Cambiar todas las credenciales
- Usar SSL/TLS
- Limitar acceso por IP
- Usar secretos de Docker/Kubernetes
- Backups regulares
- Monitoreo y alertas

## 📝 Cambios en el Flujo de Desarrollo

### Antes (SQLite3)
```
1. Clonar repo
2. python manage.py migrate
3. python manage.py runserver
✅ Listo en segundos
```

### Ahora (MariaDB)
```
1. Clonar repo
2. docker-compose up -d
3. Esperar ~15 segundos (MariaDB inicia)
4. docker-compose logs backend (verificar migraciones)
✅ Listo (~15 segundos en Docker)
```

## 🎯 Beneficios Logrados

✅ **Escalabilidad** - Soporta múltiples usuarios y operaciones concurrentes
✅ **Confiabilidad** - Transacciones ACID garantizan integridad de datos
✅ **Unicode Completo** - utf8mb4 soporta emojis y caracteres especiales
✅ **Producción Ready** - Configuración robusta para deployment
✅ **Backup y Replicación** - Características nativas de MariaDB
✅ **Performance** - Mejor que SQLite3 en operaciones I/O
✅ **Debugging** - Fácil acceso directo a datos vía CLI

## 🔗 Referencias

- [MariaDB Docs](https://mariadb.com/kb/en/documentation/)
- [Django Database Setup](https://docs.djangoproject.com/en/6.0/ref/settings/#databases)
- [MySQLdb](https://github.com/PyMySQL/mysqlclient)
- [Docker Compose](https://docs.docker.com/compose/)

## 📞 Soporte

Si encuentras problemas:

1. Ver logs del backend:
   ```bash
   docker-compose logs -f backend
   ```

2. Ver logs de MariaDB:
   ```bash
   docker-compose logs -f mariadb
   ```

3. Ejecutar verificación:
   ```bash
   python scripts/verify_mariadb.py
   ```

4. Reiniciar todo:
   ```bash
   docker-compose down -v
   docker-compose up -d
   ```

---

**Última actualización:** Abril 2026
**Estado:** ✅ Completado y verificado
