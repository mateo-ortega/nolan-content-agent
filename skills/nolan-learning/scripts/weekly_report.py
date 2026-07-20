"""
weekly_report.py — Dashboard semanal de diversidad y salud de Nolan.

Ejecutar via cron Hermes los lunes 9:00 LATAM:
    /srv/nolan-venv/bin/python3.12 \\
        /srv/sapiens-nolan/skills/nolan-learning/scripts/weekly_report.py

Metricas reportadas a Telegram:
  - N piezas producidas / aprobadas / rechazadas (ultimos 7 dias)
  - Distincion de evergreen_id usados (diversidad de pool)
  - Distincion de pillar usados (rotacion editorial)
  - % de piezas que vinieron de research (evergreen_id IS NULL)
  - Top 3 pares de piezas con angulo conceptualmente cercano (Jaccard n-gramas)

Si % research < 30 → alerta "research degradado".
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent.parent.parent,
))
sys.path.insert(0, str(PROJECT_ROOT))

from sapiens._paths import pieces_db_path           # noqa: E402
from sapiens.dedup import topic_ngrams, jaccard     # noqa: E402

EVERGREEN_YAML = PROJECT_ROOT / "prompts" / "evergreen_topics.yaml"


def _send_telegram(text: str) -> None:
    token = os.environ.get("HERMES_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat  = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
    if not (token and chat):
        print("[weekly] WARN: falta TELEGRAM_BOT_TOKEN o TELEGRAM_ALLOWED_USERS", file=sys.stderr)
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
    except Exception as e:
        print(f"[weekly] WARN telegram: {e}", file=sys.stderr)


def _evergreen_pool_size() -> int:
    """Total de items en evergreen_topics.yaml (denominador de diversidad)."""
    try:
        import yaml
        with open(EVERGREEN_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return len(data.get("temas", []))
    except Exception:
        return 0


def main() -> None:
    db = pieces_db_path()
    if not db.exists():
        print(f"[weekly] ERROR: pieces.sqlite no existe en {db}", file=sys.stderr)
        sys.exit(1)

    cutoff_7d  = (datetime.now(tz=timezone.utc) - timedelta(days=7)).isoformat()
    cutoff_30d = (datetime.now(tz=timezone.utc) - timedelta(days=30)).isoformat()

    with sqlite3.connect(str(db)) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM pieces WHERE created_at >= ?", (cutoff_7d,)
        ).fetchone()[0]

        approved = conn.execute(
            "SELECT COUNT(*) FROM pieces "
            "WHERE created_at >= ? AND status = 'approved'", (cutoff_7d,)
        ).fetchone()[0]

        rejected = conn.execute(
            "SELECT COUNT(*) FROM pieces "
            "WHERE created_at >= ? AND status = 'rejected'", (cutoff_7d,)
        ).fetchone()[0]

        distinct_evergreen = conn.execute(
            "SELECT COUNT(DISTINCT evergreen_id) FROM pieces "
            "WHERE created_at >= ? AND evergreen_id IS NOT NULL "
            "AND evergreen_id != ''", (cutoff_7d,)
        ).fetchone()[0]

        distinct_pillar = conn.execute(
            "SELECT COUNT(DISTINCT pillar) FROM pieces "
            "WHERE created_at >= ? AND pillar IS NOT NULL "
            "AND pillar != ''", (cutoff_7d,)
        ).fetchone()[0]

        from_research = conn.execute(
            "SELECT COUNT(*) FROM pieces "
            "WHERE created_at >= ? AND (evergreen_id IS NULL OR evergreen_id = '')",
            (cutoff_7d,)
        ).fetchone()[0]

        # Pares con angulo cercano (Jaccard n-gramas > 0.40) en 30d
        rows = conn.execute(
            "SELECT piece_id, topic, hook, created_at FROM pieces "
            "WHERE created_at >= ? AND topic IS NOT NULL", (cutoff_30d,)
        ).fetchall()

    pct_research = (from_research / total * 100) if total else 0.0
    pool = _evergreen_pool_size()

    # Detectar pares conceptualmente cercanos
    close_pairs: list[tuple[float, str, str]] = []
    rows = list(rows)
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a_text = f"{rows[i][1]} {rows[i][2] or ''}"
            b_text = f"{rows[j][1]} {rows[j][2] or ''}"
            score = jaccard(topic_ngrams(a_text), topic_ngrams(b_text))
            if score >= 0.40:
                close_pairs.append((score, rows[i][0], rows[j][0]))
    close_pairs.sort(reverse=True)
    top3 = close_pairs[:3]

    lines = [
        "*Nolan — reporte semanal*",
        f"_{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}_",
        "",
        f"*Volumen 7d:* {total} piezas (✓ {approved} / ✗ {rejected})",
        f"*Diversidad evergreen:* {distinct_evergreen}/{pool} items distintos",
        f"*Rotacion pillar:* {distinct_pillar}/4 pilares distintos",
        f"*Origen:* {from_research}/{total} desde research "
        f"({pct_research:.0f}%) — resto evergreen",
    ]

    if pct_research < 30 and total >= 3:
        lines.append("")
        lines.append("⚠️ *Alerta:* < 30% de piezas desde research. "
                     "Sistema vive del evergreen — revisar APIs (Tavily/Apify).")

    if top3:
        lines.append("")
        lines.append("*Top 3 angulos cercanos (30d):*")
        for score, pa, pb in top3:
            lines.append(f"  · {score:.2f} — `{pa}` ↔ `{pb}`")

    msg = "\n".join(lines)
    print(msg)
    _send_telegram(msg)


if __name__ == "__main__":
    main()
