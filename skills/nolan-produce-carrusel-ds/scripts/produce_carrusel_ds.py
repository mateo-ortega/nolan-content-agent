"""
nolan-produce-carrusel-ds — produce un carrusel completo usando el sistema
de diseño estructurado (sapiens-carrusel-ds).

Pipeline copy-and-edit literal:
  1. Carga 7 templates HTML canónicos.
  2. LLM (Sonnet cached) edita el texto manteniendo CSS/layout.
  3. Validador post-LLM chequea voz v2, ritmo cromático, índices.
  4. Reintento único si falla validación.
  5. Render: Playwright captura PNGs 1080x1350.
  6. Caption + assets + metadata via skills/_shared/produce_common.

Uso:
    python produce_carrusel_ds.py --brief <ruta>
    python produce_carrusel_ds.py --brief <ruta> --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import yaml

# Añadir project root para importar sapiens.* y skills._shared
PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent.parent.parent
))
sys.path.insert(0, str(PROJECT_ROOT))

from sapiens.nolan_llm_router import LLMRouter, load_router    # noqa: E402
from sapiens.ethics_gate import EthicsGate, load_gate          # noqa: E402
from skills._shared.produce_common import (                     # noqa: E402
    generate_caption, caption_dry_run,
    build_alt_text, build_sources_md, build_metadata,
    abort_ethics, write_json, copy_slide01_to_cover_and_preview,
)

DS_SKILL_DIR = PROJECT_ROOT / "skills" / "sapiens-carrusel-ds"
RENDER_PY    = DS_SKILL_DIR / "render.py"
SOUL_PATH    = PROJECT_ROOT / "SOUL.md"
BRAND_PATH   = PROJECT_ROOT / "memory" / "brand_context.md"

TEMPLATE_NAMES = [
    "Cover", "Thesis", "Comparative", "Process",
    "BigQuote", "Stat", "CTA",
]

V1_FORBIDDEN_PATTERNS = [
    r"compa[ñn]ero de viaje",
    r"aprende a tu medida",
    r"par que razona",
    r"\bel profe\b",
    r"tu propio ritmo",
    r"agente que (decide|piensa|razona)",
    r"colaborador",  # cuando se refiere a IA — captura amplia, validador puede ajustar
]

SLIDE_BREAK = "<!--SLIDE_BREAK-->"


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Produce carrusel-ds desde brief YAML")
    ap.add_argument("--brief", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="Omite LLM y render real; usa templates como están")
    ap.add_argument("--piece-id")
    args = ap.parse_args()

    brief_path = Path(args.brief)
    if not brief_path.is_absolute():
        brief_path = PROJECT_ROOT / args.brief

    with open(brief_path, encoding="utf-8") as f:
        brief: dict = yaml.safe_load(f)

    piece_id: str = args.piece_id or brief["piece_id"]
    staging: Path = PROJECT_ROOT / "staging" / piece_id
    (staging / "slides").mkdir(parents=True, exist_ok=True)

    print(f"[produce-carrusel-ds] piece_id={piece_id}  dry_run={args.dry_run}")

    # ── 1. Cargar templates ─────────────────────────────────────────────────
    templates: dict[str, str] = {}
    for name in TEMPLATE_NAMES:
        p = DS_SKILL_DIR / "slides" / f"{name}.html"
        if not p.exists():
            print(f"[produce-carrusel-ds] ERROR: template no existe: {p}", file=sys.stderr)
            sys.exit(1)
        templates[name] = p.read_text(encoding="utf-8")

    # ── 2. Copiar recursos compartidos al staging ──────────────────────────
    _copy_shared_assets(staging)

    # ── 3. Generar slides HTML (LLM o dry-run) ─────────────────────────────
    router: LLMRouter | None = None if args.dry_run else load_router()
    gate: EthicsGate = load_gate()
    llm_cost_total = 0.0

    if args.dry_run:
        # Copiar 6 templates por defecto (Cover, Thesis, Comparative, Process, Stat, CTA)
        # sin BigQuote (requiere caso real)
        default_order = ["Cover", "Thesis", "Comparative", "Process", "Stat", "CTA"]
        slide_htmls = [templates[name] for name in default_order]
        # Renumerar footer index a NN / NN del total
        slide_htmls = [_renumber_footer(h, i + 1, len(slide_htmls))
                       for i, h in enumerate(slide_htmls)]
        print(f"[produce-carrusel-ds] dry-run: {len(slide_htmls)} templates copiados sin editar")
    else:
        hint = ""
        slide_htmls: list[str] = []
        for attempt in range(2):
            raw, cost = _generate_slides(router, templates, brief, piece_id, hint=hint)
            llm_cost_total += cost
            print(f"[produce-carrusel-ds] LLM call (intento {attempt + 1}, costo=${cost:.4f})")
            try:
                slide_htmls = _parse_slides(raw)
                _validate_slides(slide_htmls)
                break
            except ValueError as exc:
                if attempt == 0:
                    hint = f"\n\nERROR DE VALIDACIÓN — corrige antes de reenviar:\n{exc}"
                    print(
                        f"[produce-carrusel-ds] WARN intento 1 inválido: {exc} — reintentando…",
                        file=sys.stderr,
                    )
                else:
                    raise

    print(f"[produce-carrusel-ds] {len(slide_htmls)} slides válidos")

    # ── 4. Escribir slide-NN.html ──────────────────────────────────────────
    for i, html in enumerate(slide_htmls, start=1):
        (staging / "slides" / f"slide-{i:02d}.html").write_text(html, encoding="utf-8")

    # ── 5. Ethics pre-render (sobre texto plano de cada slide) ─────────────
    slide_texts_per_slide = [_extract_text(h) for h in slide_htmls]
    flat_texts = [t for slide in slide_texts_per_slide for t in slide]
    ethics = gate.check(flat_texts)
    if ethics.status == "red":
        abort_ethics(piece_id, ethics)
    elif ethics.status == "yellow":
        print(f"[ETHICS YELLOW] regla={ethics.rule_id}: {ethics.description}", file=sys.stderr)

    # ── 6. Render PNG ──────────────────────────────────────────────────────
    if args.dry_run:
        _create_placeholder_pngs(staging, len(slide_htmls))
    else:
        _run_render(staging)

    # ── 7. Caption ─────────────────────────────────────────────────────────
    if args.dry_run:
        caption = caption_dry_run(brief)
    else:
        soul = SOUL_PATH.read_text(encoding="utf-8")
        brand = BRAND_PATH.read_text(encoding="utf-8")
        caption, cost = generate_caption(
            router, soul, brand, brief, slide_texts_per_slide, piece_id
        )
        llm_cost_total += cost
    (staging / "caption.md").write_text(caption, encoding="utf-8")

    cap_ethics = gate.check([caption])
    if cap_ethics.status == "red":
        abort_ethics(piece_id, cap_ethics)

    # ── 8. Alt text + sources + cover + preview + metadata ─────────────────
    alt_descriptions = [" ".join(t)[:300] for t in slide_texts_per_slide]
    (staging / "alt_text.md").write_text(build_alt_text(alt_descriptions), encoding="utf-8")
    (staging / "sources.md").write_text(build_sources_md(brief), encoding="utf-8")
    copy_slide01_to_cover_and_preview(staging)

    meta = build_metadata(
        brief, piece_id, llm_cost_total, ethics.status,
        extra_fields={"visual_skill": "sapiens-carrusel-ds"},
    )
    write_json(staging / "metadata.json", meta)

    print(f"[produce-carrusel-ds] OK → {staging}  (costo_total=${llm_cost_total:.4f})")
    import json
    print(json.dumps({"piece_id": piece_id, "staging": str(staging), "status": "ok"}))


# ---------------------------------------------------------------------------
# Generación de slides — LLM call
# ---------------------------------------------------------------------------

_SYSTEM_TEMPLATE = """{soul}

---

{brand}

---

Eres el copywriter de sapiens. Tu tarea: editar 5 a 9 templates HTML de carrusel \
manteniendo INTACTAS las clases CSS, los estilos inline y la estructura. \
SOLO cambias el TEXTO entre etiquetas.

REGLAS CRÍTICAS — cualquier violación invalida la salida:

1. **Voz v2 estricta del SOUL.** Los templates traen copy v1 ("aprende a tu medida", "compañero", etc.) — IGNÓRALO. Reescribe todo el copy con autoridad técnica + calidez. Tagline obligado en CTA: 'tu ruta. diseñada con método.'
2. **Vocabulario sapiens v2:** diagnosticar, ruta, método, evidencia, datos, progreso, entender, claridad, práctica, caso, proceso, personalizado, resultado, prerequisito.
3. **Prohibido en cualquier slide:** 'compañero de viaje', 'aprende a tu medida', 'par que razona', 'el profe', 'tu propio ritmo', 'agente que decide/piensa/razona'.
4. **IA nunca es protagonista.** Sujeto activo de cada frase = humano (estudiante, tutor, padre, método). Nunca el modelo.
5. **Sentence case** en títulos y body. Proper nouns retienen casing (ICFES, UNAL, UdeA, Montessori).
6. **Sin emojis** en ningún slide.
7. **Audiencia segments NUNCA en surfaces:** cero 'L1', 'L2', 'Para padres', 'adultos_ia'.
8. **NO toques** las clases CSS, los `<style>`, los estilos inline `style="..."`, las imágenes (`<img src=...>`), ni `<link rel="stylesheet">`. SOLO cambias texto entre etiquetas.
9. **Footer index `NN / NN`:** actualiza ambos números para reflejar la posición real y el total. Ejemplo: si haces 6 slides y este es el 3°, debe decir `03 / 06`.
10. **Eyebrows/tags** (texto Jura uppercase): traduce al contenido de cada slide. Ejemplos válidos: 'La tesis · 02 / 06', 'Comparativa · 03 / 06', 'El método · 04 / 06', 'El dato · 05 / 06', 'Empieza · 06 / 06'. Para BigQuote (si lo usas): 'Caso real · NN / NN'.
11. **UNA SOLA IDEA POR SLIDE.** Cada slide desarrolla UN solo concepto, expresado en el TEXTO PRINCIPAL del template. NO uses estructura tipo título + subtítulo + cuerpo largo. Excepciones explícitas y únicas:
    - **Comparative:** contrasta dos polos del MISMO concepto (no son dos ideas, es UN contraste). Estructura nueva: `.side.old` con `.label` + `.frase` (UNA frase máx 8 palabras), y `.side.new` con `.label` + `.frase` (UNA frase máx 8 palabras). NO uses `<div class="li">` ni bullets — el template viejo con `.col.old/.col.new/.li/.big` fue ELIMINADO.
    - **Process:** UNA secuencia de pasos donde cada `.step` tiene UN solo `<div class="step-text">…</div>` (frase única máx 12 palabras). NO uses `class="h"` ni `class="p"` dentro de `.step` — la separación título-paso/descripción fue ELIMINADA.
    - **Thesis:** ya NO tiene `.kicker`. Solo `.thesis` (texto principal único) + `.body` opcional.
12. **Body opcional, máx 80 caracteres (sin `<br>`).** El campo `<div class="body">` es OPCIONAL: úsalo SOLO cuando aporte un matiz que NO cabe en el texto principal. NUNCA repitas la idea principal en el body. Si dudas, omítelo (déjalo como `<div class="body"></div>` vacío o quita la línea entera). Si necesitas más de 80 chars para explicar algo, ESO ES OTRO SLIDE.

ORDEN NARRATIVO POR DEFECTO (6 slides — sin BigQuote):
  Cover → Thesis → Comparative → Process → Stat → CTA

PALETA POR TEMPLATE (NO cambies estos backgrounds CSS):
  Cover      = teal   (#2B9E8F)
  Thesis     = warm   (#FAFAF7)
  Comparative= warm   (#FAFAF7)
  Process    = cream  (#F5F0EB)
  BigQuote   = cream  (#F5F0EB)
  Stat       = teal-deep (#1E7A6D)
  CTA        = dark   (#1A1C23)

REGLA CROMÁTICA ESTRICTA: máx 2 slides consecutivos del mismo color de fondo.
Thesis y Comparative son ambos 'warm' — el orden Cover→Thesis→Comparative→Process
ya satisface la regla (teal, warm, warm, cream). NO repitas Thesis o Comparative
juntas si ya hay otro warm en el orden; intercala Process (cream) o Stat (teal-deep).

CUÁNDO INCLUIR BigQuote (slide 5°, antes de Stat):
  Solo si el brief incluye un caso real verificable con nombre y contexto. \
Si no hay caso → omitir BigQuote (mes 1-3 estamos sin clientes reales).

CUÁNDO OMITIR un slide del orden por defecto:
  - Comparative: si el tema no admite contraste viejo/nuevo natural.
  - Stat: si no hay fuente verificable. Sin fuente = no Stat.
  - Cualquier otro: solo si rompe el ritmo narrativo.

TEMPLATES DISPONIBLES (los 7 — copia + edita el texto):

{templates_block}

FORMATO DE SALIDA (estricto):
- Devuelve los HTMLs editados, en orden, cada uno COMPLETO desde `<!DOCTYPE html>` hasta `</html>`.
- Separa cada HTML del siguiente con la línea exacta: `{slide_break}`
- NO incluyas markdown fences (```html), explicaciones, ni texto fuera de los HTMLs.
- NO incluyas BigQuote si no hay caso real.
"""


def _generate_slides(
    router: LLMRouter,
    templates: dict[str, str],
    brief: dict,
    piece_id: str,
    hint: str = "",
) -> tuple[str, float]:
    soul  = SOUL_PATH.read_text(encoding="utf-8")
    brand = BRAND_PATH.read_text(encoding="utf-8")
    templates_block = "\n\n".join(
        f"=== {name}.html ===\n{html}" for name, html in templates.items()
    )
    system = _SYSTEM_TEMPLATE.format(
        soul=soul,
        brand=brand,
        templates_block=templates_block,
        slide_break=SLIDE_BREAK,
    )
    brief_str = yaml.dump(brief, allow_unicode=True, default_flow_style=False)
    user = (
        f"piece_id: {piece_id}\n\n"
        f"Brief para este carrusel:\n\n{brief_str}\n\n"
        "Genera el carrusel completo siguiendo las REGLAS y el FORMATO DE SALIDA."
        + hint
    )

    resp = router.call(
        task="copy.carrusel_ds_html",  # tarea dedicada con max_tokens=16000 para 6-7 HTMLs completos
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        cache_system=True,
        piece_id=piece_id,
    )

    raw = resp.text.strip()
    # Limpiar posibles markdown fences
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:] if lines[-1] != "```" else lines[1:-1])

    return raw, resp.cost_usd


# ---------------------------------------------------------------------------
# Parser y validador
# ---------------------------------------------------------------------------

def _parse_slides(raw: str) -> list[str]:
    """Divide la respuesta del LLM por SLIDE_BREAK y limpia cada bloque."""
    parts = raw.split(SLIDE_BREAK)
    slides = [p.strip() for p in parts if p.strip()]
    if not slides:
        raise ValueError(f"No se pudo dividir la salida por '{SLIDE_BREAK}' — output vacío o sin separadores")
    return slides


def _validate_slides(slides: list[str]) -> None:
    """Aplica todas las reglas duras. Acumula todos los errores antes de lanzar."""
    errors: list[str] = []
    n = len(slides)

    if n < 5 or n > 9:
        raise ValueError(f"Total de slides = {n} (debe estar entre 5 y 9)")

    # Cada HTML completo
    for i, html in enumerate(slides, start=1):
        if not re.search(r"<!DOCTYPE\s+html", html, re.IGNORECASE):
            errors.append(f"slide-{i:02d}: falta `<!DOCTYPE html>` al inicio")
        elif "<html" not in html or "</html>" not in html:
            errors.append(f"slide-{i:02d}: HTML incompleto (falta `<html>` o `</html>`)")
        if 'href="../colors_and_type.css"' not in html:
            errors.append(
                f"slide-{i:02d}: falta `<link rel='stylesheet' href='../colors_and_type.css'>` "
                "(no toques esa línea)"
            )

    # Footer index NN / NN
    # Slide 1 (Cover) no tiene .idx — usa .tag; slide N (CTA) tampoco.
    for i, html in enumerate(slides, start=1):
        if i == 1 or i == n:
            continue
        idx_matches = re.findall(r'<b>\s*(\d{2})\s*</b>\s*/\s*(\d{2})', html)
        if not idx_matches:
            errors.append(f"slide-{i:02d}: no se encontró footer index `<b>NN</b> / NN`")
            continue
        for cur, total in idx_matches:
            if int(cur) != i or int(total) != n:
                errors.append(
                    f"slide-{i:02d}: footer index = {cur} / {total}, "
                    f"debería ser {i:02d} / {n:02d}"
                )

    # Palabras prohibidas v1 (sobre texto plano)
    for i, html in enumerate(slides, start=1):
        text = " ".join(_extract_text(html)).lower()
        for pat in V1_FORBIDDEN_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                errors.append(
                    f"slide-{i:02d}: contiene patrón v1 prohibido `{pat}` — usa voz v2 del SOUL"
                )

    # Comillas curvas
    for i, html in enumerate(slides, start=1):
        text = " ".join(_extract_text(html))
        if any(c in text for c in '""'''):
            errors.append(f"slide-{i:02d}: comillas curvas detectadas — usa comillas rectas")

    # Ritmo cromático: máx 2 surfaces consecutivos iguales
    surfaces = [_detect_surface(h) for h in slides]
    for i in range(len(surfaces) - 2):
        if surfaces[i] and surfaces[i] == surfaces[i+1] == surfaces[i+2]:
            errors.append(
                f"Ritmo cromático roto: 3 slides consecutivos con surface '{surfaces[i]}' "
                f"(slides {i+1}, {i+2}, {i+3}). "
                f"Paleta: Cover=teal, Thesis=warm, Comparative=warm, Process=cream, "
                f"BigQuote=cream, Stat=teal-deep, CTA=dark. "
                f"Intercala cream/dark entre los dos slides warm."
            )

    # ── Body opcional ≤ 80 chars (regla "una idea por slide") ───────────────
    for i, html in enumerate(slides, start=1):
        for body_text in re.findall(r'class="body"[^>]*>([^<]+)</div>', html):
            body_clean = re.sub(r'<br\s*/?>', ' ', body_text).strip()
            if len(body_clean) > 80:
                errors.append(
                    f"slide-{i:02d}: .body tiene {len(body_clean)} chars > 80 máx. "
                    f"Si necesitas más, parte el contenido en otro slide o quita el body. "
                    f"Texto: '{body_clean[:50]}…'"
                )

    # ── Estructura simplificada de templates densos ─────────────────────────
    # Thesis: sin .kicker (eliminado en mayo 2026)
    # Comparative: sin .li, .col.old/.col.new, .big — usar .side.old/.side.new + .frase
    # Process: sin .h ni .p dentro de .step — usar .step-text
    for i, html in enumerate(slides, start=1):
        is_thesis = "sapiens · Thesis" in html
        is_comparative = "sapiens · Comparative" in html
        is_process = "sapiens · Process" in html

        if is_thesis and 'class="kicker"' in html:
            errors.append(
                f"slide-{i:02d} (Thesis): contiene `class=\"kicker\"` que fue ELIMINADO. "
                f"Usa solo `.thesis` (texto principal único) + `.body` opcional."
            )
        if is_comparative:
            if re.search(r'class="li"', html) or re.search(r'class="col old"', html) or re.search(r'class="col new"', html):
                errors.append(
                    f"slide-{i:02d} (Comparative): usa estructura vieja con `.li`/`.col.old/.new`. "
                    f"Estructura nueva: `.side.old` con `.label` + `.frase`, y `.side.new` igual. SIN bullets."
                )
            if 'class="frase"' not in html:
                errors.append(
                    f"slide-{i:02d} (Comparative): falta `class=\"frase\"`. Cada `.side` debe tener UNA `.frase` única."
                )
        if is_process and re.search(r'class="step-text"', html) is None:
            errors.append(
                f"slide-{i:02d} (Process): falta `class=\"step-text\"`. "
                f"Cada `.step` ahora tiene UN solo `<div class=\"step-text\">…</div>` (sin `.h` ni `.p`)."
            )

    if errors:
        raise ValueError("\n".join(errors))


def _detect_surface(html: str) -> str:
    """Detecta el background dominante del .slide por su CSS inline."""
    m = re.search(r'\.slide\s*\{[^}]*background:\s*(#[0-9A-Fa-f]{6})', html)
    if not m:
        return ""
    bg = m.group(1).upper()
    return {
        "#2B9E8F": "teal",
        "#1E7A6D": "teal-deep",
        "#FAFAF7": "warm",
        "#F5F0EB": "cream",
        "#1A1C23": "dark",
        "#FFFFFF": "white",
    }.get(bg, bg.lower())


# ---------------------------------------------------------------------------
# Extracción de texto plano (para ethics + caption + alt)
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Extrae texto plano ignorando <style>, <script>, <head>."""

    SKIP_TAGS = {"style", "script", "head", "title", "meta", "link"}

    def __init__(self):
        super().__init__()
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            txt = data.strip()
            if txt:
                self.parts.append(txt)


def _extract_text(html: str) -> list[str]:
    p = _TextExtractor()
    p.feed(html)
    return p.parts


# ---------------------------------------------------------------------------
# Footer index renumber (para dry-run)
# ---------------------------------------------------------------------------

def _renumber_footer(html: str, position: int, total: int) -> str:
    """Reemplaza patrones `<b>NN</b> / NN` y eyebrows tipo `· NN / NN` con valores correctos."""
    pos = f"{position:02d}"
    tot = f"{total:02d}"
    # <b>02</b> / 07
    html = re.sub(r'<b>\s*\d{2}\s*</b>\s*/\s*\d{2}', f'<b>{pos}</b> / {tot}', html)
    # · 02 / 07
    html = re.sub(r'·\s*\d{2}\s*/\s*\d{2}', f'· {pos} / {tot}', html)
    return html


# ---------------------------------------------------------------------------
# Copia de assets compartidos al staging
# ---------------------------------------------------------------------------

def _copy_shared_assets(staging: Path) -> None:
    """Copia colors_and_type.css, fonts/, assets/ del skill al staging."""
    # CSS
    css_src = DS_SKILL_DIR / "colors_and_type.css"
    if css_src.exists():
        shutil.copy(css_src, staging / "colors_and_type.css")
    # fonts/
    fonts_src = DS_SKILL_DIR / "fonts"
    if fonts_src.is_dir():
        dst = staging / "fonts"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(fonts_src, dst)
    # assets/
    assets_src = DS_SKILL_DIR / "assets"
    if assets_src.is_dir():
        dst = staging / "assets"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(assets_src, dst)


# ---------------------------------------------------------------------------
# Render: invoca render.py del skill sapiens-carrusel-ds
# ---------------------------------------------------------------------------

def _run_render(staging: Path) -> None:
    if not RENDER_PY.exists():
        raise FileNotFoundError(f"render.py no encontrado: {RENDER_PY}")
    python = os.environ.get("NOLAN_PYTHON", "python3.12")
    cmd = [python, str(RENDER_PY), str(staging)]
    print(f"[produce-carrusel-ds] render: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"render.py terminó con código {result.returncode}")


def _create_placeholder_pngs(staging: Path, n: int) -> None:
    try:
        from PIL import Image
        for i in range(1, n + 1):
            Image.new("RGB", (1080, 1350), color=(250, 250, 247)).save(
                staging / f"slide-{i:02d}.png"
            )
        print(f"[produce-carrusel-ds] dry-run: {n} placeholder PNGs creados")
    except ImportError:
        print("[produce-carrusel-ds] WARN: Pillow no instalado, sin placeholder PNGs",
              file=sys.stderr)


if __name__ == "__main__":
    main()
