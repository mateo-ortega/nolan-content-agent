-- trends.sqlite — señales de investigación de Nolan
-- Motor: SQLite 3.x
-- Append-only: nunca UPDATE/DELETE en tablas signals_*
-- Ejecutar: sqlite3 memory/trends.sqlite < memory/schemas/trends.sql

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- =========================================================================
-- Señales crudas por fuente
-- =========================================================================

CREATE TABLE IF NOT EXISTS signals_ig (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_norm   TEXT    NOT NULL UNIQUE,          -- sha256(normalize(title)+canonical_url)
    source      TEXT    NOT NULL,                 -- handle IG
    post_url    TEXT    NOT NULL,
    caption     TEXT,
    hook_text   TEXT,                             -- primera línea del caption
    likes       INTEGER DEFAULT 0,
    comments    INTEGER DEFAULT 0,
    followers   REAL    DEFAULT 0,
    engagement  REAL GENERATED ALWAYS AS (
                    CASE WHEN followers > 0
                    THEN (likes + comments) * 1.0 / followers
                    ELSE 0 END) VIRTUAL,
    format      TEXT,                             -- reel | carrusel_N | story
    scraped_at  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS signals_tt (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_norm   TEXT    NOT NULL UNIQUE,
    source      TEXT    NOT NULL,
    video_url   TEXT    NOT NULL,
    description TEXT,
    hook_text   TEXT,
    plays       INTEGER DEFAULT 0,
    likes       INTEGER DEFAULT 0,
    shares      INTEGER DEFAULT 0,
    duration_s  REAL,
    scraped_at  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS signals_rss (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_norm   TEXT    NOT NULL UNIQUE,
    feed_name   TEXT    NOT NULL,
    feed_url    TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    link        TEXT    NOT NULL,
    summary     TEXT,
    published   TEXT,
    tags        TEXT,                             -- JSON array de tags del feed
    scraped_at  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS signals_news (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_norm   TEXT    NOT NULL UNIQUE,
    query       TEXT    NOT NULL,                 -- query de Perplexity que la originó
    title       TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    snippet     TEXT,
    citations   TEXT,                             -- JSON array de citaciones
    low_confidence INTEGER DEFAULT 0,             -- 1 si citations vacías
    published   TEXT,
    scraped_at  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS signals_trends (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT    NOT NULL,
    geo         TEXT    NOT NULL DEFAULT 'CO',
    interest    INTEGER,                          -- valor 0-100 de Google Trends
    rising_pct  REAL,                             -- % de aumento (rising queries)
    related     TEXT,                             -- JSON array de related queries
    scraped_at  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(keyword, geo, scraped_at)
);

-- =========================================================================
-- Señales normalizadas y clusterizadas (output de research.dedupe_cluster)
-- =========================================================================

CREATE TABLE IF NOT EXISTS signals_clustered (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id      TEXT    NOT NULL,             -- uuid del cluster
    nicho           TEXT    NOT NULL,             -- jovenes_preicfes | padres | adultos_ia | pymes
    tema            TEXT    NOT NULL,             -- título normalizado del cluster
    angulo          TEXT,                         -- ángulo editorial propuesto
    score           REAL    NOT NULL DEFAULT 0,
    novedad_horas   REAL,
    formato_sugerido TEXT,
    ethics_risk     TEXT    DEFAULT 'low',         -- low | medium | high
    low_confidence  INTEGER DEFAULT 0,
    source_ids      TEXT    NOT NULL,             -- JSON array de ids de signals_*
    source_tables   TEXT    NOT NULL,             -- JSON array de tabla por cada id
    fuentes_json    TEXT,                         -- JSON array [{url, tipo, titulo}]
    ciclo_ts        TEXT    NOT NULL,             -- timestamp del ciclo de research
    used_in_piece   TEXT,                         -- piece_id si ya fue usado, null si no
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_clustered_nicho    ON signals_clustered(nicho);
CREATE INDEX IF NOT EXISTS idx_clustered_score    ON signals_clustered(score DESC);
CREATE INDEX IF NOT EXISTS idx_clustered_used     ON signals_clustered(used_in_piece);
CREATE INDEX IF NOT EXISTS idx_clustered_ciclo    ON signals_clustered(ciclo_ts);

-- =========================================================================
-- Fuentes candidatas (de discovery semanal — requieren aprobación de Mateo)
-- =========================================================================

CREATE TABLE IF NOT EXISTS candidate_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    platform    TEXT    NOT NULL,                 -- instagram | tiktok | rss | youtube
    handle_url  TEXT    NOT NULL,
    niches      TEXT    NOT NULL,                 -- JSON array de nichos
    rationale   TEXT,
    quality_signals TEXT,                         -- JSON array
    risk_flags  TEXT,                             -- JSON array
    proposed_at TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending', -- pending | approved | rejected
    decided_at  TEXT,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- =========================================================================
-- Log de ciclos de research (trazabilidad y debugging)
-- =========================================================================

CREATE TABLE IF NOT EXISTS research_cycles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ciclo_ts        TEXT    NOT NULL UNIQUE,
    trigger         TEXT    NOT NULL DEFAULT 'cron', -- cron | telegram | manual
    nichos          TEXT,                           -- JSON array de nichos procesados
    signals_raw     INTEGER DEFAULT 0,
    signals_deduped INTEGER DEFAULT 0,
    clusters_total  INTEGER DEFAULT 0,
    shortlist_count INTEGER DEFAULT 0,
    cost_usd        REAL    DEFAULT 0,
    duration_s      REAL,
    status          TEXT    NOT NULL DEFAULT 'ok',  -- ok | partial | failed
    error_log       TEXT,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
