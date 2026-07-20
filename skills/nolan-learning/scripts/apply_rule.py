"""
nolan-learning/scripts/apply_rule.py

Aplica o rechaza una propuesta de regla generada por rule_writer.py.
Cuando se aplica: añade la regla al SOUL.md (VPS + ~/.hermes/) y reinicia Hermes.

Uso:
    python apply_rule.py --action aplicar  --proposal-id 3
    python apply_rule.py --action rechazar --proposal-id 3
"""

import argparse
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent.parent.parent
))
DB_PATH     = PROJECT_ROOT / "memory" / "pieces.sqlite"
SOUL_VPS    = PROJECT_ROOT / "SOUL.md"
SOUL_HERMES = Path.home() / ".hermes" / "SOUL.md"

LEARNED_MARKER = "\n## Reglas aprendidas (auto-propuestas)\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--action",      required=True, choices=["aplicar", "rechazar"])
    ap.add_argument("--proposal-id", required=True, type=int)
    args = ap.parse_args()

    proposal = _load_proposal(args.proposal_id)
    if not proposal:
        msg = f"[apply_rule] Propuesta #{args.proposal_id} no encontrada."
        print(msg, file=sys.stderr)
        _send_message(f"Error: propuesta #{args.proposal_id} no encontrada.")
        sys.exit(1)

    if proposal["status"] != "pending":
        _send_message(f"Propuesta #{args.proposal_id} ya fue *{proposal['status']}*.")
        print(f"[apply_rule] Propuesta #{args.proposal_id} ya estaba {proposal['status']}")
        return

    now = datetime.now(tz=timezone.utc).isoformat()

    if args.action == "rechazar":
        _update_proposal(args.proposal_id, status="rejected", decided_at=now, updated_at=now)
        _send_message(f"Propuesta #{args.proposal_id} rechazada. No se modifica SOUL.md.")
        print(f"[apply_rule] #{args.proposal_id} rechazada")
        return

    # ── Aplicar ──────────────────────────────────────────────────────────────
    _append_to_soul(args.proposal_id, proposal["pattern_desc"], proposal["rule_text"])
    _update_proposal(args.proposal_id, status="applied", decided_at=now, updated_at=now)
    _restart_hermes()

    _send_message(
        f"*Regla #{args.proposal_id} aplicada* a SOUL.md.\n\n"
        f"Patrón: _{proposal['pattern_desc']}_\n\n"
        f"Hermes reiniciado con la nueva regla activa."
    )
    print(f"[apply_rule] #{args.proposal_id} aplicada y Hermes reiniciado")


# ── DB helpers ───────────────────────────────────────────────────────────────

def _load_proposal(proposal_id: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM rule_proposals WHERE id=?", (proposal_id,)
        ).fetchone()
    return dict(row) if row else None


def _update_proposal(proposal_id: int, **kwargs) -> None:
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [proposal_id]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"UPDATE rule_proposals SET {cols} WHERE id=?", vals)


# ── Modificar SOUL.md ────────────────────────────────────────────────────────

def _append_to_soul(proposal_id: int, pattern_desc: str, rule_text: str) -> None:
    entry = (
        f"\n### Regla #{proposal_id} — {pattern_desc}\n\n"
        f"{rule_text}\n"
    )
    for soul_path in [SOUL_VPS, SOUL_HERMES]:
        if not soul_path.exists():
            print(f"[apply_rule] WARN: {soul_path} no encontrado, saltando", file=sys.stderr)
            continue
        content = soul_path.read_text(encoding="utf-8")
        if LEARNED_MARKER.strip() not in content:
            content += LEARNED_MARKER
        content += entry
        soul_path.write_text(content, encoding="utf-8")
        print(f"[apply_rule] Regla escrita en {soul_path}")


# ── Reiniciar Hermes ─────────────────────────────────────────────────────────

def _restart_hermes() -> None:
    hermes_bin = Path.home() / ".local" / "bin" / "hermes"

    result = subprocess.run(
        ["pgrep", "-f", "hermes.*gateway"],
        capture_output=True, text=True
    )
    for pid_str in result.stdout.strip().splitlines():
        try:
            os.kill(int(pid_str), signal.SIGTERM)
        except ProcessLookupError:
            pass

    time.sleep(2)

    log = open("/tmp/hermes-gateway.log", "a")
    subprocess.Popen(
        [str(hermes_bin), "gateway", "run"],
        stdout=log, stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(3)
    print("[apply_rule] Hermes gateway reiniciado")


# ── Telegram ─────────────────────────────────────────────────────────────────

def _send_message(text: str) -> None:
    token   = os.environ.get("HERMES_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
    if not token or not chat_id:
        return
    try:
        with httpx.Client(timeout=15) as client:
            client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            )
    except Exception as e:
        print(f"[apply_rule] WARN Telegram: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
