@echo off
REM ============================================================================
REM Script de inicialización de MariaDB para MCP Backend (Windows)
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ==========================================
echo Inicialización de MariaDB para MCP Backend
echo ==========================================
echo.

REM Configuración de variables
set DB_HOST=%DB_HOST:localhost%
set DB_PORT=%DB_PORT:3306%
set DB_NAME=%DB_NAME:mcp_db%
set DB_USER=%DB_USER:mcp_user%
set DB_PASSWORD=%DB_PASSWORD:mcp_secure_2026%

REM Verificar que Python está disponible
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Python no está instalado o no está en PATH
    exit /b 1
)

echo Información de configuración:
echo   Host: %DB_HOST%:%DB_PORT%
echo   Base de datos: %DB_NAME%
echo   Usuario: %DB_USER%
echo.

REM Ejecutar el script de inicialización Python
echo Ejecutando inicialización...
echo.

python scripts\init_mariadb.py

if %errorlevel% neq 0 (
    echo.
    echo Error: Fallo la inicialización
    exit /b 1
)

echo.
echo Inicialización completada exitosamente
echo.
pause
