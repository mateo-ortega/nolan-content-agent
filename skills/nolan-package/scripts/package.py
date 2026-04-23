"""
nolan-package — valida, sincroniza a Drive (opcional) y notifica a Mateo por Telegram.

Uso:
    python package.py --piece-id 2026-04-22-icfes-lectura-critica-metodo
    python package.py --piece-id 2026-04-22-icfes-lectura-critica-metodo --dry-run

Env vars requeridas (en ~/.hermes/.env o entorno):
    HERMES_TELEGRAM_BOT_TOKEN
    TELEGRAM_ALLOWED_USERS   (ID numérico de Mateo, ej: 5638117128)
    RCLONE_REMOTE            (opcional, ej: gdrive_sapiens)
    DRIVE_ROOT               (opcional, ej: SapiensContent)
"""

import argparse
import json
import os
import shutil
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

from sapiens.ethics_gate import load_gate, EthicsResult   # noqa: E402

# Archivos obligatorios para cualquier paquete
_REQUIRED_FILES = ["metadata.json", "caption.md", "alt_text.md", "sources.md"]
_REQUIRED_META = [
    "piece_id", "format", "niche", "topic", "sources",
    "llm_cost_usd", "ethics_score", "status", "created_at", "archetype",
]


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Empaqueta pieza y notifica a Mateo")
    ap.add_argument("--piece-id", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="Valida y muestra preview sin sincronizar ni notificar")
    args = ap.parse_args()

    piece_dir = PROJECT_ROOT / "staging" / args.piece_id
    if not piece_dir.exists():
        print(f"[package] ERROR: directorio no encontrado: {piece_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[package] piece_id={args.piece_id}  dry_run={args.dry_run}")

    # ── 1. Validar paquete ───────────────────────────────────────────────────
    try:
        validate_package(piece_dir)
    except ValueError as e:
        print(f"[package] ERROR validación: {e}", file=sys.stderr)
        sys.exit(1)
    print("[package] validación OK")

    # ── 2. Ethics final ──────────────────────────────────────────────────────
    gate = load_gate()
    texts = _collect_texts(piece_dir)
    sources_present = (piece_dir / "sources.md").exists()
    ethics = gate.check(texts, sources_available=sources_present)
    print(f"[package] ethics={ethics.status}")
    if ethics.status == "red":
        _notify_block(args.piece_id, ethics, args.dry_run)
        sys.exit(2)

    # ── 3. Preview.jpg si falta ──────────────────────────────────────────────
    cover = piece_dir / "cover.jpg"
    preview = piece_dir / "preview.jpg"
    if not preview.exists() and cover.exists():
        _build_preview(cover, preview)

    # ── 4. pieces.sqlite ─────────────────────────────────────────────────────
    _upsert_piece(args.piece_id, piece_dir)
    print("[package] pieces.sqlite actualizado")

    # ── 5. Drive sync ────────────────────────────────────────────────────────
    drive_url: str | None = None
    if not args.dry_run:
        drive_url = _sync_drive(args.piece_id, piece_dir)
    else:
        print("[package] dry-run: Drive sync omitido")

    # ── 6. Notificación Telegram ─────────────────────────────────────────────
    if args.dry_run:
        _print_telegram_preview(args.piece_id, piece_dir, drive_url)
    else:
        msg_id = _send_telegram(args.piece_id, piece_dir, drive_url)
        if msg_id:
            _save_message_id(args.piece_id, msg_id)

    print(f"[package] OK → pieza {args.piece_id} enviada a revisión")


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------

def validate_package(piece_dir: Path):
    missing = [f for f in _REQUIRED_FILES if not (piece_dir / f).exists()]
    meta_path = piece_dir / "metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        is_carrusel = meta.get("format") == "carrusel"
    else:
        is_carrusel = False

    slides = sorted(piece_dir.glob("slide-*.png"))
    if is_carrusel and not slides:
        missing.append("slide-*.png (ninguno encontrado porque es carrusel)")
    if missing:
        raise ValueError(f"Faltan archivos: {', '.join(missing)}")

    meta = json.loads((piece_dir / "metadata.json").read_text(encoding="utf-8"))
    missing_fields = [k for k in _REQUIRED_META if k not in meta]
    if missing_fields:
        raise ValueError(f"metadata.json incompleto — faltan: {', '.join(missing_fields)}")

    # Verificar dimensiones (opcional, requiere Pillow)
    try:
        from PIL import Image
        img = Image.open(slides[0])
        w, h = img.size
        if (w, h) != (1080, 1350) and not os.environ.get("NOLAN_SKIP_DIM_CHECK"):
            print(
                f"[package] WARN: {slides[0].name} es {w}×{h}, esperado 1080×1350",
                file=sys.stderr,
            )
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_texts(piece_dir: Path) -> list[str]:
    texts: list[str] = []
    cap = piece_dir / "caption.md"
    if cap.exists():
        texts.append(cap.read_text(encoding="utf-8"))
    cyaml = piece_dir / "content.yaml"
    if cyaml.exists():
        with open(cyaml, encoding="utf-8") as f:
            content = yaml.safe_load(f)
        for s in content.get("slides", []):
            texts.append(s.get("text", ""))
    return texts


def _build_preview(cover: Path, preview: Path):
    try:
        from PIL import Image
        img = Image.open(cover)
        img.thumbnail((480, 600))
        img.save(preview, "JPEG", quality=85)
    except (ImportError, Exception):
        shutil.copy(cover, preview)


def _upsert_piece(piece_id: str, piece_dir: Path):
    db = PROJECT_ROOT / "memory" / "pieces.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    meta_path = piece_dir / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    now = datetime.now(tz=timezone.utc).astimezone().isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pieces (
                piece_id TEXT PRIMARY KEY,
                format TEXT,
                niche TEXT,
                status TEXT,
                drive_path TEXT,
                telegram_message_id TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.execute("""
            INSERT INTO pieces (piece_id, format, niche, status, drive_path, created_at, updated_at)
            VALUES (?, ?, ?, 'pending_review', '', ?, ?)
            ON CONFLICT(piece_id) DO UPDATE SET
                status = 'pending_review',
                updated_at = excluded.updated_at
        """, (
            piece_id,
            meta.get("format", "carrusel"),
            meta.get("niche", ""),
            meta.get("created_at", now),
            now,
        ))


def _sync_drive(piece_id: str, piece_dir: Path) -> str | None:
    # Si Rclone se llama diferente, lo leemos, pero por defecto asume "gdrive"
    remote = os.environ.get("RCLONE_REMOTE")
    if not remote:
        # Por defecto intentamos usar el remote llamado 'gdrive'
        remote = "gdrive"
        
    # Capa madre siempre será "Nolan" o lo que diga el entorno
    root = os.environ.get("DRIVE_ROOT", "Nolan")
    
    # Extraer el formato para la subcarpeta de distribución ("Carruseles", "Animaciones")
    meta_path = piece_dir / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    format_type = meta.get("format", "carrusel")
    
    # Mapeo estructurado para mantener Drive hiperorganizado
    format_folder_map = {
        "carrusel": "Carruseles",
        "animacion": "Animaciones",
        "voiceover_broll": "Voiceovers",
        "talking_head": "Videos_Script"
    }
    subfolder = format_folder_map.get(format_type, "Otros")
    
    # Construcción de la jerarquía solicitada: remote:Nolan/Carruseles/2026-04-22-tema/
    dest = f"{remote}:{root}/{subfolder}/{piece_id}/"
    
    cmd = ["rclone", "copy", str(piece_dir) + "/", dest, "--transfers", "4", "--checkers", "8"]
    print(f"[package] rclone → {dest}")
    
    for attempt in range(3):
        try:
            subprocess.run(cmd, check=True, timeout=180)
            return dest
        except FileNotFoundError:
            print("[package] ERROR: 'rclone' no está instalado o no está en el PATH de tu VPS.", file=sys.stderr)
            return None
        except subprocess.CalledProcessError as e:
            if attempt == 2:
                print(f"[package] WARN: Drive sync falló ({e}). Staging local disponible.", file=sys.stderr)
                return None
    return None


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _bot_base() -> str:
    token = os.environ.get("HERMES_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("Falta HERMES_TELEGRAM_BOT_TOKEN o TELEGRAM_BOT_TOKEN")
    return f"https://api.telegram.org/bot{token}"


def _mateo_chat_id() -> str:
    raw = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
    if not raw:
        raise RuntimeError("Falta TELEGRAM_ALLOWED_USERS (ID numérico de Mateo)")
    return raw


def _send_telegram(piece_id: str, piece_dir: Path, drive_url: str | None) -> int | None:
    try:
        base = _bot_base()
        chat_id = _mateo_chat_id()
    except RuntimeError as e:
        print(f"[package] WARN: {e}", file=sys.stderr)
        return None

    meta = json.loads((piece_dir / "metadata.json").read_text(encoding="utf-8"))
    caption_preview = (piece_dir / "caption.md").read_text(encoding="utf-8").strip()[:300]
    n_slides = len(list(piece_dir.glob("slide-*.png")))
    cost = meta.get("llm_cost_usd", 0)

    msg = (
        f"✅ Misión Cumplida (Modo Autónomo): {piece_id}\n"
        f"• {n_slides} slides carrusel, nicho={meta.get('niche')}, ethics={meta.get('ethics_score')}\n"
        f"• costo LLM: ${cost:.3f}\n"
        f"• caption: {caption_preview}..."
    )
    payload = {"chat_id": chat_id, "text": msg}
    if drive_url:
        payload["reply_markup"] = {"inline_keyboard": [[{"text": "Ver en Drive", "url": drive_url}]]}

    slides = sorted(piece_dir.glob("slide-*.png"))[:10]
    msg_id: int | None = None

    # Enviar slides como media group
    if slides:
        media = []
        file_handles = {}
        for i, p in enumerate(slides):
            fname = f"f{i}"
            media.append({
                "type": "photo",
                "media": f"attach://{fname}",
                **({"caption": msg, "parse_mode": "HTML"} if i == 0 else {}),
            })
            file_handles[fname] = (p.name, open(p, "rb"), "image/png")
        try:
            with httpx.Client(timeout=90) as client:
                r = client.post(
                    f"{base}/sendMediaGroup",
                    data={"chat_id": chat_id, "media": json.dumps(media)},
                    files=file_handles,
                )
                r.raise_for_status()
                msg_id = r.json()["result"][0]["message_id"]
            print(f"[package] media group enviado ({n_slides} slides)")
        except Exception as e:
            print(f"[package] WARN: media group falló ({e})", file=sys.stderr)
        finally:
            for _, (_, fh, _) in file_handles.items():
                fh.close()

    # Mensaje de texto de confirmación
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(
                f"{base}/sendMessage",
                json=payload,
            )
            r.raise_for_status()
            if msg_id is None:
                msg_id = r.json()["result"]["message_id"]
        print(f"[package] Telegram notificado (message_id={msg_id})")
    except Exception as e:
        print(f"[package] WARN: sendMessage falló ({e})", file=sys.stderr)

    return msg_id


def _notify_block(piece_id: str, ethics: EthicsResult, dry_run: bool):
    msg = (
        f"[bloqueo] SOUL rojo en draft {piece_id}\n"
        f"• regla: {ethics.rule_id} — {ethics.description}\n"
        f"• texto: {ethics.matched_text[:120]}\n"
        f"• /autofix {piece_id} o /rechazar {piece_id}"
    )
    print(msg, file=sys.stderr)
    if dry_run:
        return
    try:
        base = _bot_base()
        chat_id = _mateo_chat_id()
        with httpx.Client(timeout=15) as client:
            client.post(f"{base}/sendMessage", json={"chat_id": chat_id, "text": msg})
    except Exception:
        pass


def _save_message_id(piece_id: str, msg_id: int):
    db = PROJECT_ROOT / "memory" / "pieces.sqlite"
    if not db.exists():
        return
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE pieces SET telegram_message_id=? WHERE piece_id=?",
            (str(msg_id), piece_id),
        )


def _print_telegram_preview(piece_id: str, piece_dir: Path, drive_url: str | None):
    meta = json.loads((piece_dir / "metadata.json").read_text(encoding="utf-8"))
    n = len(list(piece_dir.glob("slide-*.png")))
    print("\n--- Telegram preview (dry-run) ---")
    print(f"[aprobación] Pieza lista: {piece_id}")
    print(f"• {n} slides, nicho={meta.get('niche')}, ethics={meta.get('ethics_score')}")
    print(f"• costo LLM: ${meta.get('llm_cost_usd', 0):.4f}")
    cap_preview = (piece_dir / "caption.md").read_text(encoding="utf-8").strip()[:200]
    print(f"• caption: {cap_preview}...")
    print(f"• Botones: /aprobar {piece_id} | /rechazar {piece_id} | /editar {piece_id}")
    if drive_url:
        print(f"• Drive: {drive_url}")
    print("---\n")


if __name__ == "__main__":
    main()
