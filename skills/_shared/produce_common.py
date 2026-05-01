"""
skills/_shared/produce_common.py

Utilidades compartidas entre scripts de producción de carruseles Nolan
(produce_carrusel.py — gestos, produce_carrusel_ds.py — design system).

Funciones extraídas:
  - generate_caption: caption final (Sonnet, cached)
  - caption_dry_run: caption placeholder para --dry-run
  - build_alt_text, build_sources_md, build_preview, build_metadata
  - abort_ethics: salida estandarizada cuando ethics gate da rojo

Cada función es self-contained — no asume el formato del content.yaml
(quien llama pasa la lista de textos por slide explícitamente).
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Caption — Claude Sonnet con cached system prompt
# ---------------------------------------------------------------------------

_CAPTION_USER_TEMPLATE = """\
Escribe el caption de Instagram para esta pieza de sapiens (@sapiens.ed).

Nicho: {niche}
Hook: {hook}
Tesis: {thesis}

Slides:
{slides}

Reglas:
- 600-900 caracteres.
- Sin emojis.
- Primera línea = hook (es lo único que IG muestra en feed antes del "ver más").
- Cierre: acción concreta pequeña (no "síganos", no "dale like").
- Tuteo colombiano neutro.
- Citar fuente si hay dato técnico.
"""


def generate_caption(
    router,
    soul_text: str,
    brand_text: str,
    brief: dict,
    slide_texts_per_slide: list[list[str]],
    piece_id: str,
) -> tuple[str, float]:
    """
    Genera el caption final con Sonnet (cached system).

    Args:
        router: instancia de LLMRouter
        soul_text: contenido de SOUL.md
        brand_text: contenido de memory/brand_context.md
        brief: dict del brief (con keys niche, hook, thesis)
        slide_texts_per_slide: lista de listas — cada sublista son los strings del slide
        piece_id: id de la pieza (para tracking de costo)

    Returns:
        (caption_text, cost_usd)
    """
    system = f"{soul_text}\n\n---\n\n{brand_text}"
    slides_txt = "\n".join(
        f"Slide {i}: {' '.join(texts)}"
        for i, texts in enumerate(slide_texts_per_slide, start=1)
    )
    user = _CAPTION_USER_TEMPLATE.format(
        niche=brief.get("niche", ""),
        hook=brief.get("hook", ""),
        thesis=brief.get("thesis", ""),
        slides=slides_txt,
    )
    resp = router.call(
        task="copy.final_caption",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        cache_system=True,
        piece_id=piece_id,
    )
    return resp.text.strip(), resp.cost_usd


def caption_dry_run(brief: dict) -> str:
    """Caption placeholder cuando --dry-run."""
    return (
        f"{brief.get('hook', 'Lectura crítica ICFES.')}\n\n"
        f"{brief.get('thesis', '')}\n\n"
        "[Caption generado en dry-run — reemplazar en producción real]"
    )


# ---------------------------------------------------------------------------
# Alt text — descripción simple por slide
# ---------------------------------------------------------------------------

def build_alt_text(slide_descriptions: list[str]) -> str:
    """
    Construye el alt_text.md a partir de descripciones por slide.

    slide_descriptions: lista de strings, uno por slide (puede ser el texto
    plano del slide concatenado, o una descripción visual breve).
    """
    lines = []
    for i, desc in enumerate(slide_descriptions, start=1):
        lines.append(f"## Slide {i}\n{desc}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# sources.md — fuentes del brief
# ---------------------------------------------------------------------------

def build_sources_md(brief: dict) -> str:
    sources = brief.get("sources", [])
    if not sources:
        return "Sin fuentes específicas registradas en el brief."
    lines = ["# Fuentes\n"]
    for s in sources:
        lines.append(f"- {s.get('citation', s.get('url', ''))}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Preview JPG (480px) — thumbnail para Telegram
# ---------------------------------------------------------------------------

def build_preview(slide01_path: Path, preview_path: Path) -> None:
    try:
        from PIL import Image
        img = Image.open(slide01_path)
        img.thumbnail((480, 600))
        img.save(preview_path, "JPEG", quality=85)
    except (ImportError, Exception):
        shutil.copy(slide01_path, preview_path)


# ---------------------------------------------------------------------------
# metadata.json — registro completo del piece
# ---------------------------------------------------------------------------

def build_metadata(
    brief: dict,
    piece_id: str,
    llm_cost: float,
    ethics_status: str,
    extra_fields: dict | None = None,
) -> dict:
    """
    Construye metadata.json. extra_fields permite agregar campos específicos
    del skill (e.g. {'visual_skill': 'design-system'}).
    """
    meta = {
        "piece_id": piece_id,
        "format": brief.get("format", "carrusel"),
        "niche": brief.get("niche"),
        "topic": brief.get("thesis", ""),
        "archetype": brief.get("archetype"),
        "sources": brief.get("sources", []),
        "llm_cost_usd": round(llm_cost, 6),
        "ethics_score": ethics_status,
        "status": "draft",
        "created_at": datetime.now(tz=timezone.utc).astimezone().isoformat(),
        "hook": brief.get("hook"),
        "slides_count_estimate": brief.get("slides_count_estimate"),
        "tone_calibration": brief.get("tone_calibration"),
        "decision_method": brief.get("decision_method", "rules"),
    }
    if extra_fields:
        meta.update(extra_fields)
    return meta


# ---------------------------------------------------------------------------
# Ethics abort — salida estandarizada cuando gate.check() = red
# ---------------------------------------------------------------------------

def abort_ethics(piece_id: str, result) -> None:
    """Imprime diagnóstico ethics y termina con sys.exit(2)."""
    print(
        f"[ETHICS RED] regla={result.rule_id}: {result.description}\n"
        f"  texto: {result.matched_text}",
        file=sys.stderr,
    )
    print(
        f"[bloqueo] SOUL rojo en draft {piece_id}\n"
        f"• regla: {result.rule_id} — {result.description}\n"
        f"• /autofix {piece_id} o /rechazar {piece_id}"
    )
    sys.exit(2)


# ---------------------------------------------------------------------------
# Helpers comunes para piece_dir
# ---------------------------------------------------------------------------

def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def copy_slide01_to_cover_and_preview(staging: Path) -> None:
    """Si existe slide-01.png, lo copia a cover.jpg y genera preview.jpg."""
    slide01 = staging / "slide-01.png"
    if slide01.exists():
        shutil.copy(slide01, staging / "cover.jpg")
        build_preview(slide01, staging / "preview.jpg")
