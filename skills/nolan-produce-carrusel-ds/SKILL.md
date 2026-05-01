---
name: nolan-produce-carrusel-ds
version: 0.1.0
description: Wrapper que produce un carrusel completo usando el sistema de diseño estructurado (`sapiens-carrusel-ds`). Pipeline copy-and-edit literal — el LLM edita los 7 templates HTML canónicos, validador post-LLM chequea voz v2 y CSS, render.py captura PNGs 1080x1350. Alternativa al wrapper `nolan-produce-carrusel` (gestos tipográficos).
platforms: [linux]
metadata:
  hermes:
    tags: [production, carrusel, sapiens, design-system, nolan]
    category: sapiens
    requires_toolsets: [terminal, llm]
---

# nolan-produce-carrusel-ds

Wrapper sobre `sapiens-carrusel-ds` (skill visual). Genera carrusel completo: HTMLs editados + PNGs + caption.md + metadata.json.

## When to use

Brief recibido con `format: carrusel-ds` (jueves por defecto via `scripts/ciclo.sh`). También invocable manualmente desde Telegram con `ciclo --format carrusel-ds`.

## EJECUCIÓN

**Nolan NO ejecuta este procedimiento con su propio modelo.**

Todo el pipeline (carga templates, LLM call, validador, render, caption) está implementado en `skills/nolan-produce-carrusel-ds/scripts/produce_carrusel_ds.py`. Ese script usa `nolan-llm-router` internamente. Ejecutarlo siempre en terminal:

```bash
python3.12 /srv/sapiens-nolan/skills/nolan-produce-carrusel-ds/scripts/produce_carrusel_ds.py \
    --brief <ruta_al_brief>
```

## Procedure (referencia interna)

1. **Cargar brief** + `SOUL.md` + `memory/brand_context.md` + 7 templates HTML de `sapiens-carrusel-ds/slides/`.
2. **LLM call (Sonnet, cached system):** una sola llamada con SOUL + reglas voz v2 + 7 templates + brief. Output: HTMLs separados por `<!--SLIDE_BREAK-->`.
3. **Parser:** dividir respuesta, validar cada bloque como HTML.
4. **Validador post-LLM:**
   - 5-9 slides totales.
   - Cada HTML referencia `../colors_and_type.css`.
   - Footer index `01 / 07` consistente con total.
   - Background rhythm: máx 2 surfaces consecutivos iguales.
   - Texto plano pasa ethics gate y no incluye palabras prohibidas v2.
5. **Si falla** → reintento único con el error como hint al LLM.
6. **Persistir** en `staging/<piece_id>/slides/slide-NN.html` y copiar `colors_and_type.css`, `fonts/`, `assets/` al staging.
7. **Render:** `render.py` itera HTMLs y captura `slide-NN.png`.
8. **Caption + alt_text + sources.md + cover.jpg + preview.jpg + metadata.json**: usar funciones de `skills/_shared/produce_common.py`.

## Brand lock

- Fuentes: Outfit, Instrument Sans, Geist Mono, Jura — verificar con `fc-list | grep -i jura` antes del primer ciclo.
- Tagline: `tu ruta. diseñada con método.`
- Voz v2 estricta — `SOUL.md` es la fuente de verdad.
