---
name: nolan-research
description: Ciclo de investigación de Nolan. Scrapea Apify (IG/TikTok benchmarks), lee RSS, consulta Perplexity y Google Trends; deduplica; escribe señales a memory/trends.sqlite. Se invoca en L-W-V 6AM por cron Hermes, o bajo demanda con /tema. Devuelve shortlist top 3 por nicho.
version: 0.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [research, sapiens, nolan]
    category: sapiens
    requires_toolsets: [terminal, http]
---

# nolan-research

Ciclo de ingesta de señales de tendencia para educación e IA en Colombia. Produce una shortlist top-3 por nicho (padres, jovenes_preicfes, adultos_ia, pymes) con justificación breve.

## When to use

- Cron L-W-V 06:00 Bogotá — ciclo automático.
- Usuario envía `/tema <descripción>` — research on-demand sobre un tema específico.
- Tras un rechazo múltiple, Nolan re-corre research con parámetros ajustados.

## Procedure

1. **Cargar config**: `config/sources.yaml`, `config/benchmarks.yaml`, `config/cadence.yaml`.
2. **Fan-out paralelo** (delegación a subagentes):
   - `apify_scrape_ig` — últimas 20 publicaciones de cada benchmark_handle.
   - `apify_scrape_tt` — últimos 15 videos TikTok (cadencia 72h).
   - `rss_poll` — feeds oficiales (cada 4h de cadencia).
   - `perplexity_news` — 5 queries predefinidas, filtro recency=week.
   - `google_trends` — keywords CO, rising queries.
3. **Normalizar + dedupe**: `sha256(normalize(title) + canonical_url)` → drop duplicados.
4. **Clasificar nicho** por señal (task: `research.classify_niche` → DeepSeek).
5. **Clusterizar temas similares** (task: `research.dedupe_cluster`).
6. **Puntuar shortlist** (task: `strategy.score_topics`):
   - novedad (≤72h para news, ≤7d para trends)
   - relevancia al nicho (weighted por `cadence.yaml.niche_mix_weekly`)
   - fit con SOUL (si un tema pide copy imposible de pasar ethics, penalizar)
   - evidencia disponible (citas, datos, autoridad)
7. **Escribir** a `memory/trends.sqlite.signals_*` (append-only, hash indexado).
8. **Devolver** shortlist `{tema, nicho, score, fuentes[], formato_sugerido, estimated_ethics_risk}`.

## Tools / scripts

- `scripts/apify_client.py` — wrapper sobre apify-client SDK con retry + budget tracking
- `scripts/rss_reader.py` — feedparser + normalización
- `scripts/perplexity_client.py` — httpx async con return_citations=true
- `scripts/google_trends.py` — pytrends wrapper CO geo
- `scripts/dedupe.py` — hash + cluster
- `scripts/source_discovery.py` — weekly, propone fuentes nuevas a aprobar

## Pitfalls

- **Apify quota**: máx 20 runs/semana. `budget_guard` debe preflight antes de cada run.
- **Perplexity citaciones vacías**: si el JSON devuelve `citations: []`, tratar como señal débil (score × 0.5). No publicar piezas basadas SOLO en una fuente Perplexity sin citaciones.
- **RSS feeds rotos**: fail-soft. Log WARN, no bloquear el ciclo completo.
- **Google Trends rate limit**: pytrends fallará silenciosamente si se pasa; usar backoff 60s entre keywords.

## Verification

```bash
hermes chat "ejecuta research.ciclo_manual --nichos padres,jovenes_preicfes --dry-run"
# Esperado: shortlist JSON de 6 temas (3 por nicho) impreso, trends.sqlite actualizado,
# logs/research.log con trazas por fuente, costo < $0.20.

sqlite3 memory/trends.sqlite "SELECT COUNT(*), nicho FROM signals_clustered GROUP BY nicho;"
```

## Outputs

- `memory/trends.sqlite` — append
- `logs/research.log` — trace de ciclo
- Return value (a Hermes): shortlist JSON para `nolan-decide-format`
