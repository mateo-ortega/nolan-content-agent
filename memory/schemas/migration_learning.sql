-- migration_learning.sql
-- Ejecutar: sqlite3 memory/pieces.sqlite < memory/schemas/migration_learning.sql
--
-- 1. Añade columnas faltantes a pieces (usadas por callbacks.py)
-- 2. Crea tabla rule_proposals para el learning loop
-- 3. Idempotente: usa ADD COLUMN solo si no existe (via temp table trick)

PRAGMA journal_mode = WAL;

-- ── Columnas faltantes en pieces ────────────────────────────────────────────
-- SQLite no soporta IF NOT EXISTS en ALTER TABLE; el script falla si ya existe.
-- La forma segura es intentar y silenciar el error con el flag .bail off.

ALTER TABLE pieces ADD COLUMN rejection_reason TEXT;
ALTER TABLE pieces ADD COLUMN edit_instruction  TEXT;
ALTER TABLE pieces ADD COLUMN reviewed_at       TEXT;
ALTER TABLE pieces ADD COLUMN approved_at       TEXT;
ALTER TABLE pieces ADD COLUMN topic             TEXT;
ALTER TABLE pieces ADD COLUMN hook              TEXT;
ALTER TABLE pieces ADD COLUMN llm_cost_usd      REAL DEFAULT 0;
ALTER TABLE pieces ADD COLUMN archetype         TEXT;

-- ── rule_proposals ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rule_proposals (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_desc         TEXT    NOT NULL,
    piece_ids            TEXT    NOT NULL,   -- JSON array de piece_id
    rule_text            TEXT    NOT NULL,   -- texto concreto a insertar en SOUL.md
    status               TEXT    NOT NULL DEFAULT 'pending',  -- pending|applied|rejected
    proposed_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    decided_at           TEXT,
    updated_at           TEXT,
    telegram_message_id  TEXT
);

CREATE INDEX IF NOT EXISTS idx_rule_proposals_status ON rule_proposals(status);
