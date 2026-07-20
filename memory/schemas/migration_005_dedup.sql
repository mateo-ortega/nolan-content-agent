-- migration_005_dedup.sql
-- Ejecutar: sqlite3 memory/pieces.sqlite < memory/schemas/migration_005_dedup.sql
--
-- 1. Anade columnas pillar y evergreen_id a pieces (estrategia editorial / dedup)
-- 2. Crea tabla auxiliar evergreen_usage
-- 3. Indices para los queries de dedup y rotacion de pillar
--
-- Idempotente: los ALTER fallan silencioso si la columna ya existe (mismo patron
-- que migration_learning.sql:11-12). Ejecutar con .bail off o bash || true.

PRAGMA journal_mode = WAL;

-- ── Columnas faltantes en pieces ────────────────────────────────────────────

ALTER TABLE pieces ADD COLUMN pillar       TEXT;
ALTER TABLE pieces ADD COLUMN evergreen_id TEXT;

-- ── Indices ─────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_pieces_pillar    ON pieces(pillar);
CREATE INDEX IF NOT EXISTS idx_pieces_evergreen ON pieces(evergreen_id);

-- ── Tabla auxiliar evergreen_usage ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS evergreen_usage (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    evergreen_id    TEXT    NOT NULL,
    piece_id        TEXT,
    used_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (piece_id) REFERENCES pieces(piece_id)
);

CREATE INDEX IF NOT EXISTS idx_evergreen_usage_id   ON evergreen_usage(evergreen_id);
CREATE INDEX IF NOT EXISTS idx_evergreen_usage_when ON evergreen_usage(used_at);
