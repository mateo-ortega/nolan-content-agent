"""
nolan-produce-carrusel — genera carrusel completo desde un brief YAML.

Uso:
    python produce_carrusel.py --brief staging/fixtures/brief-icfes-lectura-critica.yaml
    python produce_carrusel.py --brief staging/fixtures/brief-icfes-lectura-critica.yaml --dry-run

Salida: staging/<piece_id>/ con content.yaml, slides PNG, caption.md,
        alt_text.md, sources.md, cover.jpg, preview.jpg, metadata.json.
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

import yaml

# Añadir project root al sys.path para importar sapiens.*
PROJECT_ROOT = Path(os.environ.get(
    "NOLAN_PROJECT_ROOT",
    Path(__file__).parent.parent.parent.parent
))
sys.path.insert(0, str(PROJECT_ROOT))

from sapiens.nolan_llm_router import LLMRouter, load_router    # noqa: E402
from sapiens.ethics_gate import EthicsGate, load_gate          # noqa: E402

RENDER_PY = PROJECT_ROOT / "skills" / "sapiens-carrusel" / "assets" / "render.py"
SOUL_PATH = PROJECT_ROOT / "SOUL.md"
BRAND_PATH = PROJECT_ROOT / "memory" / "brand_context.md"


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Produce carrusel Sapiens desde brief YAML")
    ap.add_argument("--brief", required=True, help="Ruta al brief YAML (relativa a PROJECT_ROOT)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Omite llamadas LLM y render; crea artefactos placeholder")
    ap.add_argument("--piece-id", help="Sobrescribe piece_id del brief")
    args = ap.parse_args()

    # Resolver ruta del brief
    brief_path = Path(args.brief)
    if not brief_path.is_absolute():
        brief_path = PROJECT_ROOT / args.brief

    with open(brief_path, encoding="utf-8") as f:
        brief: dict = yaml.safe_load(f)

    piece_id: str = args.piece_id or brief["piece_id"]
    staging: Path = PROJECT_ROOT / "staging" / piece_id
    staging.mkdir(parents=True, exist_ok=True)

    print(f"[produce-carrusel] piece_id={piece_id}  dry_run={args.dry_run}")

    router: LLMRouter | None = None if args.dry_run else load_router()
    gate: EthicsGate = load_gate()
    llm_cost_total = 0.0

    # ── 1. Generar y validar content.yaml (con 1 reintento si falla validación)
    content_yaml_path = staging / "content.yaml"
    if args.dry_run:
        fixture = PROJECT_ROOT / "staging" / "fixtures" / "content_min.yaml"
        shutil.copy(fixture, content_yaml_path)
        print("[produce-carrusel] dry-run: copiado content_min.yaml como content.yaml")
        with open(content_yaml_path, encoding="utf-8") as f:
            content: dict = yaml.safe_load(f)
        _validate_content_yaml(content, content_yaml_path)
    else:
        hint = ""
        content = {}
        for attempt in range(2):
            raw, cost = _generate_content_yaml(router, brief, piece_id, hint=hint)
            content_yaml_path.write_text(raw, encoding="utf-8")
            llm_cost_total += cost
            print(f"[produce-carrusel] content.yaml generado (intento {attempt + 1}, costo=${cost:.4f})")
            try:
                with open(content_yaml_path, encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                _validate_content_yaml(content, content_yaml_path)
                break
            except (ValueError, yaml.YAMLError) as exc:
                if attempt == 0:
                    hint = f"\n\nERROR DE VALIDACIÓN — corrige antes de reenviar:\n{exc}"
                    print(
                        f"[produce-carrusel] WARN intento 1 inválido: {exc} — reintentando…",
                        file=sys.stderr,
                    )
                else:
                    raise
    print("[produce-carrusel] content.yaml válido")

    # ── 3. Ethics pre-render ─────────────────────────────────────────────────
    slide_texts = _collect_slide_texts(content)
    ethics = gate.check(slide_texts)
    if ethics.status == "red":
        _abort_ethics(piece_id, ethics)
    elif ethics.status == "yellow":
        print(f"[ETHICS YELLOW] regla={ethics.rule_id}: {ethics.description}", file=sys.stderr)

    # ── 4. Render PNG ────────────────────────────────────────────────────────
    if args.dry_run:
        _create_placeholder_slides(content, staging)
    else:
        _run_render(content_yaml_path, staging)

    # ── 5. Caption ──────────────────────────────────────────────────────────
    if args.dry_run:
        caption = _caption_dry_run(brief)
    else:
        caption, cost = _generate_caption(router, brief, content, piece_id)
        llm_cost_total += cost
    (staging / "caption.md").write_text(caption, encoding="utf-8")

    # Ethics sobre caption
    cap_ethics = gate.check([caption])
    if cap_ethics.status == "red":
        _abort_ethics(piece_id, cap_ethics)

    # ── 6. Alt text ──────────────────────────────────────────────────────────
    (staging / "alt_text.md").write_text(_build_alt_text(content), encoding="utf-8")

    # ── 7. Sources.md ────────────────────────────────────────────────────────
    (staging / "sources.md").write_text(_build_sources_md(brief), encoding="utf-8")

    # ── 8. Preview + cover ───────────────────────────────────────────────────
    slide01 = staging / "slide-01.png"
    if slide01.exists():
        shutil.copy(slide01, staging / "cover.jpg")
        _build_preview(slide01, staging / "preview.jpg")

    # ── 9. Metadata.json ─────────────────────────────────────────────────────
    meta = _build_metadata(brief, piece_id, llm_cost_total, ethics.status)
    (staging / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"[produce-carrusel] OK → {staging}  (costo_total=${llm_cost_total:.4f})")
    print(json.dumps({"piece_id": piece_id, "staging": str(staging), "status": "ok"}))


# ---------------------------------------------------------------------------
# Generación de content.yaml vía LLM
# ---------------------------------------------------------------------------

_CARRUSEL_SYSTEM_TEMPLATE = """{soul}

---

{brand}

---

Eres el copywriter de sapiens. Tu única tarea ahora es generar el YAML de contenido \
para un carrusel de Instagram usando el schema completo nativo del renderer.

REGLAS CRÍTICAS — cualquier violación invalida el YAML:
1. Comillas SIMPLES rectas (' ') obligatorias. NUNCA uses comillas curvas. Esta regla es solo de estilo; el contenido DEBE tener tildes, ñ y ortografía española perfecta sin usar comillas.
2. Ortografía española perfecta OBLIGATORIA: tildes en todo (á, é, í, ó, ú, ñ). 
3. Sin emojis en ningún campo.
4. Usa `<br>` explícitamente en el texto para los saltos de línea estratégicos. No dejes líneas muy largas.
5. El wordmark "sapiens" SIEMPRE se escribe en minúsculas en tus textos renderizados.
6. Tipos de slide (orden): 1 portada → N interiores (4-7) → 1 cta.
7. Modos cromáticos (`mode`): 'light', 'teal', 'deep'. La 'portada' y el 'cta' deben usar 'teal' o 'deep'. Los 'interior' usan 'light', aunque puedes alternar 1-2 en 'teal' o 'deep'. Nunca 3 modos iguales consecutivos.
8. Gestos permitidos para `interior`: tachadura, escala, repeticion, inversion, fragmentacion. NO USES el gesto bloque.
9. El campo `eyebrow` (la ETIQUETA numerada superior) para portada y cta va en la raíz de su objeto, pero para interiores debe ir siempre DENTRO del objeto `g`.
10. Devuelve SOLO el YAML, sin bloques markdown ni explicaciones.
11. **LÍMITES DE CARACTERES POR GESTO** — el render fallará si excedes estos topes. Los caracteres incluyen espacios pero NO los tags `<br>`:
    - `escala` (tipografía 210px): `accent` = UNA sola palabra-concepto (el héroe visual del slide). `pre` y `post` son conectores gramaticales mínimos — NO frases completas. NINGUNA palabra individual en `pre` o `post` puede superar 7 chars. `accent` máx 10 chars. Total `pre`+`accent`+`post` ≤ 50 chars (sin `<br>`). Correcto: pre='aprende a<br>', accent='leer', post='<br>más rápido.' · Incorrecto: pre='la habilidad de colaborar en equipo'.
    - `fragmentacion` (tipografía 180-220px): cada `text` máx 8 chars · `left` ≤ '55%' · `top` ≤ '65%' · `size` ≤ '200px'.
    - `tachadura` (tipografía 84px): `pre`+`strike`+`mid`+`emphasis`+`post` totales ≤ 80 chars.
    - `inversion` (tipografía 84px): `pre`+`flipped`+`post` totales ≤ 60 chars · `flipped` máx 8 chars (rota 180°).
    - `repeticion` (tipografía 120px): cada `word` máx 14 chars · máx 3 palabras (la 4ta queda fuera de canvas).
    - `portada.hero`: `hero_pre`+`hero_accent`+`hero_post` totales ≤ 60 chars · cada palabra máx 14 chars · usa `<br>` cada 2-3 palabras.
    - `cta.hero`: máx 12 chars (idealmente solo "sapiens").
    - `body` (cualquier slide): máx 140 chars con `<br>` cada ~50.
    Si un concepto requiere más caracteres → reformula más corto, parte con `<br>`, o cambia de gesto.
12. **PROHIBIDO palabras largas en gestos de tipografía grande.** En `escala` y `fragmentacion` (210px), palabras de más de 7 chars casi no caben en una línea. Usa sinónimos cortos: "apps" en vez de "aplicaciones", "método" en vez de "metodología", "saber" en vez de "conocimiento". En `escala`, el campo `accent` es SIEMPRE una sola palabra: es el concepto central del slide, no una frase. Si el tema requiere una frase completa → cambia el gesto a `tachadura` o `inversion`.
13. **Conexión con Sapiens cuando sea natural.** Si el tema permite tocar el método (diagnóstico, ruta personalizada, tutor humano, ciencia del aprendizaje aplicada), aprovecha UN slide interior para hacerlo de forma orgánica. No es obligatorio en cada carrusel — pero nunca lo fuerces. El vocabulario sapiens (diagnosticar, ruta, método, evidencia, claridad, proceso, diseñado) debe estar presente de forma continua en todo el copy — esa es la conexión implícita mínima. NUNCA posicionar la IA como 'par que razona', 'colega', 'agente que decide' o entidad con agencia. La IA es herramienta del método, no protagonista. El sujeto activo de cada frase debe ser el humano (el estudiante, el tutor, el método) — nunca el modelo.

SCHEMA DEL RENDERER (cópialo exactamente en su estructura y llaves):

nombre: '{{piece_id}}'
titulo: 'Título descriptivo del carrusel'
tono: 'l1'
slides:
  # --- PORTADA (obligatoria) ---
  - tipo: portada
    mode: teal
    logo_path: 'assets/sapiens_logo_white.png'
    eyebrow: '00 · CONTEXTO GENERAL'
    hero_size: '160px'
    hero_pre: 'texto antes<br>del '
    hero_accent: 'accent'
    hero_post: '. continuo.'
    subline: 'subtítulo de contexto con o sin <br>'

  # --- INTERIOR — tachadura (contraste error→verdad) ---
  - tipo: interior
    mode: light
    gesto: tachadura
    label_indice: 'paso 1'
    g:
      eyebrow: '01 · EYEBROW LABEL'
      pre: 'la mayoría '
      strike: 'memoriza'
      mid: '.<br>los que aprueban '
      emphasis: 'entienden'
      post: '.'
      body: 'Frase corta de apoyo con <br> explicando contraste.'

  # --- INTERIOR — escala (concepto destacado hero) ---
  - tipo: interior
    mode: light
    gesto: escala
    label_indice: 'paso 2'
    g:
      eyebrow: '02 · EYEBROW LABEL'
      pre: 'el secreto<br>'
      accent: 'entender'
      post: '<br>el patrón.'
      subline: 'Frase breve de apoyo.'

  # --- INTERIOR — repeticion (refuerzo iterativo) ---
  - tipo: interior
    mode: deep
    gesto: repeticion
    label_indice: 'paso 3'
    g:
      eyebrow: '03 · EYEBROW LABEL'
      words:
        - 'coherencia.'
        - 'coherencia.'
        - 'coherencia.'
      body: 'Explicación del término iterado.'

  # --- INTERIOR — inversion (giro semántico / concepto al revés) ---
  - tipo: interior
    mode: light
    gesto: inversion
    label_indice: 'giro'
    g:
      eyebrow: '04 · EYEBROW LABEL'
      pre: 'tú crees que es '
      flipped: 'así'
      post: '<br>pero es al revés.'
      body: 'Explicación breve.'

  # --- INTERIOR — fragmentacion (concepto difuso disperso) ---
  - tipo: interior
    mode: light
    gesto: fragmentacion
    label_indice: 'caos'
    g:
      eyebrow: '05 · EYEBROW LABEL'
      frags:
        - text: 'd'
          top: '20%'
          left: '15%'
          size: '180px'
        - text: 'e'
          top: '35%'
          left: '40%'
          size: '200px'
        - text: 's'
          top: '50%'
          left: '70%'
          size: '220px'
          color: 'var(--highlight)'
      body: 'Sólo vemos piezas sueltas.'

  # --- CTA (obligatorio) ---
  - tipo: cta
    mode: teal
    logo_path: 'assets/sapiens_logo_white.png'
    eyebrow: '06 · CIERRE'
    hero_size: '140px'
    hero: 'sapiens'
    body: 'Guarda esto y aplícalo esta semana.'
    tagline: 'tu ruta. diseñada con método.'
    bio_text: 'link en bio'
"""


def _generate_content_yaml(
    router: LLMRouter, brief: dict, piece_id: str, hint: str = ""
) -> tuple[str, float]:
    soul = SOUL_PATH.read_text(encoding="utf-8")
    brand = BRAND_PATH.read_text(encoding="utf-8")
    system = _CARRUSEL_SYSTEM_TEMPLATE.format(soul=soul, brand=brand)
    brief_str = yaml.dump(brief, allow_unicode=True, default_flow_style=False)
    user = (
        f"piece_id (campo `nombre` del YAML): {piece_id}\n\n"
        f"Genera el content.yaml para esta pieza:\n\n{brief_str}"
        + hint
    )

    resp = router.call(
        task="copy.carrusel_yaml",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        cache_system=True,
        piece_id=piece_id,
    )

    raw = resp.text.strip()
    # Limpiar posibles markdown fences
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:] if lines[-1] != "```" else lines[1:-1])

    return raw, resp.cost_usd


def _collect_slide_texts(content: dict) -> list[str]:
    """Extrae todos los strings de texto del YAML nativo del renderer."""
    texts: list[str] = []
    for s in content.get("slides", []):
        tipo = s.get("tipo", "")
        if tipo == "portada":
            for field in ("hero_pre", "hero_accent", "hero_post", "subline", "eyebrow"):
                v = s.get(field, "")
                if v:
                    texts.append(v)
        elif tipo == "interior":
            g = s.get("g", {})
            for field in ("pre", "strike", "mid", "emphasis", "post", "body",
                          "accent", "subline", "flipped", "eyebrow"):
                v = g.get(field, "")
                if v:
                    texts.append(v)
            for w in g.get("words", []):
                texts.append(w)
            for frag in g.get("frags", []):
                if isinstance(frag, dict):
                    texts.append(frag.get("text", ""))
        elif tipo == "cta":
            for field in ("hero", "body", "tagline", "bio_text", "eyebrow"):
                v = s.get(field, "")
                if v:
                    texts.append(v)
    return texts


def _validate_content_yaml(content: dict, path: Path):
    if not content.get("nombre"):
        raise ValueError(f"content.yaml sin campo 'nombre' (piece_id): {path}")
    slides = content.get("slides", [])
    if not slides:
        raise ValueError(f"content.yaml sin slides: {path}")
    tipos = [s.get("tipo") for s in slides]
    if tipos[0] != "portada":
        raise ValueError("El primer slide debe ser tipo: portada")
    if tipos[-1] != "cta":
        raise ValueError("El último slide debe ser tipo: cta")
    _VALID_GESTOS = {"tachadura", "escala", "repeticion", "inversion", "fragmentacion"}
    for s in slides:
        tipo = s.get("tipo")
        mode = s.get("mode")
        if not mode or mode not in ("light", "teal", "deep", "dark"):
            raise ValueError(f"Slide tipo={tipo} tiene mode inválido o está ausente: '{mode}'")

        if tipo == "interior":
            gesto = s.get("gesto")
            if gesto not in _VALID_GESTOS:
                raise ValueError(f"Slide interior con gesto inválido: '{gesto}'. Permitidos: {_VALID_GESTOS}")
            if not s.get("g"):
                raise ValueError(f"Slide interior sin campo 'g': {s}")
        # Detectar comillas curvas en cualquier string
        for v in _collect_slide_texts({"slides": [s]}):
            if any(c in v for c in '\u201c\u201d\u2018\u2019'):
                raise ValueError(f"Slide tipo={tipo}: comillas curvas detectadas — reintentar")

    # ── Validación de límites por gesto ─────────────────────────────────────
    def _strip_br(t: str) -> str:
        return re.sub(r'<br\s*/?>', ' ', t)

    def _words(t: str) -> list:
        return [re.sub(r'[^\w]', '', w) for w in _strip_br(t).split() if w]

    for s in slides:
        if s.get("tipo") != "interior":
            continue
        g = s.get("g") or {}
        gesto = s.get("gesto", "")

        if gesto == "escala":
            accent = _strip_br(g.get("accent", ""))
            if len(accent) > 10:
                raise ValueError(
                    f"escala·accent: '{accent}' tiene {len(accent)} chars (máx 10). "
                    f"Usa una palabra más corta o un sinónimo."
                )
            if len(accent.split()) > 2:
                raise ValueError(
                    f"escala·accent: '{accent}' tiene {len(accent.split())} palabras. "
                    f"accent debe ser UNA sola palabra-concepto (el héroe visual)."
                )
            for field in ("pre", "post"):
                for word in _words(g.get(field, "")):
                    if len(word) > 7:
                        raise ValueError(
                            f"escala·{field}: la palabra '{word}' tiene {len(word)} chars (máx 7). "
                            f"Usa sinónimo más corto o reformula."
                        )
            total = len(_strip_br(
                g.get("pre", "") + g.get("accent", "") + g.get("post", "")
            ))
            if total > 50:
                raise ValueError(f"escala: total {total} chars > 50 (máx 50)")

        elif gesto == "tachadura":
            total = len(_strip_br(
                "".join(g.get(f, "") for f in ("pre", "strike", "mid", "emphasis", "post"))
            ))
            if total > 80:
                raise ValueError(f"tachadura: total {total} chars > 80 (máx 80)")

        elif gesto == "inversion":
            flipped = _strip_br(g.get("flipped", ""))
            if len(flipped) > 8:
                raise ValueError(f"inversion·flipped: '{flipped}' tiene {len(flipped)} chars (máx 8)")
            total = len(_strip_br(
                g.get("pre", "") + g.get("flipped", "") + g.get("post", "")
            ))
            if total > 60:
                raise ValueError(f"inversion: total {total} chars > 60 (máx 60)")

        elif gesto == "repeticion":
            words = g.get("words") or []
            if not words:
                raise ValueError("repeticion: falta el campo 'words' (lista de palabras grandes)")
            if len(words) > 3:
                raise ValueError(f"repeticion: {len(words)} palabras > 3 (la 4ta queda fuera del canvas)")
            for w in words:
                wc = _strip_br(str(w)).strip()
                if len(wc) > 14:
                    raise ValueError(f"repeticion: '{wc}' tiene {len(wc)} chars (máx 14 por word)")


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _run_render(content_yaml_path: Path, _staging: Path):
    if not RENDER_PY.exists():
        raise FileNotFoundError(
            f"render.py no encontrado: {RENDER_PY}\n"
            "Asegurate de que skills/sapiens-carrusel/assets/render.py exista en el VPS."
        )
    python = os.environ.get("NOLAN_PYTHON", "python3.12")
    # output_base es staging/ (el renderer crea staging/{nombre}/ usando el campo `nombre` del YAML)
    cmd = [python, str(RENDER_PY), str(content_yaml_path), str(PROJECT_ROOT / "staging") + "/"]
    print(f"[produce-carrusel] render: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"render.py terminó con código {result.returncode}")


def _create_placeholder_slides(content: dict, staging: Path):
    try:
        from PIL import Image
        slides = content.get("slides", [])
        for idx, _ in enumerate(slides, start=1):
            img = Image.new("RGB", (1080, 1350), color=(250, 250, 247))
            img.save(staging / f"slide-{idx:02d}.png")
        print(f"[produce-carrusel] dry-run: {len(slides)} slides placeholder creados")
    except ImportError:
        print("[produce-carrusel] WARN: Pillow no instalado, sin placeholder slides", file=sys.stderr)


# ---------------------------------------------------------------------------
# Caption y textos auxiliares
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


def _generate_caption(
    router: LLMRouter, brief: dict, content: dict, piece_id: str
) -> tuple[str, float]:
    soul = SOUL_PATH.read_text(encoding="utf-8")
    brand = BRAND_PATH.read_text(encoding="utf-8")
    system = f"{soul}\n\n---\n\n{brand}"
    slides_txt = "\n".join(
        f"Slide {i}: {' '.join(_collect_slide_texts({'slides': [s]}))}"
        for i, s in enumerate(content.get("slides", []), start=1)
    )
    user = _CAPTION_USER_TEMPLATE.format(
        niche=brief.get("niche", ""),
        hook=brief.get("hook", ""),
        thesis=brief.get("thesis", ""),
        slides=slides_txt,
    )
    resp = router.call(
        task="copy.final_caption",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        cache_system=True,
        piece_id=piece_id,
    )
    return resp.text.strip(), resp.cost_usd


def _caption_dry_run(brief: dict) -> str:
    return (
        f"{brief.get('hook', 'Lectura crítica ICFES.')}\n\n"
        f"{brief.get('thesis', '')}\n\n"
        "[Caption generado en dry-run — reemplazar en producción real]"
    )


def _build_alt_text(content: dict) -> str:
    lines = []
    for s in content.get("slides", []):
        lines.append(f"## Slide {s.get('id', '?')}\n{s.get('text', '')}\n")
    return "\n".join(lines)


def _build_sources_md(brief: dict) -> str:
    sources = brief.get("sources", [])
    if not sources:
        return "Sin fuentes específicas registradas en el brief."
    lines = ["# Fuentes\n"]
    for s in sources:
        lines.append(f"- {s.get('citation', s.get('url', ''))}")
    return "\n".join(lines)


def _build_preview(slide01: Path, preview_path: Path):
    try:
        from PIL import Image
        img = Image.open(slide01)
        img.thumbnail((480, 600))
        img.save(preview_path, "JPEG", quality=85)
    except (ImportError, Exception):
        shutil.copy(slide01, preview_path)


def _build_metadata(brief: dict, piece_id: str, llm_cost: float, ethics_status: str) -> dict:
    return {
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


# ---------------------------------------------------------------------------
# Abortar por ethics
# ---------------------------------------------------------------------------

def _abort_ethics(piece_id: str, result):
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


if __name__ == "__main__":
    main()
