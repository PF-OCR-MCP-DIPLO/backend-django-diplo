#!/bin/bash
# ============================================================================
# Script de inicialización de MariaDB para el proyecto MCP
# 
# Este script configura la base de datos MariaDB, ejecuta migraciones Django
# y prepara el sistema para procesamiento OCR/LLM.
# ============================================================================

set -e

echo "=========================================="
echo "Inicializando MariaDB para MCP Backend"
echo "=========================================="

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuración de variables
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-mcp_db}"
DB_USER="${DB_USER:-mcp_user}"
DB_PASSWORD="${DB_PASSWORD:-mcp_secure_2026}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-root_mcp_2026}"
DJANGO_MANAGE="python manage.py"

# Función para esperar a que MariaDB esté disponible
wait_for_mariadb() {
    echo -e "${YELLOW}Esperando a que MariaDB esté disponible en ${DB_HOST}:${DB_PORT}...${NC}"
    
    for i in {1..30}; do
        if mysql -h "${DB_HOST}" -P "${DB_PORT}" -u root -p"${DB_ROOT_PASSWORD}" -e "SELECT 1" &> /dev/null; then
            echo -e "${GREEN}MariaDB está disponible${NC}"
            return 0
        fi
        echo "Intento $i/30..."
        sleep 2
    done
    
    echo -e "${RED}Error: No se pudo conectar a MariaDB${NC}"
    return 1
}

# Función para crear base de datos y usuario
setup_database() {
    echo -e "${YELLOW}Configurando base de datos MariaDB...${NC}"
    
    mysql -h "${DB_HOST}" -P "${DB_PORT}" -u root -p"${DB_ROOT_PASSWORD}" << EOF
-- Crear base de datos si no existe
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` 
    CHARACTER SET utf8mb4 
    COLLATE utf8mb4_unicode_ci;

-- Crear usuario si no existe
CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}';

-- Otorgar permisos
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'%';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';

-- Aplicar cambios
FLUSH PRIVILEGES;

-- Mostrar información de configuración
SELECT '========== INFORMACIÓN DE BASE DE DATOS ==========' as INFO;
SELECT CONCAT('Base de datos: ', '${DB_NAME}') as SETTING;
SELECT CONCAT('Usuario: ', '${DB_USER}') as SETTING;
SELECT CONCAT('Host: ', '${DB_HOST}', ':', '${DB_PORT}') as SETTING;
EOF

    echo -e "${GREEN}Base de datos configurada correctamente${NC}"
}

# Función para ejecutar migraciones
run_migrations() {
    echo -e "${YELLOW}Ejecutando migraciones Django...${NC}"
    
    # Crear migraciones iniciales (si es necesario)
    echo "Creando archivos de migración..."
    $DJANGO_MANAGE makemigrations --noinput
    
    # Aplicar migraciones
    echo "Aplicando migraciones a la base de datos..."
    $DJANGO_MANAGE migrate --noinput
    
    echo -e "${GREEN}Migraciones completadas${NC}"
}

# Función para crear superusuario (opcional)
create_superuser() {
    echo -e "${YELLOW}Creando superusuario (opcional)...${NC}"
    
    # Este comando será interactivo
    $DJANGO_MANAGE createsuperuser --noinput \
        --username=admin \
        --email=admin@mcp.local || echo "Superusuario ya existe o no se pudo crear"
}

# Función para cargar datos iniciales (si existen)
load_initial_data() {
    echo -e "${YELLOW}Buscando datos iniciales para cargar...${NC}"
    
    # Buscar fixtures en apps
    if find . -name "*.json" -path "*/fixtures/*" | grep -q .; then
        echo "Cargando fixtures..."
        $DJANGO_MANAGE loaddata $(find . -name "*.json" -path "*/fixtures/*" | head -5) || true
    else
        echo "No se encontraron fixtures para cargar"
    fi
}

# Función para verificar integridad de tablas
verify_tables() {
    echo -e "${YELLOW}Verificando integridad de tablas...${NC}"
    
    mysql -h "${DB_HOST}" -P "${DB_PORT}" -u "${DB_USER}" -p"${DB_PASSWORD}" "${DB_NAME}" << EOF
-- Mostrar tablas creadas
SHOW TABLES;

-- Mostrar charset y collation de la base de datos
SELECT @@character_set_database, @@collation_database;

-- Mostrar información de almacenamiento
SELECT 
    table_name,
    table_rows,
    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb,
    table_collation
FROM information_schema.tables
WHERE table_schema = '${DB_NAME}'
ORDER BY table_name;
EOF

    echo -e "${GREEN}Verificación completada${NC}"
}

# ============================================================================
# FLUJO PRINCIPAL
# ============================================================================

# Ejecutar funciones en orden
wait_for_mariadb || exit 1
setup_database
run_migrations
verify_tables

echo ""
echo -e "${GREEN}=========================================="
echo "Inicialización completada exitosamente"
echo "==========================================${NC}"
echo ""
echo "Información de conexión:"
echo "  Host: $DB_HOST:$DB_PORT"
echo "  Base de datos: $DB_NAME"
echo "  Usuario: $DB_USER"
echo ""
echo "Próximos pasos:"
echo "  1. Verificar que las tablas estén creadas correctamente"
echo "  2. Acceder a la UI en http://localhost:5173"
echo "  3. Subir documentos DOCX para procesamiento OCR"
echo ""
