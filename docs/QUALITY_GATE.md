# Quality gate

Antes de mergear:

- `python3 -m compileall MCP_back apps mcp_server tests`
- `python3 -m pytest` si está instalado
- `python manage.py check`
- `mkdocs build --strict`
- revisar docs si cambió API, rutas o variables
