"""
nolan-package — valida, sincroniza a Drive y notifica a Mateo por Telegram.

Formatos soportados: carrusel · carrusel-ds · animacion · guion

Uso:
    python package.py --piece-id 2026-04-22-icfes-lectura-critica-metodo
    python package.py --piece-id 2026-04-22-icfes-lectura-critica-metodo --dry-run

Env vars requeridas (en ~/.hermes/.env o entorno):
    HERMES_TELEGRAM_BOT_TOKEN  o  TELEGRAM_BOT_TOKEN
    TELEGRAM_ALLOWED_USERS   (ID numérico de Mateo, ej: <TELEGRAM_USER_ID>)
    RCLONE_REMOTE            (opcional, default: "gdrive")
    DRIVE_ROOT               (opcional, default: "Nolan")
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

from sapiens.ethics_gate import load_gate, EthicsResult              # noqa: E402
from sapiens.alignment_gate import load_align_gate, AlignmentResult  # noqa: E402
from sapiens._paths import pieces_db_path                            # noqa: E402

_REQUIRED_FILES = ["metadata.json", "caption.md", "alt_text.md", "sources.md"]
_REQUIRED_META  = [
    "piece_id", "format", "niche", "topic", "pillar", "sources",
    "llm_cost_usd", "ethics_score", "status", "created_at", "archetype",
]

_FORMAT_DRIVE_FOLDER = {
    "carrusel":    "Carruseles",
    "carrusel-ds": "Carruseles",
    "animacion":   "Animaciones",
    "guion":       "Guiones",
}


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Empaqueta pieza y notifica a Mateo")
    ap.add_argument("--piece-id", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    piece_dir = PROJECT_ROOT / "staging" / args.piece_id
    if not piece_dir.exists():
        print(f"[package] ERROR: directorio no encontrado: {piece_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[package] piece_id={args.piece_id}  dry_run={args.dry_run}")

    # ── 1. Validar ───────────────────────────────────────────────────────────
    try:
        validate_package(piece_dir)
    except ValueError as e:
        print(f"[package] ERROR validación: {e}", file=sys.stderr)
        sys.exit(1)
    print("[package] validación OK")

    # ── 2. Ethics ────────────────────────────────────────────────────────────
    gate   = load_gate()
    texts  = _collect_texts(piece_dir)
    ethics = gate.check(texts, sources_available=(piece_dir / "sources.md").exists())
    print(f"[package] ethics={ethics.status}")
    if ethics.status == "red":
        _notify_block(args.piece_id, ethics, args.dry_run)
        sys.exit(2)

    # ── 2b. Alignment (fit Sapiens: pillar, cuota, arquetipo, vocabulario) ───
    align_gate = load_align_gate()
    meta_path  = piece_dir / "metadata.json"
    if meta_path.exists():
        meta_for_align = json.loads(meta_path.read_text(encoding="utf-8"))
        alignment = align_gate.check(meta_for_align, texts)
        failed = [c for c in alignment.checks if not c.passed]
        print(f"[package] alignment={alignment.status} "
              f"failed={[c.id for c in failed]}")
        if alignment.status == "red":
            _notify_block_alignment(args.piece_id, alignment, args.dry_run)
            sys.exit(4)
        if alignment.status == "yellow":
            meta_for_align["alignment_warnings"] = [
                {"id": c.id, "severity": c.severity, "reason": c.reason}
                for c in failed
            ]
            meta_path.write_text(
                json.dumps(meta_for_align, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ── 3. Preview para carrusel ──────────────────────────────────────────────
    slides = sorted(piece_dir.glob("slide-*.png"))
    if slides:
        cover   = piece_dir / "cover.jpg"
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

    # ── 6. Telegram ──────────────────────────────────────────────────────────
    if args.dry_run:
        _print_preview(args.piece_id, piece_dir, drive_url)
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
    fmt = "carrusel"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        fmt  = meta.get("format", "carrusel")
    else:
        missing.append("metadata.json")

    # Archivos específicos por formato
    if fmt in ("carrusel", "carrusel-ds"):
        if not list(piece_dir.glob("slide-*.png")):
            missing.append("slide-*.png (ninguno encontrado)")
        else:
            _check_slide_dimensions(piece_dir)
    elif fmt == "animacion":
        if not (piece_dir / "animation.mp4").exists():
            missing.append("animation.mp4")
    elif fmt == "guion":
        if not (piece_dir / "guion.md").exists():
            missing.append("guion.md")

    if missing:
        raise ValueError(f"Faltan archivos: {', '.join(missing)}")

    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        bad  = [k for k in _REQUIRED_META if k not in meta]
        if bad:
            raise ValueError(f"metadata.json incompleto — faltan: {', '.join(bad)}")


def _check_slide_dimensions(piece_dir: Path):
    try:
        from PIL import Image
        slides = sorted(piece_dir.glob("slide-*.png"))
        if not slides:
            return
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
# Helpers de contenido
# ---------------------------------------------------------------------------

def _collect_texts(piece_dir: Path) -> list[str]:
    texts: list[str] = []
    for fname in ("caption.md", "guion.md"):
        p = piece_dir / fname
        if p.exists():
            texts.append(p.read_text(encoding="utf-8"))
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


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

_SCHEMA_PATH = PROJECT_ROOT / "memory" / "schemas" / "pieces.sql"

# Columnas que el schema oficial puede no tener en DBs viejas creadas por
# versiones anteriores de package.py. Se intentan agregar de forma defensiva.
_DEFENSIVE_COLUMNS = [
    ("topic",            "TEXT"),
    ("hook",             "TEXT"),
    ("archetype",        "TEXT"),
    ("pillar",           "TEXT"),
    ("evergreen_id",     "TEXT"),
    ("ethics_score",     "TEXT DEFAULT 'green'"),
    ("rejection_reason", "TEXT"),
    ("llm_cost_usd",     "REAL DEFAULT 0"),
    ("sources_json",     "TEXT"),
    ("produced_at",      "TEXT"),
]


def _ensure_schema(conn: sqlite3.Connection):
    """Aplica el schema oficial (pieces.sql) + ALTER defensivos para DBs viejas."""
    if _SCHEMA_PATH.exists():
        try:
            conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        except sqlite3.OperationalError as e:
            print(f"[package] WARN aplicando schema oficial: {e}", file=sys.stderr)
    for col, decl in _DEFENSIVE_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE pieces ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass  # columna ya existe


def _upsert_piece(piece_id: str, piece_dir: Path):
    db = pieces_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    meta = {}
    mp   = piece_dir / "metadata.json"
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))
    now = datetime.now(tz=timezone.utc).astimezone().isoformat()
    niche = meta.get("niche", "")
    if isinstance(niche, list):
        niche = json.dumps(niche, ensure_ascii=False)
    sources = meta.get("sources", [])
    sources_json = json.dumps(sources, ensure_ascii=False) if not isinstance(sources, str) else sources
    evergreen_id = meta.get("evergreen_id") or None

    with sqlite3.connect(db) as conn:
        _ensure_schema(conn)
        conn.execute("""
            INSERT INTO pieces (
                piece_id, format, niche, topic, hook, archetype, pillar, evergreen_id,
                status, ethics_score, llm_cost_usd, sources_json,
                drive_path, produced_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?, ?, '', ?, ?, ?)
            ON CONFLICT(piece_id) DO UPDATE SET
                status       = 'pending_review',
                topic        = COALESCE(excluded.topic, pieces.topic),
                hook         = COALESCE(excluded.hook, pieces.hook),
                archetype    = COALESCE(excluded.archetype, pieces.archetype),
                pillar       = COALESCE(excluded.pillar, pieces.pillar),
                evergreen_id = COALESCE(excluded.evergreen_id, pieces.evergreen_id),
                ethics_score = excluded.ethics_score,
                llm_cost_usd = excluded.llm_cost_usd,
                sources_json = excluded.sources_json,
                updated_at   = excluded.updated_at
        """, (
            piece_id,
            meta.get("format", "carrusel"),
            niche,
            meta.get("topic", ""),
            meta.get("hook", ""),
            meta.get("archetype", ""),
            meta.get("pillar", ""),
            evergreen_id,
            meta.get("ethics_score", "green"),
            float(meta.get("llm_cost_usd", 0) or 0),
            sources_json,
            meta.get("created_at", now),
            meta.get("created_at", now),
            now,
        ))

        if evergreen_id:
            conn.execute(
                "INSERT INTO evergreen_usage (evergreen_id, piece_id, used_at) VALUES (?, ?, ?)",
                (evergreen_id, piece_id, now),
            )


def _save_message_id(piece_id: str, msg_id: int):
    db = pieces_db_path()
    if not db.exists():
        return
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE pieces SET telegram_message_id=? WHERE piece_id=?",
            (str(msg_id), piece_id),
        )


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

_FORMAT_DRIVE_INCLUDE = {
    "carrusel":    ["--include", "slide-*.png"],
    "carrusel-ds": ["--include", "slide-*.png"],
    "animacion":   ["--include", "animation.mp4"],
    "guion":       ["--include", "guion.md"],
}


def _sync_drive(piece_id: str, piece_dir: Path) -> str | None:
    remote = os.environ.get("RCLONE_REMOTE", "gdrive")
    root   = os.environ.get("DRIVE_ROOT", "Nolan")

    meta = {}
    mp   = piece_dir / "metadata.json"
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))
    fmt      = meta.get("format", "carrusel")
    subfolder = _FORMAT_DRIVE_FOLDER.get(fmt, "Otros")
    dest     = f"{remote}:{root}/{subfolder}/{piece_id}/"

    includes = list(_FORMAT_DRIVE_INCLUDE.get(fmt, []))
    includes += [
        "--include", "caption.md",
        "--include", "sources.md",
        "--include", "alt_text.md",
        "--include", "metadata.json",
        "--exclude", "*",
    ]

    cmd = [
        "rclone", "copy", str(piece_dir) + "/", dest,
        "--transfers", "4", "--checkers", "8",
        *includes,
    ]
    print(f"[package] rclone → {dest}")

    for attempt in range(3):
        try:
            subprocess.run(cmd, check=True, timeout=180)
            return dest
        except FileNotFoundError:
            print("[package] ERROR: rclone no encontrado en PATH", file=sys.stderr)
            return None
        except subprocess.CalledProcessError as e:
            if attempt == 2:
                print(f"[package] WARN: Drive sync falló ({e})", file=sys.stderr)
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
        raise RuntimeError("Falta TELEGRAM_ALLOWED_USERS")
    return raw


def _inline_keyboard(piece_id: str, drive_url: str | None) -> dict:
    """Botones Aprobar / Rechazar / Editar + Ver en Drive opcional."""
    kb = {"inline_keyboard": [[
        {"text": "Aprobar",  "callback_data": f"aprobar|{piece_id}"},
        {"text": "Rechazar", "callback_data": f"rechazar|{piece_id}"},
        {"text": "Editar",   "callback_data": f"editar|{piece_id}"},
    ]]}
    if drive_url and drive_url.startswith("https://"):
        kb["inline_keyboard"].append([{"text": "Ver en Drive", "url": drive_url}])
    return kb


def _send_telegram(piece_id: str, piece_dir: Path, drive_url: str | None) -> int | None:
    try:
        base    = _bot_base()
        chat_id = _mateo_chat_id()
    except RuntimeError as e:
        print(f"[package] WARN: {e}", file=sys.stderr)
        return None

    meta   = json.loads((piece_dir / "metadata.json").read_text(encoding="utf-8"))
    fmt    = meta.get("format", "carrusel")
    cost   = meta.get("llm_cost_usd", 0)
    niche  = meta.get("niche", "")
    ethics = meta.get("ethics_score", "green")
    keyboard = _inline_keyboard(piece_id, drive_url)

    summary = (
        f"[{fmt}] {piece_id}\n"
        f"nicho={niche} · ethics={ethics} · costo=${cost:.3f}"
    )
    msg_id: int | None = None

    if fmt in ("carrusel", "carrusel-ds"):
        msg_id = _send_carrusel(base, chat_id, piece_dir, summary, keyboard)
    elif fmt == "animacion":
        msg_id = _send_animacion(base, chat_id, piece_dir, summary, keyboard)
    elif fmt == "guion":
        msg_id = _send_guion(base, chat_id, piece_dir, summary, keyboard)
    else:
        msg_id = _send_text_only(base, chat_id, summary, keyboard)

    return msg_id


def _send_carrusel(base: str, chat_id: str, piece_dir: Path,
                   summary: str, keyboard: dict) -> int | None:
    slides = sorted(piece_dir.glob("slide-*.png"))[:10]
    msg_id = None

    if slides:
        media, file_handles = [], {}
        for i, p in enumerate(slides):
            fname = f"f{i}"
            media.append({
                "type":  "photo",
                "media": f"attach://{fname}",
                **({"caption": summary} if i == 0 else {}),
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
            print(f"[package] media group enviado ({len(slides)} slides)")
        except Exception as e:
            print(f"[package] WARN: media group falló ({e})", file=sys.stderr)
        finally:
            for _, (_, fh, _) in file_handles.items():
                fh.close()

    # Mensaje con botones inline
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(f"{base}/sendMessage", json={
                "chat_id": chat_id,
                "text": summary,
                "reply_markup": keyboard,
            })
            r.raise_for_status()
            if msg_id is None:
                msg_id = r.json()["result"]["message_id"]
    except Exception as e:
        print(f"[package] WARN: sendMessage falló ({e})", file=sys.stderr)

    return msg_id


def _send_animacion(base: str, chat_id: str, piece_dir: Path,
                    summary: str, keyboard: dict) -> int | None:
    mp4   = piece_dir / "animation.mp4"
    cover = piece_dir / "cover.jpg"
    msg_id = None

    if mp4.exists():
        files = {"video": (mp4.name, open(mp4, "rb"), "video/mp4")}
        data  = {"chat_id": chat_id, "caption": summary, "supports_streaming": "true"}
        if cover.exists():
            files["thumbnail"] = (cover.name, open(cover, "rb"), "image/jpeg")
        try:
            with httpx.Client(timeout=120) as client:
                r = client.post(f"{base}/sendVideo", data=data, files=files)
                r.raise_for_status()
                msg_id = r.json()["result"]["message_id"]
            print("[package] sendVideo OK")
        except Exception as e:
            print(f"[package] WARN: sendVideo falló ({e})", file=sys.stderr)
        finally:
            for _, (_, fh, _) in files.items():
                fh.close()

    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(f"{base}/sendMessage", json={
                "chat_id": chat_id,
                "text": summary,
                "reply_markup": keyboard,
            })
            r.raise_for_status()
            if msg_id is None:
                msg_id = r.json()["result"]["message_id"]
    except Exception as e:
        print(f"[package] WARN: sendMessage botones falló ({e})", file=sys.stderr)

    return msg_id


def _send_guion(base: str, chat_id: str, piece_dir: Path,
                summary: str, keyboard: dict) -> int | None:
    guion_path = piece_dir / "guion.md"
    preview    = guion_path.read_text(encoding="utf-8").strip()[:800] if guion_path.exists() else ""
    msg_text   = f"{summary}\n\n--- script preview ---\n{preview}"
    msg_id     = None

    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(f"{base}/sendMessage", json={
                "chat_id":    chat_id,
                "text":       msg_text,
                "reply_markup": keyboard,
            })
            r.raise_for_status()
            msg_id = r.json()["result"]["message_id"]
        print("[package] guion enviado a Telegram")
    except Exception as e:
        print(f"[package] WARN: sendMessage guion falló ({e})", file=sys.stderr)

    return msg_id


def _send_text_only(base: str, chat_id: str, summary: str, keyboard: dict) -> int | None:
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(f"{base}/sendMessage", json={
                "chat_id": chat_id,
                "text": summary,
                "reply_markup": keyboard,
            })
            r.raise_for_status()
            return r.json()["result"]["message_id"]
    except Exception as e:
        print(f"[package] WARN: sendMessage falló ({e})", file=sys.stderr)
        return None


def _notify_block(piece_id: str, ethics: EthicsResult, dry_run: bool):
    msg = (
        f"[bloqueo] SOUL rojo en draft {piece_id}\n"
        f"regla: {ethics.rule_id} — {ethics.description}\n"
        f"texto: {ethics.matched_text[:120]}\n"
        f"/autofix {piece_id} o /rechazar {piece_id}"
    )
    print(msg, file=sys.stderr)
    if dry_run:
        return
    try:
        base    = _bot_base()
        chat_id = _mateo_chat_id()
        with httpx.Client(timeout=15) as client:
            client.post(f"{base}/sendMessage", json={"chat_id": chat_id, "text": msg})
    except Exception:
        pass


def _notify_block_alignment(piece_id: str, alignment: AlignmentResult, dry_run: bool):
    failed_red = [c for c in alignment.checks if c.severity == "red"]
    lines = [f"[bloqueo] Alignment rojo en draft {piece_id}"]
    for c in failed_red:
        lines.append(f"  · {c.id}: {c.reason}")
    lines.append(f"/autofix {piece_id} o /rechazar {piece_id}")
    msg = "\n".join(lines)
    print(msg, file=sys.stderr)
    if dry_run:
        return
    try:
        base    = _bot_base()
        chat_id = _mateo_chat_id()
        with httpx.Client(timeout=15) as client:
            client.post(f"{base}/sendMessage", json={"chat_id": chat_id, "text": msg})
    except Exception:
        pass


def _print_preview(piece_id: str, piece_dir: Path, drive_url: str | None):
    meta  = json.loads((piece_dir / "metadata.json").read_text(encoding="utf-8"))
    fmt   = meta.get("format", "carrusel")
    cost  = meta.get("llm_cost_usd", 0)
    print("\n--- Telegram preview (dry-run) ---")
    print(f"[{fmt}] {piece_id}")
    print(f"nicho={meta.get('niche')} · ethics={meta.get('ethics_score')} · costo=${cost:.4f}")

    if fmt == "carrusel":
        n = len(list(piece_dir.glob("slide-*.png")))
        print(f"{n} slides")
    elif fmt == "animacion":
        exists = (piece_dir / "animation.mp4").exists()
        print(f"animation.mp4 presente={exists}")
    elif fmt == "guion":
        gp = piece_dir / "guion.md"
        if gp.exists():
            print("--- guion preview ---")
            print(gp.read_text(encoding="utf-8").strip()[:400])

    print("Botones: [Aprobar] [Rechazar] [Editar]", end="")
    if drive_url:
        print(f" [Ver en Drive → {drive_url}]", end="")
    print("\n---\n")


if __name__ == "__main__":
    main()
