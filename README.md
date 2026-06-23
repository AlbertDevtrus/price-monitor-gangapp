# Price Monitor — Alertas de Ofertas

Monitorea precios en marketplaces y te **avisa por Telegram** cuando aparece una buena
oferta. Pensado para uso personal, con arquitectura lista para crecer.

## ¿Qué hace?

1. **Scrapea** productos de uno o más marketplaces con Scrapy.
2. **Guarda** el historial de precios en PostgreSQL (un registro por cambio de precio).
3. **Evalúa alertas** en cada cambio de precio según 3 criterios configurables.
4. **Notifica** por Telegram cuando un producto califica como oferta.
5. **Se ejecuta solo** en intervalos definidos vía un scheduler.

## Arquitectura

```
backend/
├── models/                  # SQLAlchemy ORM
│   ├── platform.py          # Marketplace
│   ├── product.py           # Producto (con `location` para ventas locales)
│   ├── price_history.py     # Historial de precios
│   └── alert.py             # Alertas de ofertas
├── alerts/
│   └── evaluator.py         # Lógica pura "¿es una buena oferta?" (+ tests)
├── notifications/
│   └── telegram.py          # Cliente ligero de Telegram (httpx)
├── scheduler.py             # APScheduler: corre los spiders cada N horas
├── create_tables.py         # Crea el esquema en la DB
└── scrapers/price_scrapers/
    ├── base_spiders.py      # BaseMarketplaceSpider (clase abstracta)
    ├── items.py             # ProductScraped (validación Pydantic)
    ├── pipelines.py         # DatabasePipeline: guarda precios + dispara alertas
    └── spiders/
        ├── mercadolibre_spider.py  # vía Playwright (navegador real)
        └── craigslist_spider.py    # vía RSS
```

**Flujo:** spider → `ProductScraped` (validado) → `DatabasePipeline` → guarda precio →
si cambió, evalúa alertas activas → si califica, envía Telegram.

## Stack

Python 3.13 · Scrapy · scrapy-playwright (navegador real) · SQLAlchemy 2.0 ·
PostgreSQL 16 · Pydantic · APScheduler · httpx · uv (gestión de dependencias) ·
Docker Compose.

## Setup

### 1. Base de datos

```bash
docker compose up -d postgres        # PostgreSQL en localhost:5432
# (opcional) pgAdmin en http://localhost:5050
docker compose up -d pgadmin
```

### 2. Variables de entorno

Copia `.env.example` a `.env` y complétalo:

```ini
DATABASE_URL=postgresql+psycopg2://priceuser:pricepass@localhost:5432/price_monitor
POSTGRES_USER=priceuser
POSTGRES_PASSWORD=pricepass
POSTGRES_DB=price_monitor

TELEGRAM_BOT_TOKEN=         # token de @BotFather
TELEGRAM_DEFAULT_CHAT_ID=   # tu chat id (ver abajo)
```

> **Telegram:** crea un bot con [@BotFather](https://t.me/BotFather) para el token.
> Para el `chat_id`: escríbele cualquier mensaje a tu bot y abre
> `https://api.telegram.org/bot<TOKEN>/getUpdates`, busca `"chat":{"id":...}`.
> **Importante:** debes escribirle al bot al menos una vez, si no Telegram responde
> `chat not found`.

### 3. Dependencias y esquema

```bash
cd backend
uv sync                          # instala dependencias
uv run playwright install chromium   # navegador real (necesario para Mercado Libre)
uv run python create_tables.py   # crea las tablas
```

## Uso

### Crear una alerta

Inserta una fila en la tabla `alerts` (vía pgAdmin o psql). Los criterios son
opcionales y se combinan con **OR** (basta que uno se cumpla):

| Campo | Significado |
|---|---|
| `label` | Nombre descriptivo |
| `search_query` | Término que debe aparecer en el título del producto |
| `platform_id` | Plataforma específica, o `NULL` = todas |
| `max_price` | Alerta si el precio ≤ este valor |
| `min_drop_pct` | Alerta si el precio cae ≥ esta fracción (ej. `0.20` = 20%) |
| `below_avg_pct` | Alerta si el precio ≤ promedio histórico × (1 − esta fracción) |
| `telegram_chat_id` | Destino (si es `NULL` usa `TELEGRAM_DEFAULT_CHAT_ID`) |
| `is_active` | `true`/`false` |

Ejemplo:

```sql
INSERT INTO alerts (label, search_query, is_active, max_price, min_drop_pct)
VALUES ('Laptop gamer barata', 'laptop gamer', true, 15000, 0.15);
```

Anti-spam: una alerta no se vuelve a disparar dentro de las 6 horas
(`last_triggered_at`).

### Correr un spider manualmente

```bash
cd backend/scrapers
# Mercado Libre usa navegador real; su robots.txt prohíbe los listados,
# así que se corre con ROBOTSTXT_OBEY=False (uso personal).
uv run scrapy crawl mercadolibre -a search_query=iphone -s ROBOTSTXT_OBEY=False
uv run scrapy crawl craigslist  -a search_query=bicycle -a site=newyork
```

### Automatizar (scheduler)

```bash
cd backend
uv run python scheduler.py    # corre los spiders cada 12h (configurable)
```

### Tests

```bash
cd backend
uv run --with pytest python -m pytest alerts/test_evaluator.py -q
```

## Anti-bot: estado y estrategia

Los marketplaces protegen sus listados contra scraping. Estado verificado (2026-06):

- **Mercado Libre** → ✅ **funciona** con `scrapy-playwright` (navegador real Chromium).
  Por HTTP simple redirige a `account-verification`/captcha, pero el navegador real
  carga los listados. ML muestra un **muro de captcha intermitente**; se mitiga con:
  contexto de navegador **persistente** (cookies que generan confianza, guardadas en
  `backend/scrapers/.pw_state/`), opciones **anti-detección de headless** y **reintento**
  al detectar el muro. Confiabilidad medida: ~3/3 corridas exitosas.
- **OLX MX** → ❌ el dominio `olx.com.mx` ya **no existe** (OLX cerró en México). Spider
  eliminado.
- **Vivanuncios** → ⚠️ **pivoteó a solo bienes raíces**; no sirve para productos. Spider
  eliminado.
- **Craigslist** → ⚠️ 403 por IP de datacenter (US-céntrico). Se conserva el spider; podría
  funcionar más adelante vía Playwright.

Si la confiabilidad de ML baja, los siguientes escalones son: modo **headful**, un plugin
**stealth**, o **proxies residenciales** (de pago).

## Roadmap

- [x] **scrapy-playwright**: navegador real integrado; Mercado Libre scrapea datos reales.
- [ ] **Facebook Marketplace**: spider con Playwright + cuenta dedicada (login manual una
      vez, sesión persistida con cookies).
- [ ] **Retail**: spiders de Amazon MX y Walmart MX.
- [ ] Migrar `start_requests()` → `start()` (deprecado en Scrapy 2.13).
- [ ] API (FastAPI) y/o frontend si se abre la app a más usuarios.
- [ ] Celery + Redis en lugar de APScheduler para escalar el scheduling.

## Notas de desarrollo

- Estilo: `black` (88 cols) + `ruff`.
- Agregar un marketplace nuevo (HTML estándar) = crear una clase que herede de
  `BaseMarketplaceSpider` e implementar los métodos `extract_*` y `build_page_url`.
  El pipeline lo integra automáticamente.
