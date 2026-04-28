"""Script de inicialización de base de datos MariaDB para el backend MCP.

Ejecuta automáticamente:
1. Espera a que MariaDB esté disponible
2. Ejecuta migraciones Django
3. Verifica la integridad de las tablas
4. Carga datos iniciales (si existen)
"""

import os
import sys
import django
import subprocess
import time
from pathlib import Path

# Ensure project root is available on PYTHONPATH when running from scripts/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configurar Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MCP_back.settings")
django.setup()

# Importar después de setup
from django.core.management import call_command
from django.db import connection
from django.db.utils import OperationalError


def wait_for_database(max_retries=30, retry_delay=2):
    """Espera a que la base de datos esté disponible."""
    print("⏳ Esperando a que MariaDB esté disponible...")

    for attempt in range(max_retries):
        try:
            connection.ensure_connection()
            print("✅ Base de datos disponible")
            return True
        except OperationalError as e:
            if attempt < max_retries - 1:
                print(
                    f"   Intento {attempt + 1}/{max_retries} fallido. Reintentando en {retry_delay}s..."
                )
                time.sleep(retry_delay)
            else:
                print(
                    f"❌ Error: No se pudo conectar a la base de datos después de {max_retries} intentos"
                )
                print(f"   Detalles: {str(e)}")
                return False

    return False


def run_migrations():
    """Ejecuta las migraciones de Django."""
    print("\n📋 Ejecutando migraciones Django...")

    try:
        # Crear migraciones si es necesario
        print("   Creando archivos de migración...")
        call_command("makemigrations", verbosity=1)

        # Aplicar migraciones
        print("   Aplicando migraciones a la base de datos...")
        call_command("migrate", verbosity=1)
        print("✅ Migraciones completadas")
        return True
    except Exception as e:
        print(f"❌ Error al ejecutar migraciones: {str(e)}")
        return False


def verify_tables():
    """Verifica la integridad de las tablas creadas."""
    print("\n📊 Verificando integridad de tablas...")

    try:
        with connection.cursor() as cursor:
            # Obtener lista de tablas
            cursor.execute("SHOW TABLES;")
            tables = [row[0] for row in cursor.fetchall()]

            print(f"   Tablas creadas: {len(tables)}")
            for table in sorted(tables):
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`;")
                count = cursor.fetchone()[0]
                print(f"      - {table}: {count} registros")

            # Verificar charset
            cursor.execute("SELECT @@character_set_database, @@collation_database;")
            charset, collation = cursor.fetchone()
            print(f"   Charset: {charset}")
            print(f"   Collation: {collation}")

            print("✅ Verificación completada")
            return True
    except Exception as e:
        print(f"❌ Error al verificar tablas: {str(e)}")
        return False


def load_initial_data():
    """Carga datos iniciales si existen fixtures."""
    print("\n📁 Cargando datos iniciales...")

    try:
        fixtures_path = Path(__file__).parent.parent
        fixtures = list(fixtures_path.glob("*/fixtures/*.json"))

        if fixtures:
            print(f"   Encontradas {len(fixtures)} fixtures")
            fixture_names = [
                str(f.relative_to(fixtures_path.parent)) for f in fixtures[:5]
            ]
            call_command("loaddata", *fixture_names, verbosity=1)
            print("✅ Datos iniciales cargados")
        else:
            print("   No se encontraron fixtures")

        return True
    except Exception as e:
        print(f"⚠️  No se pudieron cargar datos iniciales: {str(e)}")
        return True  # No fallar si no hay fixtures


def check_requirements():
    """Verifica que las dependencias necesarias estén instaladas."""
    print("🔍 Verificando dependencias...")

    try:
        import MySQLdb

        print("✅ MySQLdb (mysqlclient) disponible")
    except ImportError:
        print("❌ Error: mysqlclient no está instalado")
        print("   Ejecuta: pip install mysqlclient")
        return False

    return True


def main():
    """Función principal."""
    print("=" * 60)
    print("Inicialización de MariaDB para MCP Backend")
    print("=" * 60)
    print()

    # Verificar dependencias
    if not check_requirements():
        return 1

    # Esperar a que la base de datos esté disponible
    if not wait_for_database():
        return 1

    # Ejecutar migraciones
    if not run_migrations():
        return 1

    # Verificar integridad
    if not verify_tables():
        return 1

    # Cargar datos iniciales
    load_initial_data()

    print("\n" + "=" * 60)
    print("✅ Inicialización completada exitosamente")
    print("=" * 60)
    print("\nInformación de conexión:")
    print(f"  Host: {os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '3306')}")
    print(f"  Base de datos: {os.getenv('DB_NAME', 'mcp_db')}")
    print(f"  Usuario: {os.getenv('DB_USER', 'mcp_user')}")
    print("\nPróximos pasos:")
    print("  1. Verificar que el backend esté corriendo en http://localhost:8000")
    print("  2. Acceder a la UI en http://localhost:5173")
    print("  3. Subir documentos DOCX para procesamiento OCR")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
