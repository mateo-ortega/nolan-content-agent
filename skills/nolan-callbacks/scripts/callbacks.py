"""
nolan-callbacks — aprobación / rechazo / edición de piezas en revisión.

Uso:
    python callbacks.py --action aprobar  --piece-id 2026-04-24-xyz
    python callbacks.py --action rechazar --piece-id 2026-04-24-xyz [--reason "tono off"]
    python callbacks.py --action editar   --piece-id 2026-04-24-xyz [--instructions "más corto"]
    python callbacks.py --action answer   --callback-query-id <cqid>
"""

import argparse
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent.parent.parent
))
sys.path.insert(0, str(PROJECT_ROOT))

NOLAN_PYTHON = os.environ.get("NOLAN_PYTHON", "python3.12")
DB_PATH      = PROJECT_ROOT / "memory" / "pieces.sqlite"
PRODUCE_PY   = PROJECT_ROOT / "skills" / "nolan-produce-carrusel" / "scripts" / "produce_carrusel.py"
PACKAGE_PY   = PROJECT_ROOT / "skills" / "nolan-package" / "scripts" / "package.py"


def main():
    ap = argparse.ArgumentParser(description="Maneja callbacks de revisión de piezas")
    ap.add_argument("--action", required=True,
                    choices=["aprobar", "rechazar", "editar", "answer"])
    ap.add_argument("--piece-id", default="")
    ap.add_argument("--reason", default="",
                    help="Motivo de rechazo (rechazar)")
    ap.add_argument("--instructions", default="",
                    help="Instrucciones de edición (editar)")
    ap.add_argument("--callback-query-id", default="",
                    help="ID del callback_query de Telegram para dismissar el spinner")
    args = ap.parse_args()

    # Dismissar spinner antes de cualquier operación lenta
    if args.callback_query_id:
        _answer_callback_query(args.callback_query_id)

    if args.action == "aprobar":
        _aprobar(args.piece_id)
    elif args.action == "rechazar":
        _rechazar(args.piece_id, args.reason)
    elif args.action == "editar":
        _editar(args.piece_id, args.instructions)
    elif args.action == "answer":
        pass  # callback query ya respondido arriba


# ---------------------------------------------------------------------------
# Acciones
# ---------------------------------------------------------------------------

def _aprobar(piece_id: str):
    if not piece_id:
        print("[callbacks] ERROR: --piece-id requerido", file=sys.stderr)
        sys.exit(1)

    now = _now()
    _update_db(piece_id, status="approved", reviewed_at=now, approved_at=now)

    marker = PROJECT_ROOT / "staging" / piece_id / "APROBADO"
    marker.touch(exist_ok=True)

    rejected_marker = PROJECT_ROOT / "staging" / piece_id / "RECHAZADO"
    rejected_marker.unlink(missing_ok=True)

    _send_message(f"*{piece_id}* aprobado.\nListo para publicar cuando quieras.")
    print(f"[callbacks] {piece_id} -> approved")


def _rechazar(piece_id: str, reason: str):
    if not piece_id:
        print("[callbacks] ERROR: --piece-id requerido", file=sys.stderr)
        sys.exit(1)

    now = _now()
    _update_db(piece_id, status="rejected", reviewed_at=now,
               rejection_reason=reason or None)

    marker = PROJECT_ROOT / "staging" / piece_id / "RECHAZADO"
    marker.write_text(reason or "(sin motivo)", encoding="utf-8")

    msg = f"*{piece_id}* rechazado."
    if reason:
        msg += f"\nMotivo: _{reason}_"
    msg += "\n\nPara nueva version: /tema"
    _send_message(msg)
    print(f"[callbacks] {piece_id} -> rejected  reason={reason!r}")


def _editar(piece_id: str, instructions: str):
    if not piece_id:
        print("[callbacks] ERROR: --piece-id requerido", file=sys.stderr)
        sys.exit(1)

    now = _now()

    if not instructions:
        _update_db(piece_id, status="needs_edit", reviewed_at=now)
        _send_message(
            f"Pieza *{piece_id}* marcada para edicion.\n"
            f"Que cambiar? Responde con las instrucciones.\n"
            f"(o /rechazar {piece_id} para descartar)"
        )
        print(f"[callbacks] {piece_id} -> needs_edit (esperando instrucciones)")
        return

    # Instrucciones presentes -> re-producir
    _update_db(piece_id, status="draft",
               edit_instruction=instructions, reviewed_at=now)

    brief_path = PROJECT_ROOT / "staging" / piece_id / "brief.yaml"
    if not brief_path.exists():
        _send_message(
            f"No encontre el brief de *{piece_id}*.\n"
            "Re-produce manualmente con /tema."
        )
        print(f"[callbacks] {piece_id}: brief.yaml no encontrado", file=sys.stderr)
        return

    with open(brief_path, encoding="utf-8") as f:
        brief = yaml.safe_load(f)
    brief["nota_edicion"] = instructions

    tmp_brief = PROJECT_ROOT / "staging" / piece_id / "brief_edit.yaml"
    with open(tmp_brief, "w", encoding="utf-8") as f:
        yaml.dump(brief, f, allow_unicode=True, default_flow_style=False)

    (PROJECT_ROOT / "staging" / piece_id / "content.yaml").unlink(missing_ok=True)

    _send_message(
        f"Re-produciendo *{piece_id}*\n"
        f"Ajuste: _{instructions}_"
    )

    result = subprocess.run(
        [NOLAN_PYTHON, str(PRODUCE_PY),
         "--brief", str(tmp_brief), "--piece-id", piece_id],
        capture_output=True, text=True
    )
    tmp_brief.unlink(missing_ok=True)

    if result.returncode != 0:
        err = result.stderr[-400:].strip()
        _send_message(f"Error al re-producir *{piece_id}*:\n`{err}`")
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    subprocess.run(
        [NOLAN_PYTHON, str(PACKAGE_PY), "--piece-id", piece_id],
        capture_output=True, text=True
    )
    print(f"[callbacks] {piece_id} -> re-produced  instructions={instructions!r}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _update_db(piece_id: str, **kwargs):
    if not DB_PATH.exists():
        return
    kwargs["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [piece_id]
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(f"UPDATE pieces SET {cols} WHERE piece_id=?", vals)
    except Exception as e:
        print(f"[callbacks] WARN DB: {e}", file=sys.stderr)


def _bot_base() -> str:
    token = (os.environ.get("HERMES_TELEGRAM_BOT_TOKEN")
             or os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    if not token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN o HERMES_TELEGRAM_BOT_TOKEN")
    return f"https://api.telegram.org/bot{token}"


def _chat_id() -> str:
    raw = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
    if not raw:
        raise RuntimeError("Falta TELEGRAM_ALLOWED_USERS")
    return raw


def _send_message(text: str):
    try:
        base = _bot_base()
        cid  = _chat_id()
        with httpx.Client(timeout=15) as client:
            client.post(f"{base}/sendMessage", json={
                "chat_id": cid, "text": text, "parse_mode": "Markdown"
            })
    except Exception as e:
        print(f"[callbacks] WARN Telegram: {e}", file=sys.stderr)


def _answer_callback_query(cq_id: str):
    """Dismissar el spinner del boton inline (<3 s o Telegram muestra error)."""
    try:
        base = _bot_base()
        with httpx.Client(timeout=8) as client:
            client.post(f"{base}/answerCallbackQuery",
                        json={"callback_query_id": cq_id})
    except Exception:
        pass


if __name__ == "__main__":
    main()
