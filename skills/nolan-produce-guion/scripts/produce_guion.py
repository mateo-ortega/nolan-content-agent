"""
nolan-produce-guion — genera script de teleprompter para cara a cámara.

Uso:
    python produce_guion.py --brief /tmp/brief.yaml
    python produce_guion.py --brief /tmp/brief.yaml --piece-id 2026-04-28-slug
    python produce_guion.py --brief /tmp/brief.yaml --dry-run

Salida (staging/<piece_id>/):
    guion.md        — script teleprompter completo
    caption.md      — caption para Instagram
    alt_text.md     — descripción accesibilidad
    sources.md      — fuentes citadas
    metadata.json   — metadatos de la pieza
    content.yaml    — schema mínimo para callbacks
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent.parent.parent
))
sys.path.insert(0, str(PROJECT_ROOT))

from sapiens.nolan_llm_router import load_router   # noqa: E402

NOLAN_PYTHON = os.environ.get("NOLAN_PYTHON", "python3.12")

_GUION_SYSTEM = """Eres Nolan, productor de contenido de Sapiens by Shift (@sapiens.ed).

Escribes scripts de teleprompter para que Mateo (ingeniero químico UNAL, fundador
de Sapiens, 21 años, Medellín) grabe reels a cámara como talking-head.

El tono es el de Mateo: **autoridad técnica + calidez**. Como un profesor
universitario joven que respeta al espectador — explica con rigor, sin jerga
innecesaria, sin condescendencia. Diagnostica antes de prescribir. No es el
compañero de aprendizaje: es el experto que muestra el método.

Habla de tú. Sin emojis en el guión. Sin corporativo.

FORMATO DE SALIDA — JSON estricto, sin markdown fuera del JSON:
{
  "guion": {
    "duracion_estimada_seg": 45,
    "gancho": "TEXTO DEL GANCHO (máx 2 líneas, la frase que abre el reel)",
    "cuerpo": [
      {"beat": 1, "texto": "...", "cue": "pausa / énfasis / gesto"},
      {"beat": 2, "texto": "...", "cue": "..."}
    ],
    "cierre_cta": "TEXTO DE CIERRE + llamada a acción"
  },
  "caption": "Caption completo para Instagram (máx 2200 chars, 3-5 párrafos, hashtags al final)",
  "alt_text": "Descripción accesible del video (1-2 oraciones, sin spoilers del gancho)",
  "fuentes": ["url o titulo de fuente 1", "url o titulo de fuente 2"]
}

Reglas del guión:
- Duración óptima: 30-60 segundos (reels educativos colombianos)
- Gancho: plantea una tensión técnica o dato concreto en ≤5 palabras — no una promesa emocional. Corta el scroll por curiosidad intelectual, no por miedo.
- Cuerpo: máx 4 beats, cada beat ≤ 3 oraciones cortas. Ritmo conversacional. Al menos un dato verificable o ejemplo concreto.
- Cierre: acción de conversión directa. Elige UNA palabra clave del tema (≤2 sílabas, fácil de recordar — ej: "ruta", "caso", "mapa", "test") y cierra con: "Comenta '[palabra]' y te envío el caso completo por DM." NO usar "guarda esto", "aplícalo esta semana", "cuéntame en los comentarios", "sesión gratis" ni "clase de muestra gratis".
- Prohibido: "revolucionario", "secreto", "truco", "garantizado", "insane", "compañero de aprendizaje", "aprende a tu medida"
- Prohibido: prometer resultados sin esfuerzo
- Prohibido: posicionar la IA como el héroe (la IA es herramienta del método)
- Prohibido: mencionar marcas de la competencia por nombre

Valores SOUL Sapiens:
- Evidencia sobre opinión. Datos concretos si los hay.
- Respeto al tiempo: cada beat se gana su espacio.
- Silencio editorial: si no hay algo útil que decir, no lo digas.
"""


def main():
    ap = argparse.ArgumentParser(description="Genera guión teleprompter para Sapiens")
    ap.add_argument("--brief",    required=True, help="Ruta al brief YAML")
    ap.add_argument("--piece-id", default="",   help="piece_id explícito (opcional)")
    ap.add_argument("--dry-run",  action="store_true")
    args = ap.parse_args()

    with open(args.brief, encoding="utf-8") as f:
        brief = yaml.safe_load(f)

    piece_id = args.piece_id or brief.get("piece_id") or _slug(brief)
    staging  = PROJECT_ROOT / "staging" / piece_id
    staging.mkdir(parents=True, exist_ok=True)

    import shutil
    shutil.copy(args.brief, staging / "brief.yaml")

    print(json.dumps({"status": "generating", "piece_id": piece_id}))

    if args.dry_run:
        _write_placeholder(staging, piece_id, brief)
        print(json.dumps({"piece_id": piece_id, "status": "dry_run_ok"}))
        return

    # ── LLM ──────────────────────────────────────────────────────────────────
    router   = load_router()
    user_msg = _build_user_msg(brief, piece_id)

    resp = router.call(
        task="copy.guion_teleprompter",
        messages=[
            {"role": "system", "content": _GUION_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        cache_system=True,
        piece_id=piece_id,
    )

    raw = resp.text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:]).rstrip("`").strip()

    data = json.loads(raw)
    guion  = data["guion"]
    llm_cost = resp.cost_usd

    # ── Escribir archivos ─────────────────────────────────────────────────────
    _write_guion_md(staging, guion)
    _write_caption(staging, data.get("caption", ""))
    _write_alt_text(staging, data.get("alt_text", ""))
    _write_sources(staging, data.get("fuentes", []))
    _write_metadata(staging, piece_id, brief, guion, llm_cost)
    _write_content_yaml(staging, piece_id, brief)

    print(json.dumps({
        "piece_id":    piece_id,
        "format":      "guion",
        "duracion_seg": guion.get("duracion_estimada_seg", 0),
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
        f"Formato: guion cara a cámara\n"
        f"Hook del brief: {brief.get('hook', '')}\n"
        f"Tesis / ángulo: {brief.get('thesis', '')}\n"
        f"Tono: {brief.get('tone_calibration', 'jovenes_directo')}\n"
        f"Nota de edición (si aplica): {brief.get('nota_edicion', '')}\n\n"
        "Genera el guión completo en JSON."
    )


def _write_guion_md(staging: Path, guion: dict):
    lines = [
        "# Guión — Cara a Cámara",
        "",
        f"**Duración estimada:** {guion.get('duracion_estimada_seg', '~45')} segundos",
        "",
        "---",
        "",
        "## GANCHO",
        "",
        guion.get("gancho", ""),
        "",
        "---",
        "",
        "## CUERPO",
        "",
    ]
    for beat in guion.get("cuerpo", []):
        lines.append(f"**Beat {beat.get('beat', '?')}**  `[{beat.get('cue', '')}]`")
        lines.append("")
        lines.append(beat.get("texto", ""))
        lines.append("")
    lines += [
        "---",
        "",
        "## CIERRE / CTA",
        "",
        guion.get("cierre_cta", ""),
        "",
    ]
    (staging / "guion.md").write_text("\n".join(lines), encoding="utf-8")


def _write_caption(staging: Path, caption: str):
    (staging / "caption.md").write_text(caption, encoding="utf-8")


def _write_alt_text(staging: Path, alt: str):
    (staging / "alt_text.md").write_text(alt, encoding="utf-8")


def _write_sources(staging: Path, fuentes: list):
    lines = ["# Fuentes\n"]
    for f in fuentes:
        lines.append(f"- {f}")
    (staging / "sources.md").write_text("\n".join(lines), encoding="utf-8")


def _write_metadata(staging: Path, piece_id: str, brief: dict, guion: dict, cost: float):
    meta = {
        "piece_id":       piece_id,
        "format":         "guion",
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
        "archetype":      brief.get("archetype", "testimonial"),
        "duracion_seg":   guion.get("duracion_estimada_seg", 0),
    }
    (staging / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_content_yaml(staging: Path, piece_id: str, brief: dict):
    content = {
        "piece_id": piece_id,
        "format":   "guion",
        "niche":    brief.get("niche", ""),
        "topic":    brief.get("thesis", ""),
    }
    (staging / "content.yaml").write_text(
        yaml.dump(content, allow_unicode=True, default_flow_style=False),
        encoding="utf-8"
    )


def _write_placeholder(staging: Path, piece_id: str, brief: dict):
    _write_guion_md(staging, {
        "duracion_estimada_seg": 45,
        "gancho": "[DRY RUN — gancho aquí]",
        "cuerpo": [{"beat": 1, "texto": "[cuerpo dry run]", "cue": "natural"}],
        "cierre_cta": "[cta dry run]",
    })
    _write_caption(staging, "[dry run caption]")
    _write_alt_text(staging, "[dry run alt text]")
    _write_sources(staging, [])
    _write_metadata(staging, piece_id, brief,
                    {"duracion_estimada_seg": 45}, 0.0)
    _write_content_yaml(staging, piece_id, brief)


def _slug(brief: dict) -> str:
    date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    raw  = brief.get("hook", brief.get("thesis", "guion"))[:35]
    slug = re.sub(r"[^a-z0-9]", "-", raw.lower()).strip("-")
    return f"{date}-{slug}"


if __name__ == "__main__":
    main()
