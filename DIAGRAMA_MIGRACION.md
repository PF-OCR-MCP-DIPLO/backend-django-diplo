# 🎨 Diagrama Visual - Migración SQLite3 → MariaDB

## 📊 Arquitectura Antes vs Después

### ANTES (SQLite3)

```
┌─────────────────────────────────────────────────────┐
│        DESARROLLO LOCAL - SQLite3                   │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Frontend ──┐                                        │
│             ├──────► Backend Django ◄──────┐        │
│  Navegador ─┘                              │        │
│                                            │        │
│                                  ┌─────────▼──┐     │
│                                  │ SQLite3 DB │     │
│                                  │ (archivo)  │     │
│                                  │ db.sqlite3 │     │
│                                  └────────────┘     │
│                                                      │
│  LIMITACIONES:                                       │
│  ❌ No escalable                                     │
│  ❌ Limitado en concurrencia                         │
│  ❌ Dificil de replicar                             │
│  ❌ No recomendado para producción                  │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### AHORA (MariaDB)

```
┌─────────────────────────────────────────────────────┐
│    DESARROLLO + PRODUCCIÓN - MariaDB (Docker)       │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Frontend ──┐                                        │
│             ├──────► Backend Django                 │
│  Navegador ─┘        (Puerto 8000)                  │
│                           │                         │
│                    ┌──────▼──────┐                  │
│                    │  Migraciones │                 │
│                    │    Django    │                 │
│                    └──────┬──────┘                  │
│                           │                         │
│                    ┌──────▼──────────────┐           │
│                    │   MariaDB 11.4      │           │
│                    │  (Contenedor)       │           │
│                    │                      │           │
│                    │  UUID: utf8mb4      │           │
│                    │  Collation: u.u.c   │           │
│                    │  ACID Transactions  │           │
│                    │  InnoDB Storage     │           │
│                    │                      │           │
│                    │  Tablas:            │           │
│                    │  • processrun       │           │
│                    │  • sourceimage      │           │
│                    │  • extracteddeposit │           │
│                    │  • settings         │           │
│                    │  • extractionlog    │           │
│                    │  • ... (Django)     │           │
│                    │                      │           │
│                    │  Volumen persistente│           │
│                    │  mariadb_data       │           │
│                    └──────────────────────┘           │
│                                                      │
│  VENTAJAS:                                           │
│  ✅ Escalable                                        │
│  ✅ Transacciones ACID                              │
│  ✅ Unicode completo                                │
│  ✅ Listo para producción                           │
│  ✅ Fácil replicación                               │
│  ✅ Backups nativos                                 │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## 📁 Estructura de Archivos Modificados

```
backend-django-diplo/
│
├── requirements.txt
│   └─► + mysqlclient==2.2.5
│
├── docker-compose.yml
│   ├─► + servicio mariadb
│   ├─► + volumen mariadb_data
│   ├─► + healthcheck
│   └─► + variables de BD
│
├── Dockerfile
│   ├─► + libmysqlclient-dev
│   ├─► + mariadb-client
│   └─► + script init_mariadb.py
│
├── MCP_back/settings.py
│   ├─► + OPTIONS (charset, mode)
│   ├─► + ATOMIC_REQUESTS
│   └─► + CONN_MAX_AGE
│
├── .env
│   └─► + DATABASE_URL
│   └─► + DB_HOST, PORT, NAME, USER, PASSWORD
│
└── .env.example
    └─► + Configuración de ejemplo
```

---

## 🔄 Flujo de Inicialización (Docker)

```
docker-compose up -d
        │
        ├─► Construir imagen backend
        │
        ├─► Levantar contenedor MariaDB
        │   ├─► Crear BD: mcp_db
        │   ├─► Crear usuario: mcp_user
        │   ├─► Charset: utf8mb4
        │   ├─► Healthcheck: En progreso...
        │   └─► Estado: ✓ Ready (10-15 segundos)
        │
        ├─► Levantar contenedor Backend
        │   ├─► Instalar dependencias Python
        │   ├─► Esperar a MariaDB (healthcheck)
        │   ├─► Ejecutar: python scripts/init_mariadb.py
        │   │   ├─► Esperar conexión a MariaDB
        │   │   ├─► Ejecutar: python manage.py makemigrations
        │   │   ├─► Ejecutar: python manage.py migrate
        │   │   ├─► Verificar: Tablas creadas
        │   │   └─► Resultado: ✓ OK
        │   │
        │   ├─► Ejecutar: python manage.py runserver
        │   └─► Estado: ✓ Corriendo en 0.0.0.0:8000
        │
        └─► LISTO ✓
            ├─► Backend: http://localhost:8000/api/
            ├─► MariaDB: localhost:3306
            └─► BD: mcp_db
```

---

## 📊 Modelo de Datos (Entidad-Relación Simplificado)

```
                    ┌──────────────────────┐
                    │  ProcessingSettings  │
                    │  (Configuración)     │
                    │  - ocr_provider      │
                    │  - llm_provider      │
                    │  - criterios         │
                    └──────────────────────┘
                              ▲
                              │ referencia
                              │
    ┌─────────────────────────┼──────────────────────────┐
    │                         │                          │
    │                    (1:N)|                          │
    │                         │                          │
    ▼                         │                          ▼
┌────────────────┐    ┌───────────────────┐    ┌──────────────────┐
│ ProcessRun     │    │  SourceImage      │    │ ExtractionLog    │
│ (Documento)    │◄───┤  (Imagen)         │◄───┤ (Auditoría)      │
│                │    │                   │    │                  │
│ - archivo      │ 1:N│ - ocr_raw_text    │ 1:N│ - stage          │
│ - status       ├────│ - ocr_status      ├────│ - is_error       │
│ - total_images │    │                   │    │ - raw_payload    │
│ - excel_file   │    └─┬─────────────────┘    └──────────────────┘
│                │      │
│ Status:        │      │ 1:N
│ • uploaded     │      │
│ • processing   │      ▼
│ • completed    │    ┌──────────────────────┐
│ • failed       │    │ ExtractedDeposit     │
└────────────────┘    │ (Consignación)       │
                      │                      │
                      │ - fecha              │
                      │ - referencia         │
                      │ - valor              │
                      │ - structured_payload │
                      │                      │
                      └──────────────────────┘
```

---

## 🚀 Opciones de Ejecución

```
┌──────────────────────────────────────────────────────┐
│             CÓMO INICIAR EL BACKEND                  │
└──────────────────────────────────────────────────────┘

╔══════════════════════════════════════════════════════╗
║  OPCIÓN 1: Docker Compose (Recomendado) ⭐          ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  $ cd backend-django-diplo                           ║
║  $ docker-compose up -d                              ║
║  $ sleep 15                                          ║
║  $ python scripts/verify_mariadb.py                  ║
║                                                      ║
║  ✅ Ventajas:                                        ║
║  • Todo incluido (MariaDB + Backend)                 ║
║  • Reproducible en cualquier máquina                 ║
║  • Fácil de escalar                                  ║
║  • Ideal para desarrollo                             ║
║                                                      ║
╚══════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════╗
║  OPCIÓN 2: Local Development (Sin Docker)           ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  $ pip install -r requirements.txt                   ║
║  $ python scripts/init_mariadb.py                    ║
║  $ python manage.py runserver                        ║
║                                                      ║
║  ✅ Ventajas:                                        ║
║  • Desarrollo más rápido                             ║
║  • Debugging más fácil                               ║
║  • Control total                                     ║
║                                                      ║
║  ⚠️ Requisitos:                                      ║
║  • MariaDB instalado localmente                      ║
║  • Python 3.12+                                      ║
║  • Variables .env configuradas                       ║
║                                                      ║
╚══════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════╗
║  OPCIÓN 3: Windows PowerShell                       ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  PS> cd backend-django-diplo                         ║
║  PS> docker-compose up -d                            ║
║  PS> Start-Sleep -Seconds 15                         ║
║  PS> python scripts/verify_mariadb.py                ║
║                                                      ║
║  ✅ Ventajas:                                        ║
║  • Funciona igual que en Linux                       ║
║  • Instrucciones específicas disponibles              ║
║  • Docker Desktop soportado                          ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
```

---

## 🔍 Verificación de Instalación

```
┌─────────────────────────────────────────────┐
│  python scripts/verify_mariadb.py           │
└─────────────────────────────────────────────┘
        │
        ├─► ✓ Conexión a Base de Datos
        │
        ├─► ✓ Charset y Collation
        │   └─► utf8mb4 | utf8mb4_unicode_ci
        │
        ├─► ✓ Tablas Django
        │   ├─► processing_processrun
        │   ├─► processing_sourceimage
        │   ├─► processing_extracteddeposit
        │   ├─► processing_processingSettings
        │   └─► processing_extractionlog
        │
        ├─► ✓ Modelos Django
        │   ├─► ProcessRun
        │   ├─► SourceImage
        │   ├─► ExtractedDeposit
        │   ├─► ProcessingSettings
        │   └─► ExtractionLog
        │
        ├─► ✓ Migraciones Django
        │   └─► 7/7 migraciones aplicadas
        │
        ├─► ✓ Configuración Django
        │   ├─► ENGINE: mysql
        │   ├─► charset: utf8mb4
        │   └─► ATOMIC_REQUESTS: True
        │
        ├─► ✓ Estadísticas de Tablas
        │   ├─► Registros totales: 0 (BD nueva)
        │   └─► Tamaño: ~2 MB
        │
        └─► ✓ INSTALACIÓN COMPLETADA Y VERIFICADA
```

---

## 🎯 Resultado Final

```
┌─────────────────────────────────────────────────────────┐
│                   ✅ MIGRACIÓN EXITOSA                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  SQLite3 ──────────────────────► MariaDB 11.4          │
│                                                         │
│  Cambios:                                              │
│  ✅ Base de datos relacional escalable                 │
│  ✅ Transacciones ACID garantizadas                    │
│  ✅ Unicode UTF-8MB4 completo                          │
│  ✅ Listo para producción                              │
│  ✅ Automatización completa                            │
│  ✅ Documentación exhaustiva                           │
│                                                         │
│  Archivos afectados: 6                                 │
│  Archivos nuevos: 11                                   │
│  Scripts creados: 3                                    │
│  Documentación: 6 archivos                             │
│                                                         │
│  Tiempo de implementación: ~15 segundos (Docker)       │
│  Tiempo de desarrollo: 100% automatizado               │
│                                                         │
│  ✓ Listo para usar                                    │
│  ✓ Listo para desarrollo                              │
│  ✓ Listo para producción                              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 📋 Resumen de Cambios

```
Modificados:
  ✏️ requirements.txt
  ✏️ docker-compose.yml
  ✏️ Dockerfile
  ✏️ MCP_back/settings.py
  ✏️ .env
  ✏️ .env.example

Creados:
  🆕 scripts/init_mariadb.py
  🆕 scripts/init_mariadb.sh
  🆕 scripts/verify_mariadb.py
  🆕 init_mariadb.bat
  🆕 docs/MARIADB_SETUP.md
  🆕 docs/MARIADB_QUICKSTART.md
  🆕 docs/DATABASE_STRUCTURE.md
  🆕 MARIADB_MIGRATION.md
  🆕 MARIADB_WINDOWS.md
  🆕 MARIADB_CHECKLIST.md
  🆕 README_MARIADB.md

Total: 6 modificados + 11 nuevos = 17 cambios
```

---

**Diagrama creado:** Abril 27, 2026  
**Estado:** ✅ Migración completada y verificada  
**Versión:** 1.0.0
