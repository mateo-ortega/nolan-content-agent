---
name: nolan-produce-carrusel
description: Adapter que toma un brief de nolan-decide-format y produce un carrusel PNG 1080x1350 invocando la skill sapiens-carrusel (Playwright+HTML+Jinja2). Genera content.yaml, llama render.py, escribe caption con Claude Sonnet 4.6 (cached), y deja todo en staging/<piece_id>/.
version: 0.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [production, carrusel, sapiens, nolan]
    category: sapiens
    requires_toolsets: [terminal, llm]
---

# nolan-produce-carrusel

Wrapper sobre `sapiens-carrusel` (skill legacy ya operativa). Genera carrusel completo desde un brief: content.yaml + PNGs + caption.md + metadata.json.

## When to use

Brief recibido de `nolan-decide-format` con `format: carrusel`.

## EJECUCIÓN — LEER ANTES DEL PROCEDURE

**Nolan NO ejecuta este procedimiento con su propio modelo.**

Todo el pipeline (generación de YAML, validación, ethics, render, caption) está implementado en `skills/nolan-produce-carrusel/scripts/produce_carrusel.py`. Ese script usa `nolan-llm-router` internamente para enrutar cada tarea al modelo correcto (DeepSeek para clasificación, Claude Sonnet solo para copy final). Ejecutarlo siempre en terminal:

```bash
python3.12 /srv/sapiens-nolan/skills/nolan-produce-carrusel/scripts/produce_carrusel.py \
    --brief <ruta_al_brief>
```

**No repliques la lógica en tu turno conversacional.** Si lo hacés, todo pasa por Sonnet y el costo se multiplica ×10.

## Procedure (referencia interna — lo ejecuta el script)

1. **Cargar brief** + `memory/brand_context.md` + `SOUL.md` (system prompt).
2. **Generar content.yaml** vía LLM task `copy.carrusel_yaml` (Claude Sonnet 4.6, cached):
   - Sistema: `prompts/system/copywriter.md` + `prompts/formats/carrusel.md`
   - Usuario: brief + shortlist de fuentes
   - Output: YAML con estructura de `sapiens-carrusel/SKILL.md` §6 (comillas simples ASCII estrictas)
   - Regla "una idea por slide" obligatoria: cada slide interior expresa una sola idea en el texto del gesto. `body`/`subline` opcionales, máx 80 chars, complementan sin repetir.
   - Solo 3 gestos vigentes: `tachadura`, `escala`, `repeticion`.
3. **Validar YAML** con `pyyaml.safe_load` antes de persistir. Si falla, reintentar una vez con error de parsing como contexto.
4. **Chequeo ethics** (pre-render): regex sobre texto de slides + caption candidata. Si rojo → halt + notify; si amarillo → reformular una vez.
5. **Persistir** `staging/<piece_id>/content.yaml`.
6. **Invocar sapiens-carrusel**:
   ```bash
   py -3.12 /srv/sapiens-nolan/skills/sapiens-carrusel/assets/render.py \
       "staging/<piece_id>/content.yaml" \
       "staging/<piece_id>/"
   ```
   Output esperado: `slide-01.png` ... `slide-NN.png` (1080×1350).
7. **Generar caption** vía `copy.final_caption` (Claude Sonnet, cached).
8. **Generar alt_text** vía `copy.alt_text` (DeepSeek, uno por slide).
9. **Generar hashtags.txt** (opcional, solo si cadence.yaml lo habilita).
10. **Generar cover.jpg** (copia de slide-01.png) y `preview.jpg` (480px redim).
11. **Escribir metadata.json** completo.
12. **Actualizar history.json** de sapiens-carrusel (rotación cromática).

## Brand lock

- Fuentes: Outfit, Instrument Sans, Geist Mono, Jura — deben estar en sistema (`fc-list`).
- Wordmark "sapiens" **siempre minúsculas** en slides.
- Gold `#E8A838` solo en palabras hero + word destacadas (1 por slide).
- Modo `dark` solo si brief lo pide explícito + L2 + tema técnico.
- Nunca coral, nunca amber (son Shift).

## Pitfalls

- **YAML con comillas curvas**: Claude Sonnet ocasionalmente genera `"` en vez de `'`. Validator debe rechazar y reintentar con prompt corrector.
- **Render Playwright falla por fuentes**: si `fc-list | grep Outfit` devuelve vacío, abort + log ERROR + notify (no intentar render con fallback — rompe identidad).
- **Slides con `body` o `subline` > 80 char**: violación de regla "una idea por slide". El validador rechaza y reintenta. Si el LLM insiste, partir el contenido en 2 slides.
- **Rotación cromática no actualizada**: revisar que `history.json` esté versionado en el deploy y que el contenedor tenga permisos de write.

## Verification

```bash
hermes chat "produce_carrusel --brief staging/fixtures/brief-icfes-lectura-critica.yaml --dry-run"
# Esperado: staging/2026-04-22-icfes-lectura-critica-metodo/ con 7 PNGs + caption.md + metadata.json
# Costo LLM < $0.15 (con cache warm).

ls staging/2026-04-22-icfes-lectura-critica-metodo/slide-*.png | wc -l  # 7
file staging/.../slide-01.png | grep "1080 x 1350"
```

## Outputs

```
staging/<piece_id>/
├── content.yaml
├── metadata.json
├── caption.md
├── hashtags.txt          (opcional)
├── alt_text.md
├── sources.md
├── slide-01.png ... slide-NN.png
├── cover.jpg
└── preview.jpg
```
