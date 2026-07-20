"""
nolan-produce-animacion — genera MP4 Manim 1080×1920 para Reels educativos.

Uso:
    python produce_animacion.py --brief /tmp/brief.yaml
    python produce_animacion.py --brief /tmp/brief.yaml --piece-id 2026-04-28-slug
    python produce_animacion.py --brief /tmp/brief.yaml --dry-run

Salida (staging/<piece_id>/):
    animation.mp4   — video vertical 1080×1920
    cover.jpg       — frame representativo (segundo 1)
    anim_params.json — parámetros usados para el render
    caption.md
    alt_text.md
    sources.md
    metadata.json
    content.yaml
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_CHECKER = Path(__file__).parent / "animacion_check.py"

import yaml

PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent.parent.parent
))
sys.path.insert(0, str(PROJECT_ROOT))

from sapiens.nolan_llm_router import load_router   # noqa: E402

NOLAN_PYTHON = os.environ.get("NOLAN_PYTHON", "python3.12")
_RENDER_SCRIPT = Path(__file__).parent / "animacion_render.py"

# Palabras clave que indican un brief B2B/tech fuera del nicho de Sapiens
_B2B_KEYWORDS = {"empresas", "b2b", "negocios", "clientes corporativos", "api ",
                  "developers", "automatización de negocio", "atención al cliente"}
_VALID_NICHES  = {"padres", "familias", "jóvenes", "preicfes", "estudiantes", "adolescentes"}


def _validate_niche(brief: dict):
    niche = brief.get("niche", "").lower()
    for kw in _B2B_KEYWORDS:
        if kw in niche:
            raise SystemExit(
                f"[NOLAN] Brief fuera de nicho Sapiens: '{niche}'. "
                "Las animaciones son solo para padres, jóvenes o estudiantes. "
                "Revisar el brief antes de continuar."
            )

_ANIM_SYSTEM = """Eres Nolan, productor de contenido de Sapiens by Shift (@sapiens.ed).

Generas parámetros JSON para el sistema de templates Manim. El JSON controla una
animación educativa vertical 9:16 (1080×1920) de 15–30 segundos.

TEMPLATES DISPONIBLES:

1. BarChart — barras horizontales (comparaciones, rankings, datos porcentuales)
   {
     "template": "BarChart",
     "hook": "línea 1\\nlínea 2 (énfasis, aparece en color)\\nlínea 3 opcional",
     "hook_accent_color": "gold|teal|red|violet",
     "title": "subtítulo opcional (máx 45 chars)",
     "bars": [
       {"label": "Método X", "value": 75, "highlight": true, "color": "teal"},
       {"label": "Método Y", "value": 30, "highlight": false, "color": ""}
     ],
     "conclusion": "mensaje línea 1\\nmensaje teal (línea 2)"
   }
   Reglas bars: value = 0–100 (porcentaje). Máx 7 barras. highlight=true en 1–2 items.
   Las barras no-highlight son grises. Las highlight usan el color indicado.

2. CurveReveal — curvas sobre ejes X/Y (tendencias, decaimiento, crecimiento)
   {
     "template": "CurveReveal",
     "hook": "...",
     "x_label": "días",
     "y_label": "retención",
     "x_range": [0, 7, 1],
     "y_range": [0, 1.0, 0.5],
     "curves": [
       {"label": "sin repaso", "color": "red", "type": "decay"},
       {"label": "repaso espaciado", "color": "teal", "type": "growth"},
       {"label": "personalizada", "color": "gold", "type": "custom",
        "custom_points": [[0,0.9],[2,0.6],[4,0.7],[7,0.65]]}
     ],
     "markers": [{"x": 1.0, "curve_index": 1}],
     "conclusion": "..."
   }
   Tipos de curva: "decay" (exp decreciente), "growth" (exp creciente), "custom" (interpolación lineal).
   markers: puntos GOLD con línea vertical punteada. curve_index = índice en curves[].

3. StepReveal — pasos secuenciales (métodos, frameworks, procesos)
   {
     "template": "StepReveal",
     "hook": "...",
     "title": "título opcional",
     "steps": [
       {"number": "1", "text": "Texto del paso (≤45 chars)", "color": "teal"},
       {"number": "2", "text": "...", "color": "gold"}
     ],
     "conclusion": "..."
   }
   Máx 5 pasos. Colores disponibles: teal, gold, red, violet.

CAMPOS ADICIONALES (en todos los templates):
{
  "caption": "Caption para Instagram (máx 2200 chars, 3-5 párrafos). OBLIGATORIO: cierra antes de los hashtags con la línea CTA exacta: 'Si quieres aplicar este método a tu hijo/a, agenda diagnóstico — link en bio.' Hashtags al final, máx 15.",
  "alt_text": "Descripción accesible del video (1-2 oraciones, sin spoilers del gancho)",
  "fuentes": ["url o título de fuente 1", "..."]
}

Reglas del hook:
- Línea 2 (si existe) es la que impacta — usa acento de color (hook_accent_color)
- Máx 3 líneas, cada línea ≤ 7 palabras
- Debe cortar el scroll: dato sorprendente, pregunta, afirmación contraintuitiva

Reglas de conclusion:
- 2 líneas máximo. Línea 1: blanca. Línea 2: teal (se formatea automáticamente).
- Mensaje que refuerza la tesis central del brief.

SALIDA: JSON estricto, sin markdown fuera del JSON, sin comentarios.
"""


def main():
    ap = argparse.ArgumentParser(description="Genera animación Manim para Sapiens")
    ap.add_argument("--brief",    required=True, help="Ruta al brief YAML")
    ap.add_argument("--piece-id", default="",   help="piece_id explícito (opcional)")
    ap.add_argument("--dry-run",  action="store_true")
    args = ap.parse_args()

    with open(args.brief, encoding="utf-8") as f:
        brief = yaml.safe_load(f)

    _validate_niche(brief)

    piece_id = args.piece_id or brief.get("piece_id") or _slug(brief)
    staging  = PROJECT_ROOT / "staging" / piece_id
    staging.mkdir(parents=True, exist_ok=True)

    shutil.copy(args.brief, staging / "brief.yaml")

    print(json.dumps({"status": "generating", "piece_id": piece_id}))

    if args.dry_run:
        _write_placeholder(staging, piece_id, brief)
        print(json.dumps({"piece_id": piece_id, "status": "dry_run_ok"}))
        return

    # ── LLM: genera params del template ──────────────────────────────────────
    router   = load_router()
    user_msg = _build_user_msg(brief, piece_id)

    resp = router.call(
        task="animacion.params",
        messages=[
            {"role": "system", "content": _ANIM_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        piece_id=piece_id,
    )

    raw = resp.text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:]).rstrip("`").strip()

    params = json.loads(raw)
    llm_cost = resp.cost_usd

    # ── Persistir params ──────────────────────────────────────────────────────
    params_file = staging / "anim_params.json"
    params_file.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Render Manim ──────────────────────────────────────────────────────────
    media_dir = staging / "media"
    media_dir.mkdir(exist_ok=True)

    env = os.environ.copy()
    env["ANIM_PARAMS_PATH"] = str(params_file)

    cmd = [
        NOLAN_PYTHON, "-m", "manim",
        str(_RENDER_SCRIPT),
        "SapiensAnimScene",
        "-qh",
        "--resolution", "1080,1920",
        "--output_file", "animation.mp4",
        "--media_dir", str(media_dir),
    ]
    print(json.dumps({"status": "rendering", "piece_id": piece_id}))
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(staging))

    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        print(json.dumps({"piece_id": piece_id, "status": "render_failed",
                          "stderr": result.stderr[-500:]}))
        sys.exit(1)

    # ── Mover MP4 a staging root ──────────────────────────────────────────────
    mp4_candidates = list(media_dir.rglob("animation.mp4"))
    if not mp4_candidates:
        mp4_candidates = list(media_dir.rglob("*.mp4"))
    if mp4_candidates:
        shutil.move(str(mp4_candidates[0]), staging / "animation.mp4")

    # ── Safe zone check ───────────────────────────────────────────────────────
    animation_path = staging / "animation.mp4"
    if animation_path.exists() and _CHECKER.exists():
        check = subprocess.run(
            [NOLAN_PYTHON, str(_CHECKER), str(animation_path)],
            capture_output=True, text=True, timeout=120,
        )
        if check.returncode == 1:
            print(f"[WARN] safe-zone overflow detectado:\n{check.stderr}", file=sys.stderr)
            print(json.dumps({"piece_id": piece_id, "status": "safezone_fail",
                              "detail": check.stderr[-800:]}))
            sys.exit(1)

    # ── Cover JPG (frame en t=1s) ─────────────────────────────────────────────
    if animation_path.exists():
        _extract_cover(animation_path, staging / "cover.jpg")

    # ── Escribir archivos de texto ────────────────────────────────────────────
    _write_caption(staging, params.get("caption", ""))
    _write_alt_text(staging, params.get("alt_text", ""))
    _write_sources(staging, params.get("fuentes", []))
    _write_metadata(staging, piece_id, brief, params, llm_cost)
    _write_content_yaml(staging, piece_id, brief)

    print(json.dumps({
        "piece_id":    piece_id,
        "format":      "animacion",
        "template":    params.get("template", ""),
        "llm_cost_usd": round(llm_cost, 4),
        "status":      "ok",
    }))


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _build_user_msg(brief: dict, piece_id: str) -> str:
    return (
        f"piece_id: {piece_id}\n"
        f"Nicho: {brief.get('niche', '')}\n"
        f"Hook del brief: {brief.get('hook', '')}\n"
        f"Tesis / ángulo: {brief.get('thesis', '')}\n"
        f"Archetype: {brief.get('archetype', '')}\n"
        f"Tono: {brief.get('tone_calibration', 'jovenes_directo')}\n\n"
        "Elige el template más apropiado y genera los parámetros JSON completos."
    )


def _extract_cover(mp4: Path, dest: Path):
    try:
        subprocess.run(
            ["ffmpeg", "-i", str(mp4), "-ss", "00:00:01", "-frames:v", "1",
             str(dest), "-y"],
            capture_output=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _write_caption(staging: Path, caption: str):
    (staging / "caption.md").write_text(caption, encoding="utf-8")


def _write_alt_text(staging: Path, alt: str):
    (staging / "alt_text.md").write_text(alt, encoding="utf-8")


def _write_sources(staging: Path, fuentes: list):
    lines = ["# Fuentes\n"]
    for f in fuentes:
        lines.append(f"- {f}")
    (staging / "sources.md").write_text("\n".join(lines), encoding="utf-8")


def _write_metadata(staging: Path, piece_id: str, brief: dict, params: dict, cost: float):
    mp4 = staging / "animation.mp4"
    meta = {
        "piece_id":       piece_id,
        "format":         "animacion",
        "niche":          brief.get("niche", ""),
        "topic":          brief.get("topic") or brief.get("thesis", brief.get("hook", "")),
        "pillar":         brief.get("pillar", "tecnica_densa"),
        "evergreen_id":   brief.get("evergreen_id", ""),
        "hook":           brief.get("hook", ""),
        "sources":        [],
        "llm_cost_usd":   round(cost, 5),
        "ethics_score":   "green",
        "status":         "pending_review",
        "created_at":     datetime.now(tz=timezone.utc).isoformat(),
        "archetype":      brief.get("archetype", "datos"),
        "manim_template": params.get("template", ""),
        "render_exists":  mp4.exists(),
    }
    (staging / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_content_yaml(staging: Path, piece_id: str, brief: dict):
    content = {
        "piece_id": piece_id,
        "format":   "animacion",
        "niche":    brief.get("niche", ""),
        "topic":    brief.get("thesis", ""),
    }
    (staging / "content.yaml").write_text(
        yaml.dump(content, allow_unicode=True, default_flow_style=False),
        encoding="utf-8"
    )


def _write_placeholder(staging: Path, piece_id: str, brief: dict):
    placeholder_params = {
        "template": "BarChart",
        "hook": "[DRY RUN]\ngancho aquí\nlínea 3",
        "bars": [{"label": "Item A", "value": 70, "highlight": True, "color": "teal"}],
        "conclusion": "[DRY RUN]\nconclusión aquí",
        "caption": "[dry run caption]",
        "alt_text": "[dry run alt text]",
        "fuentes": [],
    }
    (staging / "anim_params.json").write_text(
        json.dumps(placeholder_params, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_caption(staging, "[dry run caption]")
    _write_alt_text(staging, "[dry run alt text]")
    _write_sources(staging, [])
    _write_metadata(staging, piece_id, brief, placeholder_params, 0.0)
    _write_content_yaml(staging, piece_id, brief)


def _slug(brief: dict) -> str:
    date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    raw  = brief.get("hook", brief.get("thesis", "anim"))[:35]
    slug = re.sub(r"[^a-z0-9]", "-", raw.lower()).strip("-")
    return f"{date}-{slug}"


if __name__ == "__main__":
    main()
