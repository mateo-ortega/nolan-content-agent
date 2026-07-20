"""
nolan-learning/scripts/rule_writer.py

Analiza rechazos recientes en pieces.sqlite e identifica patrones recurrentes.
Cuando un patrón aparece en ≥ MIN_COUNT piezas rechazadas, genera una propuesta
de regla concreta para SOUL.md y la envía a Mateo por Telegram con botones
[Aplicar] [Rechazar].

Uso:
    python rule_writer.py [--days 90] [--min-count 3] [--dry-run]

Ejecutado por hermes cron semanalmente.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent.parent.parent
))
sys.path.insert(0, str(PROJECT_ROOT))

from sapiens.nolan_llm_router import load_router   # noqa: E402

DB_PATH     = PROJECT_ROOT / "memory" / "pieces.sqlite"
SOUL_HERMES = Path.home() / ".hermes" / "SOUL.md"
SOUL_VPS    = PROJECT_ROOT / "SOUL.md"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days",      type=int, default=90, help="Ventana de análisis en días")
    ap.add_argument("--min-count", type=int, default=3,  help="Rechazos mínimos para proponer regla")
    ap.add_argument("--dry-run",   action="store_true",  help="Imprime propuestas sin guardar")
    args = ap.parse_args()

    rejections = _load_rejections(args.days)
    print(f"[rule_writer] {len(rejections)} rechazos con motivo en los últimos {args.days} días")

    if len(rejections) < args.min_count:
        print(f"[rule_writer] Umbral mínimo {args.min_count} no alcanzado — sin acción.")
        return

    soul_text = SOUL_HERMES.read_text(encoding="utf-8") if SOUL_HERMES.exists() else ""
    patterns  = _analyze_patterns(rejections, soul_text, args.min_count)

    if not patterns:
        print("[rule_writer] Sin patrones recurrentes detectados.")
        _send_message("Learning loop: sin patrones recurrentes esta semana.")
        return

    saved = 0
    for p in patterns:
        if args.dry_run:
            print(f"\n[DRY-RUN] Patrón: {p['pattern_desc']}")
            print(f"  Piezas: {p['piece_ids']}")
            print(f"  Regla:\n{p['rule_text']}\n")
        else:
            if not _proposal_exists(p["pattern_desc"]):
                _save_and_notify(p)
                saved += 1
            else:
                print(f"[rule_writer] Propuesta similar ya existe: {p['pattern_desc'][:60]}")

    if not args.dry_run:
        print(f"[rule_writer] {saved} propuesta(s) nueva(s) enviadas a Telegram.")


# ── Carga de rechazos ────────────────────────────────────────────────────────

def _load_rejections(days: int) -> list[dict]:
    since = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT piece_id, format, niche, topic, hook,
                   rejection_reason, updated_at
            FROM   pieces
            WHERE  status            = 'rejected'
              AND  rejection_reason IS NOT NULL
              AND  rejection_reason != ''
              AND  updated_at       >= ?
            ORDER BY updated_at DESC
            """,
            (since,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Análisis de patrones vía DeepSeek ────────────────────────────────────────

def _analyze_patterns(rejections: list, soul_text: str, min_count: int) -> list[dict]:
    rejection_lines = "\n".join(
        f"- [{r['piece_id']}] {r['format']}/{r['niche']}: \"{r['rejection_reason']}\""
        for r in rejections
    )

    existing_section = ""
    marker = "## Reglas aprendidas"
    if marker in soul_text:
        start = soul_text.find(marker)
        existing_section = soul_text[start : start + 2000]

    prompt = f"""Eres el analizador de aprendizaje del agente Nolan, productor de contenido para @sapiens.ed (Sapiens by Shift).

Rechazos recientes de piezas:
{rejection_lines}

Reglas ya aplicadas en SOUL.md (para no duplicar):
{existing_section if existing_section else "(ninguna todavía)"}

TAREA:
1. Agrupa los rechazos por similitud semántica del motivo.
2. Para cada grupo con {min_count} o más rechazos, redacta una regla accionable para añadir al SOUL.md.
3. Solo propone reglas concretas (no generalidades). La regla debe decirle a Nolan QUÉ HACER DIFERENTE.
4. NO repitas reglas ya cubiertas en el SOUL.md existente.

RESPONDE SOLO con JSON válido, sin markdown:
{{
  "patterns": [
    {{
      "pattern_desc": "Descripción breve del patrón (ej: gancho demasiado técnico para L1)",
      "piece_ids": ["2026-04-20-xyz", "2026-04-22-abc"],
      "count": 3,
      "rule_text": "Regla concisa (1-3 líneas, en español, accionable para el agente)"
    }}
  ]
}}

Si no hay patrones claros con {min_count}+ rechazos similares: {{"patterns": []}}"""

    router = load_router()
    resp = router.call(
        task="learning.rule_proposal",
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        data = json.loads(resp.text)
        return [p for p in data.get("patterns", []) if p.get("count", 0) >= min_count]
    except json.JSONDecodeError as e:
        print(f"[rule_writer] ERROR JSON: {e}\n{resp.text[:200]}", file=sys.stderr)
        return []


# ── Persistencia y notificación ──────────────────────────────────────────────

def _proposal_exists(pattern_desc: str) -> bool:
    """Evita duplicar propuestas pendientes del mismo patrón."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM rule_proposals WHERE status='pending' AND pattern_desc=?",
            (pattern_desc,),
        ).fetchone()
    return row is not None


def _save_and_notify(pattern: dict) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO rule_proposals (pattern_desc, piece_ids, rule_text, proposed_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                pattern["pattern_desc"],
                json.dumps(pattern.get("piece_ids", [])),
                pattern["rule_text"],
                now,
            ),
        )
        proposal_id = cur.lastrowid

    msg_id = _send_proposal_telegram(proposal_id, pattern)

    if msg_id:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE rule_proposals SET telegram_message_id=? WHERE id=?",
                (str(msg_id), proposal_id),
            )

    print(f"[rule_writer] Propuesta #{proposal_id} guardada y enviada.")


def _send_proposal_telegram(proposal_id: int, pattern: dict) -> int | None:
    token   = os.environ.get("HERMES_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
    if not token or not chat_id:
        print("[rule_writer] WARN: token/chat_id Telegram no configurado", file=sys.stderr)
        return None

    pieces = pattern.get("piece_ids", [])
    pieces_str = ", ".join(pieces[:3])
    if len(pieces) > 3:
        pieces_str += f" (+{len(pieces)-3} más)"

    text = (
        f"*Propuesta de regla #{proposal_id}*\n\n"
        f"*Patrón detectado ({pattern.get('count', len(pieces))} rechazos):*\n"
        f"{pattern['pattern_desc']}\n\n"
        f"*Piezas:* _{pieces_str}_\n\n"
        f"*Regla propuesta para SOUL.md:*\n"
        f"```\n{pattern['rule_text']}\n```"
    )

    keyboard = {"inline_keyboard": [[
        {"text": "Aplicar",  "callback_data": f"aplicar-regla|{proposal_id}"},
        {"text": "Rechazar", "callback_data": f"rechazar-regla|{proposal_id}"},
    ]]}

    base = f"https://api.telegram.org/bot{token}"
    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(f"{base}/sendMessage", json={
                "chat_id":      chat_id,
                "text":         text,
                "parse_mode":   "Markdown",
                "reply_markup": keyboard,
            })
            return r.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"[rule_writer] WARN Telegram: {e}", file=sys.stderr)
        return None


def _send_message(text: str) -> None:
    token   = os.environ.get("HERMES_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
    if not token or not chat_id:
        return
    try:
        with httpx.Client(timeout=15) as client:
            client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
    except Exception:
        pass


if __name__ == "__main__":
    main()
