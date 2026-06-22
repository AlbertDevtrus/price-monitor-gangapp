# Backend

Backend de scraping + alertas. La documentación completa (setup, uso, arquitectura)
está en el [README raíz](../README.md).

Comandos rápidos (desde `backend/`):

```bash
uv sync                                # dependencias
uv run python create_tables.py         # crea el esquema
uv run python scheduler.py             # scheduler automático
cd scrapers && uv run scrapy list      # spiders disponibles
```
