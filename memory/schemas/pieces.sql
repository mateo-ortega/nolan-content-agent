-- pieces.sqlite — registro de piezas producidas por Nolan
-- Motor: SQLite 3.x
-- Ejecutar: sqlite3 memory/pieces.sqlite < memory/schemas/pieces.sql

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- =========================================================================
-- Piezas (una fila por pieza producida)
-- =========================================================================

CREATE TABLE IF NOT EXISTS pieces (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    piece_id            TEXT    NOT NULL UNIQUE,  -- slug: YYYY-MM-DD-tema-nicho
    format              TEXT    NOT NULL,          -- carrusel | animacion | voiceover_broll | talking_head
    archetype           TEXT,                      -- senales | framework | tesis | comparativa | ad_hoc | null
    niche               TEXT    NOT NULL,
    topic               TEXT    NOT NULL,
    hook                TEXT,
    thesis              TEXT,

    -- Estado del ciclo de revisión
    status              TEXT    NOT NULL DEFAULT 'draft',
    -- draft → pending_review → approved | rejected | edited

    -- Costo LLM
    llm_cost_usd        REAL    DEFAULT 0,
    llm_model_copy      TEXT,                      -- modelo usado para copy
    llm_model_research  TEXT,                      -- modelo usado para research

    -- Ethics
    ethics_score        TEXT    DEFAULT 'green',   -- green | yellow | red
    ethics_flags        TEXT,                      -- JSON array de flags disparados

    -- Producción
    render_seconds      REAL,
    slides_count        INTEGER,                   -- solo carrusel
    duration_s          REAL,                      -- animacion | voiceover

    -- Drive + revisión
    drive_path          TEXT,                      -- ruta en Drive
    telegram_message_id TEXT,                      -- ID del mensaje de review en Telegram

    -- Feedback de Mateo
    rejection_reason    TEXT,
    edit_instruction    TEXT,

    -- Sources
    sources_json        TEXT,                      -- JSON array [{url, tipo, citation}]

    -- Timestamps
    produced_at         TEXT,
    reviewed_at         TEXT,
    approved_at         TEXT,
    published_at        TEXT,                      -- null si Nolan nunca publica
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_pieces_status    ON pieces(status);
CREATE INDEX IF NOT EXISTS idx_pieces_niche     ON pieces(niche);
CREATE INDEX IF NOT EXISTS idx_pieces_format    ON pieces(format);
CREATE INDEX IF NOT EXISTS idx_pieces_produced  ON pieces(produced_at);

-- =========================================================================
-- Uso LLM por pieza (granularidad de tarea)
-- =========================================================================

CREATE TABLE IF NOT EXISTS llm_usage (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    piece_id        TEXT,                          -- null para llamadas fuera de pieza (research)
    task            TEXT    NOT NULL,              -- research.classify_niche, copy.carrusel_yaml, etc.
    provider        TEXT    NOT NULL,              -- openrouter | perplexity
    model           TEXT    NOT NULL,
    in_tokens       INTEGER DEFAULT 0,
    out_tokens      INTEGER DEFAULT 0,
    cached_tokens   INTEGER DEFAULT 0,
    cost_usd        REAL    DEFAULT 0,
    latency_ms      INTEGER,
    status          TEXT    DEFAULT 'ok',          -- ok | error | retried
    error_detail    TEXT,
    ts              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (piece_id) REFERENCES pieces(piece_id)
);

CREATE INDEX IF NOT EXISTS idx_llm_piece    ON llm_usage(piece_id);
CREATE INDEX IF NOT EXISTS idx_llm_task     ON llm_usage(task);
CREATE INDEX IF NOT EXISTS idx_llm_ts       ON llm_usage(ts);
CREATE INDEX IF NOT EXISTS idx_llm_month    ON llm_usage(substr(ts, 1, 7)); -- 'YYYY-MM'

-- =========================================================================
-- Vistas útiles
-- =========================================================================

CREATE VIEW IF NOT EXISTS v_monthly_cost AS
SELECT
    substr(ts, 1, 7)    AS month,
    SUM(cost_usd)       AS total_usd,
    SUM(in_tokens)      AS total_in_tok,
    SUM(out_tokens)     AS total_out_tok,
    SUM(cached_tokens)  AS total_cached_tok,
    COUNT(*)            AS total_calls
FROM llm_usage
GROUP BY 1
ORDER BY 1 DESC;

CREATE VIEW IF NOT EXISTS v_pieces_summary AS
SELECT
    format,
    niche,
    status,
    COUNT(*)                AS count,
    AVG(llm_cost_usd)       AS avg_cost_usd,
    AVG(render_seconds)     AS avg_render_s
FROM pieces
GROUP BY 1, 2, 3
ORDER BY format, niche, status;

CREATE VIEW IF NOT EXISTS v_approval_rate AS
SELECT
    strftime('%Y-%W', produced_at)  AS week,
    COUNT(*)                        AS total,
    SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) AS approved,
    ROUND(
        SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        1
    )                               AS approval_pct
FROM pieces
WHERE produced_at IS NOT NULL
GROUP BY 1
ORDER BY 1 DESC;

-- =========================================================================
-- Historial de colores (rotación cromática de sapiens-carrusel)
-- Replica el history.json de sapiens-carrusel pero en SQLite para consultas
-- =========================================================================

CREATE TABLE IF NOT EXISTS color_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    piece_id    TEXT    NOT NULL,
    color_scheme TEXT   NOT NULL,                  -- light | dark
    accent      TEXT    NOT NULL DEFAULT '#E8A838',
    used_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (piece_id) REFERENCES pieces(piece_id)
);
