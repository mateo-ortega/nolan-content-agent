---
name: nolan-produce-animacion
description: Genera MP4 Manim 1080×1920 para Reels educativos mediante templates parametrizados (BarChart, CurveReveal, StepReveal). El LLM elige el template y genera JSON de parámetros; animacion_templates.py renderiza con identidad Sapiens.
version: 0.3.0
platforms: [linux]
metadata:
  hermes:
    tags: [production, animacion, manim, sapiens, nolan]
    category: sapiens
    requires_toolsets: [terminal, llm]
---

# nolan-produce-animacion

Genera animaciones educativas verticales 1080×1920 60fps para Reels. El LLM **no escribe código Manim** — elige uno de tres templates y genera JSON de parámetros. `animacion_templates.py` convierte ese JSON en la animación con identidad Sapiens (teal/gold/dark, logo, outro).

## When to use

Brief con `format: animacion`. Reservado a 1–2 piezas/semana (martes y viernes según `ciclo.sh`).

## Templates disponibles

| Template | Usar cuando | Límites |
|---|---|---|
| **BarChart** | Comparación, ranking, datos porcentuales | Máx 7 barras, 1-2 highlight |
| **CurveReveal** | Tendencia, decaimiento, crecimiento exponencial | 1-2 curvas, tipos: decay/growth/custom |
| **StepReveal** | Método, framework, proceso numerado | Máx 5 pasos, ≤45 chars/paso |

## Procedure

1. **Cargar brief** + `memory/brand_context.md` + `SOUL.md`.
2. **LLM genera JSON de parámetros** (task `animacion.params`, DeepSeek en NIM):
   - Elige template más apropiado al thesis/archetype del brief.
   - Hook: ≤3 líneas, ≤7 palabras/línea. Línea 2 = acento de color (`hook_accent_color`).
   - Conclusión: 2 líneas. Línea 1 blanca, línea 2 teal (automático).
   - Caption IG (≤2200 chars), alt_text, fuentes.
3. **Persistir** `staging/<piece_id>/anim_params.json`.
4. **Render Manim**:
   ```bash
   $NOLAN_PYTHON produce_animacion.py --brief staging/<piece_id>/brief.yaml
   ```
   Internamente: `python3.12 -m manim animacion_render.py SapiensAnimScene -qh --resolution 1080,1920 --output_file animation.mp4`
5. **Safe zone check automático** (`animacion_check.py`): muestrea 9 frames del video con PIL/numpy y verifica que ningún píxel con contenido esté fuera de la safe zone IG. Si hay overflow, `produce_animacion.py` aborta con `status: safezone_fail` antes de packaging.
6. **Extraer cover.jpg** (ffmpeg, frame en t=1s).
7. **Escribir** caption.md, alt_text.md, sources.md, metadata.json, content.yaml.

## Brand lock

- Fondo: dark `#0B0D12` — excepción al light-mode del carrusel.
- Hook línea 2 = acento de color (`gold | teal | red | violet`).
- Conclusión línea 2 = teal automático, weight BOLD.
- Logo hero visible todo el video; outro estándar 3s al final (`@sapiens.ed`).
- **Safe zone IG**: texto ajustado mediante `_fit_text()` (font_size proporcional, sin `set_width()`), límite `_MAX_TEXT_W=6.5u` + `_clamp_x()` como red de seguridad final. `animacion_check.py` valida el video post-render con PIL/numpy — si detecta overflow aborta antes de subir al Drive. Aun así, respetar ≤7 palabras/línea para evitar escalado excesivo.
- **CTA obligatorio en caption** (v0.3.1, 2026-05-16): el caption debe cerrar (antes de los hashtags) con la línea exacta: `"Si quieres aplicar este método a tu hijo/a, agenda diagnóstico — link en bio."` El prompt del LLM ya lo exige con la fórmula exacta; si el output no la respeta, corregir manualmente. ~~Versión anterior: "escríbenos a @sapiens.ed" — eliminada por ser CTA débil sin oferta tangible.~~
- **Nicho Sapiens**: las animaciones son exclusivamente para padres, jóvenes preicfes o estudiantes. Briefs B2B, de APIs o de automatización empresarial son rechazados automáticamente por `produce_animacion.py` antes de invocar al LLM.

## Pitfalls

- **safezone_fail**: el check post-render detectó overflow. Revisar `anim_params.json` (textos muy largos, barras con value extremo). Corregir y re-lanzar `produce_animacion.py` con `--piece-id` explícito para no regenerar LLM. Si el template es correcto y aun así falla, revisar `animacion_templates.py` — puede haberse roto `_fit_text()` o `_clamp_x()`.
- **Render falla**: revisar `anim_params.json` — valores fuera de rango (e.g. `value > 100` en barras, `custom_points` con coordenadas fuera del eje). Corregir y re-lanzar sin regenerar LLM.
- **Hook saturado**: si una línea supera ~12 palabras, el clamp de ancho la escala hacia abajo y se verá pequeña. Reintentar LLM pidiendo líneas más cortas.
- **Render timeout / OOM**: render 1080p 60fps ≈ 4-6 GB RAM y 2-5 min en el VPS. Si falla por OOM, no hay fallback de calidad implementado — notificar.
- **Template incorrecto**: CurveReveal solo funciona bien para tendencias continuas. Si el brief pide un ranking, usar BarChart aunque "haya curvas" en el concepto.
- **Brief fuera de nicho**: `produce_animacion.py` valida el campo `niche` del brief. Si contiene palabras B2B (`empresas`, `api `, `automatización de negocio`, etc.) el script aborta antes del LLM. Corregir el brief o redirigir la pieza a otro formato.
- **Texto desbordando pantalla (StepReveal)**: al agregar pasos, el `set_width` debe aplicarse **antes** de `next_to` en `animacion_templates.py`. Si se revierte el orden, los textos anchos empujan el borde derecho fuera del frame. Bug corregido en v0.2.1.
- **Porcentaje desbordando pantalla (BarChart)**: el label `pc` se posiciona con `next_to(..., LEFT, buff=0.0)` dentro del fondo de la barra — borde derecho en x=3.50 (límite safe zone IG). No mover a `RIGHT` sin ajustar `max_w`. Bug corregido en v0.2.1.

## Verification

```bash
# Dry-run (sin render Manim, valida hasta anim_params.json)
$NOLAN_PYTHON produce_animacion.py --brief staging/fixtures/brief-binomio-cuadrado.yaml --dry-run

# Render completo (incluye safe zone check automático)
$NOLAN_PYTHON produce_animacion.py --brief staging/fixtures/brief-binomio-cuadrado.yaml
ffprobe staging/<piece_id>/animation.mp4 2>&1 | grep -E "1080x1920|Duration"

# Safe zone check manual sobre un MP4 existente
$NOLAN_PYTHON skills/nolan-produce-animacion/scripts/animacion_check.py staging/<piece_id>/animation.mp4
# → {"status": "ok", ...}  si pasa; stderr JSON con issues si hay overflow
```

## Outputs

```
staging/<piece_id>/
├── brief.yaml          (copia del brief de entrada)
├── anim_params.json    (JSON generado por LLM — template + params)
├── animation.mp4       (1080×1920 60fps — ya validado por animacion_check.py)
├── cover.jpg           (frame t=1s)
├── caption.md
├── alt_text.md
├── sources.md
├── metadata.json       (incluye manim_template, llm_cost_usd, render_exists)
└── content.yaml
```
