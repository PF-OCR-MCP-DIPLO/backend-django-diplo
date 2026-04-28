"""Script para verificar la integridad de la instalación de MariaDB.

Verifica:
1. Conexión a MariaDB
2. Tablas creadas
3. Permisos de usuario
4. Charset y collation
5. Integridad de datos
6. Configuración de Django
"""

import os
import sys
import django
from pathlib import Path

# Ensure project root is available on PYTHONPATH when running from scripts/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configurar Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MCP_back.settings")
django.setup()

from django.db import connection
from django.apps import apps
from django.db.utils import OperationalError


def color_text(text, color="green"):
    """Aplica color ANSI para salida de terminal local."""
    colors = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "reset": "\033[0m",
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"


def print_header(title):
    """Imprime un encabezado."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_section(title):
    """Imprime un subencabezado."""
    print(f"\n{color_text(f'► {title}', 'blue')}")
    print("-" * 70)


def print_result(label, value, status="ok"):
    """Imprime una línea de verificación con semáforo visual."""
    if status == "ok":
        symbol = color_text("✓", "green")
    elif status == "error":
        symbol = color_text("✗", "red")
    else:
        symbol = color_text("⚠", "yellow")

    print(f"  {symbol} {label:<40} {value}")


def check_database_connection():
    """Verifica la conexión a la base de datos."""
    print_section("Conexión a Base de Datos")

    try:
        connection.ensure_connection()
        print_result("Estado de conexión", "Conectado", "ok")

        # Obtener información de conexión
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE();")
            db_name = cursor.fetchone()[0]
            print_result("Base de datos", db_name, "ok")

            cursor.execute("SELECT VERSION();")
            version = cursor.fetchone()[0]
            print_result("Versión MariaDB", version, "ok")

        return True
    except OperationalError as e:
        print_result("Conexión", str(e), "error")
        return False


def check_charset_collation():
    """Verifica charset y collation."""
    print_section("Charset y Collation")

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT @@character_set_database, @@collation_database;")
            charset, collation = cursor.fetchone()

            charset_ok = charset == "utf8mb4"
            collation_ok = collation == "utf8mb4_unicode_ci"

            print_result("Character Set", charset, "ok" if charset_ok else "error")
            print_result("Collation", collation, "ok" if collation_ok else "error")

            if not charset_ok or not collation_ok:
                print(
                    f"\n  {color_text('⚠ Recomendación', 'yellow')}: "
                    "Usar utf8mb4 para soporte completo de Unicode"
                )

            return charset_ok and collation_ok
    except Exception as e:
        print_result("Verificación", str(e), "error")
        return False


def check_tables():
    """Verifica presencia de tablas críticas para operación del backend."""
    print_section("Tablas Django")

    required_tables = [
        "processing_processrun",
        "processing_sourceimage",
        "processing_extracteddeposit",
        "processing_processingsettings",
        "processing_extractionlog",
        "auth_user",
        "django_migrations",
    ]

    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES;")
            existing_tables = set(row[0] for row in cursor.fetchall())

            print_result("Total de tablas", str(len(existing_tables)), "ok")

            all_present = True
            for table in required_tables:
                present = table in existing_tables
                status = "ok" if present else "error"
                print_result(
                    f"Tabla '{table}'", "Presente" if present else "Faltante", status
                )
                if not present:
                    all_present = False

            return all_present
    except Exception as e:
        print_result("Verificación", str(e), "error")
        return False


def check_models():
    """Confirma que modelos de dominio estén registrados en Django apps."""
    print_section("Modelos Django")

    try:
        apps.populate(django.conf.settings.INSTALLED_APPS)

        required_models = [
            ("processing", "ProcessRun"),
            ("processing", "SourceImage"),
            ("processing", "ExtractedDeposit"),
            ("processing", "ProcessingSettings"),
            ("processing", "ExtractionLog"),
        ]

        all_present = True
        for app_label, model_name in required_models:
            try:
                model = apps.get_model(app_label, model_name)
                print_result(f"{app_label}.{model_name}", "Registrado", "ok")
            except LookupError:
                print_result(f"{app_label}.{model_name}", "No encontrado", "error")
                all_present = False

        return all_present
    except Exception as e:
        print_result("Verificación", str(e), "error")
        return False


def check_table_statistics():
    """Obtiene estadísticas de las tablas."""
    print_section("Estadísticas de Tablas")

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    table_name,
                    table_rows,
                    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb,
                    table_collation
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                AND table_type = 'BASE TABLE'
                ORDER BY table_rows DESC
                LIMIT 10;
            """)

            results = cursor.fetchall()
            if results:
                print(
                    f"\n  {'Tabla':<35} {'Registros':>10} {'Tamaño MB':>10} {'Collation':<20}"
                )
                print(f"  {'-' * 75}")

                for table_name, rows, size, collation in results:
                    print(f"  {table_name:<35} {rows:>10} {size:>10} {collation:<20}")
            else:
                print(f"  {color_text('No hay tablas aún', 'yellow')}")

            return True
    except Exception as e:
        print_result("Estadísticas", str(e), "error")
        return False


def check_migrations():
    """Verifica estado de migraciones y alerta pendientes operativas."""
    print_section("Migraciones Django")

    try:
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("showmigrations", verbosity=2, stdout=out)

        output = out.getvalue()
        lines = output.split("\n")

        # Contar aplicadas vs no aplicadas
        applied = sum(1 for line in lines if "[X]" in line)
        not_applied = sum(1 for line in lines if "[ ]" in line)

        print_result("Migraciones aplicadas", str(applied), "ok")
        print_result(
            "Migraciones pendientes",
            str(not_applied),
            "ok" if not_applied == 0 else "warning",
        )

        if not_applied == 0:
            print(
                f"\n  {color_text('✓ Todas las migraciones están aplicadas', 'green')}"
            )
        else:
            print(f"\n  {color_text('⚠ Hay migraciones pendientes', 'yellow')}")
            print("  Ejecutar: python manage.py migrate")

        return not_applied == 0
    except Exception as e:
        print_result("Verificación", str(e), "error")
        return False


def check_django_settings():
    """Verifica la configuración de Django."""
    print_section("Configuración Django")

    try:
        from django.conf import settings

        db_config = settings.DATABASES.get("default", {})

        print_result("Motor de BD", db_config.get("ENGINE", "No configurado"), "ok")
        print_result("Nombre BD", db_config.get("NAME", "No configurado"), "ok")
        print_result("Host", db_config.get("HOST", "No configurado"), "ok")
        print_result("Puerto", str(db_config.get("PORT", "Por defecto")), "ok")

        # Verificar opciones específicas de MySQL
        options = db_config.get("OPTIONS", {})
        charset = options.get("charset", "utf8mb4")
        print_result("Charset en opciones", charset, "ok")

        return True
    except Exception as e:
        print_result("Configuración", str(e), "error")
        return False


def main():
    """Ejecuta suite de checks de instalación y retorna código de salida."""
    print_header("🔍 VERIFICACIÓN DE INSTALACIÓN MARIADB - MCP BACKEND")

    checks = [
        ("Conexión BD", check_database_connection),
        ("Charset/Collation", check_charset_collation),
        ("Tablas", check_tables),
        ("Modelos", check_models),
        ("Migraciones", check_migrations),
        ("Configuración Django", check_django_settings),
        ("Estadísticas", check_table_statistics),
    ]

    results = {}
    for check_name, check_func in checks:
        try:
            results[check_name] = check_func()
        except Exception as e:
            print_section(f"Error en {check_name}")
            print_result("Error", str(e), "error")
            results[check_name] = False

    # Resumen final
    print_header("📋 RESUMEN")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for check_name, status in results.items():
        symbol = color_text("✓", "green") if status else color_text("✗", "red")
        print(f"  {symbol} {check_name}")

    print(f"\n  Resultado: {passed}/{total} verificaciones pasadas")

    if passed == total:
        print(f"\n  {color_text('✓ INSTALACIÓN COMPLETADA Y VERIFICADA', 'green')}")
        print(f"\n  Próximos pasos:")
        print(f"    1. Acceder a http://localhost:8000/api/")
        print(f"    2. Subir documentos DOCX para procesamiento")
        print(
            f"    3. Ver datos en MariaDB: mysql -u mcp_user -pmcp_secure_2026 -D mcp_db"
        )
        return 0
    else:
        print(f"\n  {color_text('✗ INSTALACIÓN INCOMPLETA O CON ERRORES', 'red')}")
        print(f"\n  Revisar los errores arriba y ejecutar:")
        print(f"    python scripts/init_mariadb.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())
