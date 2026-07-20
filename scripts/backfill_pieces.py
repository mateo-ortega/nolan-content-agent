"""
backfill_pieces.py — Carga el historial de piezas publicadas desde Drive a pieces.sqlite.

Sin historial, la dedup arranca ciega y deja pasar piezas que ya fueron publicadas.
Este script reconstruye `pieces.sqlite` listando carpetas en `gdrive:Nolan/{Carruseles,
Animaciones,Guiones}/<piece_id>/` y leyendo el metadata.json de cada una. Para piezas
viejas sin metadata.json (sincronizado solo a partir del fix de package.py), parsea
el piece_id (formato `YYYY-MM-DD-slug`) y usa el slug como topic aproximado.

Uso:
    python scripts/backfill_pieces.py [--days 60] [--dry-run] [--remote gdrive] [--root Nolan]
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent,
))
sys.path.insert(0, str(PROJECT_ROOT))
from sapiens._paths import pieces_db_path  # noqa: E402

SCHEMA_SQL = PROJECT_ROOT / "memory" / "schemas" / "pieces.sql"

_FOLDER_TO_FORMAT = {
    "Carruseles":  "carrusel",
    "Animaciones": "animacion",
    "Guiones":     "guion",
}

_PIECE_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    if SCHEMA_SQL.exists():
        try:
            conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        except sqlite3.OperationalError as e:
            print(f"[backfill] WARN schema: {e}", file=sys.stderr)
    for col, decl in [
        ("topic", "TEXT"), ("hook", "TEXT"), ("archetype", "TEXT"),
        ("pillar", "TEXT"), ("evergreen_id", "TEXT"),
        ("ethics_score", "TEXT DEFAULT 'green'"), ("llm_cost_usd", "REAL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE pieces ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass


def _rclone_lsf(path: str) -> list[str]:
    """Lista subcarpetas inmediatas. Devuelve nombres sin slash final."""
    try:
        out = subprocess.run(
            ["rclone", "lsf", "--dirs-only", path],
            check=True, capture_output=True, text=True, timeout=60,
        )
        return [l.rstrip("/") for l in out.stdout.splitlines() if l.strip()]
    except FileNotFoundError:
        print("[backfill] ERROR: rclone no encontrado en PATH", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[backfill] WARN listando {path}: {e.stderr.strip()}", file=sys.stderr)
        return []


def _rclone_cat(path: str) -> str | None:
    try:
        out = subprocess.run(
            ["rclone", "cat", path],
            check=True, capture_output=True, text=True, timeout=30,
        )
        return out.stdout
    except subprocess.CalledProcessError:
        return None


def _piece_id_to_date(piece_id: str) -> str | None:
    m = _PIECE_ID_RE.match(piece_id)
    if not m:
        return None
    return f"{m.group(1)}T00:00:00+00:00"


def _piece_id_to_slug(piece_id: str) -> str:
    m = _PIECE_ID_RE.match(piece_id)
    return m.group(2).replace("-", " ") if m else piece_id


def _within_window(piece_id: str, cutoff: datetime) -> bool:
    iso = _piece_id_to_date(piece_id)
    if not iso:
        return True  # sin fecha clara: incluir por defecto
    try:
        dt = datetime.fromisoformat(iso)
        return dt >= cutoff
    except Exception:
        return True


def backfill_from_drive(
    remote: str = "gdrive",
    root: str = "Nolan",
    days: int = 60,
    dry_run: bool = False,
) -> int:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows: list[dict] = []

    for folder, fmt in _FOLDER_TO_FORMAT.items():
        base = f"{remote}:{root}/{folder}/"
        print(f"[backfill] listando {base}")
        piece_ids = _rclone_lsf(base)
        print(f"[backfill]   {len(piece_ids)} subcarpetas")

        for pid in piece_ids:
            if not _within_window(pid, cutoff):
                continue
            meta_text = _rclone_cat(f"{base}{pid}/metadata.json")
            if meta_text:
                try:
                    meta = json.loads(meta_text)
                except json.JSONDecodeError:
                    meta = {}
            else:
                meta = {}

            row = {
                "piece_id":     pid,
                "format":       meta.get("format", fmt),
                "niche":        meta.get("niche", "") if not isinstance(meta.get("niche"), list)
                                else json.dumps(meta.get("niche"), ensure_ascii=False),
                "topic":        meta.get("topic") or _piece_id_to_slug(pid),
                "hook":         meta.get("hook", ""),
                "archetype":    meta.get("archetype", ""),
                "pillar":       meta.get("pillar", ""),
                "evergreen_id": meta.get("evergreen_id") or None,
                "status":       meta.get("status", "published"),
                "ethics_score": meta.get("ethics_score", "green"),
                "llm_cost_usd": float(meta.get("llm_cost_usd", 0) or 0),
                "created_at":   meta.get("created_at") or _piece_id_to_date(pid) or datetime.now(tz=timezone.utc).isoformat(),
            }
            rows.append(row)

    print(f"[backfill] total piezas a insertar: {len(rows)}  (dry_run={dry_run})")
    if dry_run or not rows:
        return len(rows)

    db = pieces_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    inserted = 0
    with sqlite3.connect(db) as conn:
        _ensure_schema(conn)
        for r in rows:
            try:
                conn.execute("""
                    INSERT INTO pieces (
                        piece_id, format, niche, topic, hook, archetype, pillar, evergreen_id,
                        status, ethics_score, llm_cost_usd,
                        produced_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(piece_id) DO UPDATE SET
                        topic        = COALESCE(NULLIF(excluded.topic, ''), pieces.topic),
                        hook         = COALESCE(NULLIF(excluded.hook, ''), pieces.hook),
                        archetype    = COALESCE(NULLIF(excluded.archetype, ''), pieces.archetype),
                        pillar       = COALESCE(NULLIF(excluded.pillar, ''), pieces.pillar),
                        evergreen_id = COALESCE(excluded.evergreen_id, pieces.evergreen_id),
                        updated_at   = excluded.updated_at
                """, (
                    r["piece_id"], r["format"], r["niche"], r["topic"], r["hook"],
                    r["archetype"], r["pillar"], r["evergreen_id"],
                    r["status"], r["ethics_score"], r["llm_cost_usd"],
                    r["created_at"], r["created_at"], datetime.now(tz=timezone.utc).isoformat(),
                ))
                if r["evergreen_id"]:
                    conn.execute(
                        "INSERT INTO evergreen_usage (evergreen_id, piece_id, used_at) "
                        "VALUES (?, ?, ?)",
                        (r["evergreen_id"], r["piece_id"], r["created_at"]),
                    )
                inserted += 1
            except sqlite3.Error as e:
                print(f"[backfill] WARN {r['piece_id']}: {e}", file=sys.stderr)
        conn.commit()

    return inserted


def main():
    ap = argparse.ArgumentParser(description="Backfill pieces.sqlite desde Drive")
    ap.add_argument("--days", type=int, default=60, help="Ventana de antiguedad")
    ap.add_argument("--remote", default=os.environ.get("RCLONE_REMOTE", "gdrive"))
    ap.add_argument("--root",   default=os.environ.get("DRIVE_ROOT", "Nolan"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    n = backfill_from_drive(args.remote, args.root, args.days, args.dry_run)
    print(f"[backfill] OK: {n} piezas procesadas")


if __name__ == "__main__":
    main()
